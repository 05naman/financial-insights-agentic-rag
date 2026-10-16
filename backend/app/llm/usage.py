"""Running token counts per model since the server started, so free-tier daily limits can be watched."""

import logging
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_tally: dict[str, dict[str, int]] = defaultdict(
    lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
)


def record(label: str, prompt_tokens: int | None, completion_tokens: int | None) -> None:
    with _lock:
        t = _tally[label]
        t["calls"] += 1
        t["prompt_tokens"] += prompt_tokens or 0
        t["completion_tokens"] += completion_tokens or 0
    logger.info("llm %s tokens prompt=%s completion=%s", label, prompt_tokens, completion_tokens)


def snapshot() -> dict[str, dict[str, int]]:
    with _lock:
        return {
            k: {**v, "total_tokens": v["prompt_tokens"] + v["completion_tokens"]}
            for k, v in _tally.items()
        }


def reset() -> None:
    with _lock:
        _tally.clear()
