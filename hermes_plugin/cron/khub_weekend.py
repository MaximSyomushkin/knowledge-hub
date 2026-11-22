"""Hermes no-agent cron job: the knowledge-hub weekend work list (`khub digest --weekend`), Friday and Saturday.
Hermes runs scripts without arguments, so each digest has its own wrapper. See khub_digest.py."""

from __future__ import annotations

import sys

import khub_digest


def main() -> int:
    return khub_digest.main(("digest", "--weekend"))


if __name__ == "__main__":
    sys.exit(main())
