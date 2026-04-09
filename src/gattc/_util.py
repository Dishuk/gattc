"""Shared internal utilities for gattc."""

import warnings
from typing import Any, Dict


def warn_unknown_keys(data: Dict[str, Any], valid_keys: set, context: str) -> None:
    """Warn about unknown keys in a YAML dict."""
    unknown = set(data.keys()) - valid_keys
    if unknown:
        keys_str = ", ".join(f"'{k}'" for k in sorted(unknown))
        warnings.warn(f"Unknown key(s) {keys_str} in {context} (typo?)")
