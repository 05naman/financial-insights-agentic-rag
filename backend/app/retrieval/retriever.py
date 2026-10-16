from app.core.config import Settings, get_settings
from app.ingestion.classify import is_financial_query
from app.retrieval.embedder import Embedder
from app.retrieval.query_parser import parse_query
from app.retrieval.reranker import Reranker
from app.retrieval.rewriter import QueryRewriter
from app.retrieval.schemas import SearchFilters, SearchHit
from app.retrieval.vector_store import VectorStore


class Retriever:
    """Single entry point for search. Mode controls how much retrieval machinery is used."""

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        reranker: Reranker | None = None,
        settings: Settings | None = None,
        names: dict[str, str] | None = None,
    ):
        self.embedder = embedder
        self.store = store
        self.reranker = reranker
        self.settings = settings or get_settings()
        self.names = names or {}
        self.rewriter = QueryRewriter(
            spell_correct=self.settings.query_spell_correct,
            synonyms=self.settings.query_synonyms,
            numbers=self.settings.index_normalize_numbers,
        )
        self._stats_count = -1
        self._years_by_ticker: dict[str, set[int]] = {}

    def _refresh_corpus(self) -> None:
        """Re-read the index vocabulary and company list when its size changes (e.g. after an upload)."""
        count = self.store.count()
        if count == self._stats_count:
            return
        stats = self.store.corpus_stats()
        protected = [
            *stats.years_by_ticker,
            *(w for n in self.names.values() for w in n.lower().split()),
        ]
        self.rewriter.protected = {p.lower() for p in protected}
        self.rewriter.set_vocabulary(stats.words)
        self._years_by_ticker = stats.years_by_ticker
        self._stats_count = count

    def resolve_filters(self, query: str, filters: SearchFilters | None) -> SearchFilters:
        """Keep the caller's filters; fill whatever is missing from the company/year written in the query."""
        given = filters or SearchFilters()
        if not self.settings.query_auto_filters:
            return given
        self._refresh_corpus()
        found = parse_query(query, self.names, sorted(self._years_by_ticker))
        return SearchFilters(
            tickers=given.tickers or found.tickers,
            fiscal_years=given.fiscal_years or found.fiscal_years,
        )

    def search(
        self,
        query: str,
        *,
        limit: int = 6,
        filters: SearchFilters | None = None,
        hybrid: bool = True,
        rerank: bool = True,
        improve: bool = True,
    ) -> list[SearchHit]:
        """`improve=False` gives the plain baseline: no typo fixing, synonyms, auto filters or boost."""
        dense_q, sparse_q, intent_text = query, None, query
        if improve:
            self._refresh_corpus()
            filters = self.resolve_filters(query, filters)
            rewritten = self.rewriter.rewrite(query)
            dense_q, sparse_q = rewritten.dense, rewritten.sparse
            intent_text = (
                rewritten.dense
            )  # judge "is this a money question?" on the typo-corrected text
        dense, sparse = self.embedder.embed_query(dense_q, sparse_q)
        use_rerank = rerank and self.reranker is not None
        wants_boost = not self.settings.query_boost_financial_only or is_financial_query(
            intent_text
        )
        boost = self.settings.query_statement_boost if improve and wants_boost else 0.0
        # a boost can only promote passages that are in the pool, so give it a wide one
        fetch = max(limit * 4, 60) if boost else (limit * 4 if use_rerank else limit)
        hits = self.store.search(dense, sparse if hybrid else None, limit=fetch, filters=filters)
        if boost:
            # money question: prefer the primary statements over notes that merely mention the words
            hits = sorted(
                hits,
                key=lambda h: h.score + (boost if h.kind == "statement" else 0.0),
                reverse=True,
            )
            hits = hits[: limit * 4 if use_rerank else limit]
        if use_rerank:
            hits = self.reranker.rerank(query, hits, limit)  # type: ignore[union-attr]
        return hits
