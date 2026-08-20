#!/usr/bin/env python3
"""Version 1.22 entry point for source, batch, single-order, and packaged GUI runs."""

from __future__ import annotations

import sys

import shower_batch
import shower_programmer
import shower_programmer_gui
import shower_v4_features


shower_v4_features.install(shower_programmer, shower_batch, shower_programmer_gui)


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1].lower() == "--batch":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        raise SystemExit(shower_batch.main())
    if len(sys.argv) >= 2 and sys.argv[1].lower() == "--single":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        raise SystemExit(shower_programmer.main())
    shower_programmer_gui.main()


if __name__ == "__main__":
    main()
