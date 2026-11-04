"""rapidfuzz-compatible fallback.

Android builds (and minimal installs) may not have the native rapidfuzz wheel.
The metadata code only uses token_set_ratio and token_sort_ratio, so a small
difflib implementation is enough to keep matching working.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz  # type: ignore
except Exception:  # pragma: no cover - fallback path
    def _tokens(text) -> list[str]:
        return re.findall(r"\w+", str(text or "").lower())

    def _ratio(a: str, b: str) -> float:
        return 100.0 * SequenceMatcher(None, a, b).ratio()

    class _Fuzz:
        @staticmethod
        def token_sort_ratio(a, b) -> float:
            return _ratio(" ".join(sorted(_tokens(a))), " ".join(sorted(_tokens(b))))

        @staticmethod
        def token_set_ratio(a, b) -> float:
            ta, tb = set(_tokens(a)), set(_tokens(b))
            if not ta or not tb:
                return 0.0
            inter = ta & tb
            left = " ".join(sorted(inter | (ta - tb)))
            right = " ".join(sorted(inter | (tb - ta)))
            return _ratio(left, right)

    fuzz = _Fuzz()
