"""Write a default 4-step hint ladder into a private word list, so the owner can edit it.

Usage:
    uv run python -m app.scripts.prepare_hints secrets/words.json            # fill missing
    uv run python -m app.scripts.prepare_hints secrets/words.json --overwrite

Existing hints are kept unless --overwrite is given. A backup `<file>.bak` is written first.
Hints go from hardest to easiest; the fourth must make the word unambiguous. Output lists
only counts, never words or hints.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from app.models.hints import derive_hints, hint_problems
from app.schemas.word_seed import WordSeedFile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare progressive hints for a word list.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    raw = json.loads(args.file.read_text(encoding="utf-8"))
    items = WordSeedFile.validate_python(raw)  # schema check before touching the file
    filled = 0
    for record, item in zip(raw, items, strict=True):
        if record.get("hints") and not args.overwrite:
            continue
        entry = item.to_entry()
        record["hints"] = list(derive_hints(entry))
        filled += 1
    bad = sum(1 for r in raw if hint_problems(r["word"], tuple(r["hints"])))
    if bad:
        print(f"error: {bad} entries have unusable hints; nothing written", file=sys.stderr)
        return 1
    shutil.copy2(args.file, args.file.with_suffix(args.file.suffix + ".bak"))
    args.file.write_text(json.dumps(raw, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"hints written for {filled} of {len(raw)} words (backup: {args.file.name}.bak)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
