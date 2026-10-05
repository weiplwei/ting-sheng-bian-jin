"""Load local sound-library metadata and resolve its sample paths."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_DIR = ROOT / "data" / "library"
LIB_PATH = LIBRARY_DIR / "items.json"
CATALOG_HINTS_PATH = ROOT / "data" / "catalog_hints.json"
CATALOG_HINTS_EN_PATH = ROOT / "data" / "catalog_hints.en.json"


def load_items(language: str = "zh") -> list[dict]:
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
    if language == "en":
        localized = json.loads(CATALOG_HINTS_EN_PATH.read_text(encoding="utf-8"))
        names = localized.get("names", {})
        for item in items:
            item["name"] = names.get(item.get("name"), item.get("name"))
            item["hints"] = [names.get(hint, hint) for hint in item.get("hints", [])]
            tag_names = {"大金": "Red Item", "唯一类": "Unique", "同音类": "Homophone", "听声鉴宝": "Sound ID"}
            item["tags"] = [tag_names.get(tag, tag) for tag in item.get("tags", [])]
            candidate_hints = item.get("candidateHints")
            if candidate_hints:
                for category in ("gold", "nonGold"):
                    for candidate in candidate_hints.get(category, []):
                        candidate["name"] = names.get(candidate["name"], candidate["name"])
    elif language != "zh":
        raise ValueError(f"unsupported language: {language}")
    for item in items:
        for sample in item.get("samples", []):
            file_path = Path(sample["file"])
            if not file_path.is_absolute():
                sample["file"] = str(LIBRARY_DIR / file_path)
    return items
