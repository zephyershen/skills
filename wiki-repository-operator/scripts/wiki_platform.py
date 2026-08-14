#!/usr/bin/env python3
"""Entrypoint for the Wiki Repository Operator skill."""

from pathlib import Path

from wiki_repository.cli import main


if __name__ == "__main__":
    raise SystemExit(main(operator_root=Path(__file__).absolute().parents[1]))
