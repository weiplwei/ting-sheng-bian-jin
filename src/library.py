"""Load local sound-library metadata and resolve its sample paths."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_DIR = ROOT / "data" / "library"
LIB_PATH = LIBRARY_DIR / "items.json"
CATALOG_HINTS_PATH = ROOT / "data" / "catalog_hints.json"


def load_items() -> list[dict]:
    if not LIB_PATH.exists():
        raise FileNotFoundError(
            f"library not found: {LIB_PATH}; run: python import_library.py --src PATH_TO_LIBRARY.srz"
        )
    items = json.loads(LIB_PATH.read_text(encoding="utf-8"))
    catalog = {}
    if CATALOG_HINTS_PATH.is_file():
        catalog = json.loads(CATALOG_HINTS_PATH.read_text(encoding="utf-8")).get("items", {})
    for item in items:
        shared_hints = catalog.get(item.get("id"), {})
        item.update(shared_hints)
        for sample in item.get("samples", []):
            file_path = Path(sample["file"])
            if not file_path.is_absolute():
                sample["file"] = str(LIBRARY_DIR / file_path)
    return items
