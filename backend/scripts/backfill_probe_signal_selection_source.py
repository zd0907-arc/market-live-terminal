#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.build_probe_signal_historical_similar import main as build_probe_signal_main


def main(argv: Optional[Sequence[str]] = None) -> None:
    build_probe_signal_main(argv)


if __name__ == "__main__":
    main()
