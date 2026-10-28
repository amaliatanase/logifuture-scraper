"""Load the two config files that drive the scraper.

``config/company.json`` — company identity (never hardcode it in source).
``config/scraper.json`` — sources, selector cascades, retry policy, delays.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _ROOT / "config"


def _load(name: str) -> dict[str, Any]:
    return json.loads((_CONFIG_DIR / name).read_text(encoding="utf-8"))


company: dict[str, Any] = _load("company.json")
scraper: dict[str, Any] = _load("scraper.json")

USER_AGENT: str = scraper["userAgent"]
COMPANY_CIF: str = company["id"]
OWN_URL_PREFIX: str = scraper["ownJobUrlPrefix"]
