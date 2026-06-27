#!/usr/bin/env python3
"""
Create a changelist markdown entry for a project.

Example:
    python3 init_changelist_entry.py \
        --project /path/to/project \
        --title "login retry limit" \
        --version v0.3.0 \
        --type update
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ENTRY_TYPES = ("create", "update", "fix", "refactor", "docs", "release")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    value = re.sub(r"-{2,}", "-", value)
    return value or "change"


def sanitize_token(value: str) -> str:
    value = value.strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    value = value.strip("-")
    return value or "entry"


def unique_path(base_path: Path) -> Path:
    if not base_path.exists():
        return base_path

    counter = 2
    while True:
        candidate = base_path.with_name(f"{base_path.stem}-{counter}{base_path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def build_template(project_dir: Path, title: str, entry_type: str, entry_date: str, label: str) -> str:
    return f"""# {label} - {title}

- Date: {entry_date}
- Type: {entry_type}
- Project: {project_dir}

## Why
- TODO

## What Changed
- TODO

## Files Changed
- `TODO`

## Behavior Impact
- TODO

## Validation
- Not run: TODO

## Risks
- None noted yet.

## Follow-up
- None.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a changelist markdown entry in a project's changelist folder.",
    )
    parser.add_argument("--project", required=True, help="Path to the project directory")
    parser.add_argument("--title", required=True, help="Short title for this change batch")
    parser.add_argument(
        "--version",
        help="Optional version label to use in the filename and title",
    )
    parser.add_argument(
        "--type",
        default="update",
        choices=ENTRY_TYPES,
        help="Change type shown in the document",
    )
    parser.add_argument(
        "--date",
        dest="entry_date",
        default=date.today().isoformat(),
        help="Entry date in YYYY-MM-DD format",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = Path(args.project).resolve()
    if not project_dir.exists():
        print(f"[ERROR] Project directory not found: {project_dir}", file=sys.stderr)
        return 1
    if not project_dir.is_dir():
        print(f"[ERROR] Project path is not a directory: {project_dir}", file=sys.stderr)
        return 1

    changelist_dir = project_dir / "changelist"
    changelist_dir.mkdir(parents=True, exist_ok=True)

    title_slug = slugify(args.title)
    prefix = sanitize_token(args.version) if args.version else args.entry_date
    base_path = changelist_dir / f"{prefix}-{title_slug}.md"
    entry_path = unique_path(base_path)

    label = args.version.strip() if args.version else args.entry_date
    content = build_template(project_dir, args.title.strip(), args.type, args.entry_date, label)
    entry_path.write_text(content)
    print(entry_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
