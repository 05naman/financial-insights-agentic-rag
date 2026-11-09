FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app ./app

# Prebuilt, read-only pieces made by scripts/prepare_deploy.sh (see docs/deploy-cloud-run.md):
#   deploy/models  the embedding models (no download at start-up)
#   deploy/qdrant  the search index for the reports
COPY deploy/models ./models
COPY deploy/qdrant ./seed/qdrant
COPY deploy/start.sh ./start.sh

ENV PATH="/app/.venv/bin:$PATH" \
    EMBEDDING_CACHE_DIR=/app/models \
    QDRANT_PATH=/tmp/qdrant \
    HF_HUB_OFFLINE=1 \
    PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "start.sh"]
