from __future__ import annotations

import os


def normalize_path(raw_path: str | None) -> str:
    text = (raw_path or "").strip()
    if not text:
        return ""
    return os.path.abspath(os.path.expanduser(text))

