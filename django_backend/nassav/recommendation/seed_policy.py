"""Normalization shared by pure filters and persistence adapters."""

import re


def normalize_seed_value(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()
