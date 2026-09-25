from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "dist", ".pytest_cache"}
ALLOWED_KEYS = {"sk-abcdefghijklmnopqrstuvwxyz"}
KEY_PATTERN = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}")


def scan_text(text: str) -> list[str]:
    return [match for match in KEY_PATTERN.findall(text) if match not in ALLOWED_KEYS]


def scan_path(path: Path) -> list[str]:
    hits: list[str] = []
    if path.is_file():
        return [
            f"{path}: {item}"
            for item in scan_text(path.read_text(encoding="utf-8", errors="ignore"))
        ]
    for file in path.rglob("*"):
        if not file.is_file() or SKIP_DIRS.intersection(file.parts):
            continue
        if file.stat().st_size > 1_000_000:
            continue
        for item in scan_text(file.read_text(encoding="utf-8", errors="ignore")):
            hits.append(f"{file.relative_to(path)}: {item}")
    return hits


def test_repo_allows_fixture_keys() -> None:
    assert scan_path(ROOT) == []


def test_planted_provider_key_fails(tmp_path: Path) -> None:
    planted = "sk-" + "plantedproviderkeyvalue999"
    target = tmp_path / "notes.txt"
    target.write_text(f"token {planted}\n", encoding="utf-8")
    hits = scan_path(target)
    assert hits
    assert planted in hits[0]
