import json
from pathlib import Path

from app.core.config import Settings


def load_company_names(settings: Settings) -> dict[str, str]:
    """Optional `{"TCS": "Tata Consultancy Services Limited"}` file; empty if absent or unreadable."""
    path = Path(settings.companies_file)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return {str(k).upper(): str(v) for k, v in data.items()}
    except (json.JSONDecodeError, AttributeError):
        return {}
