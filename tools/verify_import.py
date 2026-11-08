"""Verify sanitized imported files, not authenticity or production security."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(manifest, base):
    data = json.loads(manifest.read_text(encoding="utf-8"))
    entries = data["files"]
    if not isinstance(entries, dict) or not entries:
        raise ValueError("Empty or invalid manifest")
    for name, expected in entries.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe manifest path")
        path = base / relative
        if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
            raise ValueError("Unsafe file path")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Content mismatch: {name}")
    return len(entries)


if __name__ == "__main__":
    total = verify(ROOT / "IMPORT_MANIFEST.json", ROOT)
    team = verify(ROOT / "team" / "MANIFEST.json", ROOT / "team")
    print(f"Verified {total} imported files and {team} team manifest entries.")
