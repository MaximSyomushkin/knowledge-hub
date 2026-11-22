"""Hermes no-agent cron job, every 15 minutes: reminders for timed items starting within the hour
(`khub remind`). Silent unless something is coming up. See khub_digest.py."""

from __future__ import annotations

import sys

import khub_digest


def main() -> int:
    return khub_digest.main(("remind",))


if __name__ == "__main__":
    sys.exit(main())
