import re

_COMMA_IN_NUMBER = re.compile(r"(?<=\d),(?=\d)")


def normalize_numbers(text: str) -> str:
    """'1,89,866' -> '189866'. Indian digit grouping would otherwise be split into '1', '89', '866' by the
    keyword index, which makes a full figure impossible to match exactly."""
    return _COMMA_IN_NUMBER.sub("", text)
