"""Hermes no-agent cron job: the knowledge-hub Sunday recap (`khub digest --weekly`). See khub_digest.py."""

from __future__ import annotations

import sys

import khub_digest


def main() -> int:
    return khub_digest.main(("digest", "--weekly"))


if __name__ == "__main__":
    sys.exit(main())
