"""Split an answer into speakable sentences so playback can start early."""

from __future__ import annotations

import re

_BOUNDARY = re.compile(r"(?<=[.!?…])\s+|\n+")


def split_sentences(text: str, min_chars: int = 24) -> list[str]:
    """Split ``text`` at sentence ends, merging fragments shorter than ``min_chars``.

    Short pieces ("Sr.", "Ok.") sound choppy when synthesized alone and cost a
    synthesis round trip each, so they are glued to a neighbour.
    """
    parts = [p.strip() for p in _BOUNDARY.split(text.strip()) if p and p.strip()]
    merged: list[str] = []
    for part in parts:
        if merged and len(merged[-1]) < min_chars:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    if len(merged) > 1 and len(merged[-1]) < min_chars:
        tail = merged.pop()
        merged[-1] = f"{merged[-1]} {tail}"
    return merged


__all__ = ["split_sentences"]
