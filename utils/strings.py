"""
String helper
"""

import json
from pathlib import Path
import random

_STRINGS = {}

def load_strings(path: str | Path = "strings.json"):
    """Load strings.json into memory."""
    path = Path(path)

    with open(path, "r", encoding="utf-8") as f:
        _STRINGS.update(json.load(f))

def get_string(key: str) -> str:
    """Get a string by key."""
    return _STRINGS.get(key, f"<missing string: {key}>")

def get_random_string(category):
    """Get a random string based on category."""
    if category < 50:
        category = "low"
    elif 50 <= category < 80:
        category = "mid"
    else:
        category = "high"

    return random.choice(_STRINGS.get(category, ["No message available."]))
