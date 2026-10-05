"""Import a SoundRadar .srz sound library into this project."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent


def extract_archive(archive: zipfile.ZipFile, destination: Path) -> None:
    """Extract archive members only when they remain inside the destination."""
    destination = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise ValueError(f"unsafe path in archive: {member.filename}") from exc
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                output.write(source.read())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, type=Path, help="path to a SoundRadar .srz library")
    parser.add_argument(
        "--dst",
        type=Path,
        default=ROOT / "data" / "library",
        help="local library directory (default: data/library)",
    )
    args = parser.parse_args()
    src = args.src.expanduser().resolve()
    dst = args.dst.expanduser().resolve()
    if not src.is_file():
        parser.error(f"archive not found: {src}")

    raw = dst / "_raw"
    raw.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as archive:
        extract_archive(archive, raw)

    items = []
    for meta_path in sorted((raw / "items").glob("*/meta.json")):
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        item_dir = meta_path.parent
        display_hints = metadata.get("displayHints", [])
        samples = []
        for sample in metadata.get("samples", []):
            sample_path = item_dir / sample["file"]
            if sample_path.is_file():
                relative_path = PurePosixPath("_raw", "items", item_dir.name, sample["file"])
                samples.append(
                    {
                        "file": relative_path.as_posix(),
                        "lenS": sample.get("lenS"),
                        "source": sample.get("source"),
                    }
                )
        tags = metadata.get("tags", [])
        item = {
            "id": metadata["id"],
            "name": metadata["name"],
            "threshold": metadata.get("threshold", 0.75),
            "cooldownMs": metadata.get("cooldownMs", 400),
            "tags": tags,
            "samples": samples,
            "hints": [hint.get("name") for hint in display_hints],
        }
        classified_hints = [hint for hint in display_hints if "isGold" in hint]
        if classified_hints:
            item["unique"] = False
            item["candidateHints"] = {
                "gold": [
                    {key: hint[key] for key in ("name", "grid") if hint.get(key)}
                    for hint in classified_hints if hint["isGold"]
                ],
                "nonGold": [
                    {key: hint[key] for key in ("name", "grid") if hint.get(key)}
                    for hint in classified_hints if not hint["isGold"]
                ],
            }
        else:
            item["unique"] = "唯一类" in tags
        items.append(item)

    dst.mkdir(parents=True, exist_ok=True)
    (dst / "items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Imported {len(items)} items into {dst}")
    for item in items:
        print(item["id"], item["name"], "samples", len(item["samples"]), "thr", item["threshold"])


if __name__ == "__main__":
    main()
