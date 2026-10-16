import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json(text: str) -> dict | list | None:
    """Best-effort JSON extraction from an LLM reply (handles code fences and chatter)."""
    candidates = [text.strip()]
    candidates += [m.strip() for m in _FENCE.findall(text)]
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if start != -1 and end > start:
            candidates.append(text[start : end + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except (json.JSONDecodeError, ValueError):
            continue
    return None
