"""
String helper
"""

import json
from pathlib import Path

_STRINGS = {}

def load_strings(path: str | Path = "strings.json"):
    """Load strings.json into memory."""
    path = Path(path)

    with open(path, "r", encoding="utf-8") as f:
        _STRINGS.update(json.load(f))

def get_string(key: str) -> str:
    """Get a string by key."""
    return _STRINGS.get(key, f"<missing string: {key}>")
