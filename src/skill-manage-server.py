#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from skill_manage.app import main


if __name__ == "__main__":
    main()
