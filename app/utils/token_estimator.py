from __future__ import annotations

import math
import re

ESTIMATOR_NAME = "simple_mixed_heuristic_v1"
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk_count = len(_CJK_RE.findall(text))
    without_cjk = _CJK_RE.sub(" ", text)
    word_count = len(_WORD_RE.findall(without_cjk))
    punct_count = len([ch for ch in without_cjk if not ch.isspace() and not ch.isalnum()])
    total = cjk_count + word_count + math.ceil(punct_count / 4)
    return max(1, total)
