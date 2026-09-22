from __future__ import annotations

import re

CHITCHAT = frozenset(
    {
        "hello",
        "hi",
        "hey",
        "thanks",
        "thank you",
        "good morning",
        "good night",
        "how are you",
        "yo",
        "ok",
        "okay",
        "bye",
    }
)

_CLEAN = re.compile(r"[^a-z0-9\s]+")


def is_chitchat(text: str) -> bool:
    cleaned = " ".join(_CLEAN.sub(" ", text.lower()).split())
    return cleaned in CHITCHAT
