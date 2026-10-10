"""Bengali script helpers: script detection, visual→logical reordering, sanity checks."""

import re

CONSONANTS = "কখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহড়ঢ়য়ৎ"
HASANTA = "্"
PRE_KARS = "িেৈ"  # dependent vowels drawn to the left of their consonant
POST_KARS = "াীুূৃৗ"
SIGNS = "ংঃঁ"
_BENGALI_RANGE = ("ঀ", "৿")

# A consonant cluster: consonant (+ hasanta + consonant)*, optionally a nukta.
_CLUSTER = f"[{CONSONANTS}]়?(?:{HASANTA}[{CONSONANTS}]়?)*"
_PRE_KAR_BEFORE_CLUSTER = re.compile(f"([{PRE_KARS}]+)({_CLUSTER})")
_PRE_KAR_AT_WORD_START = re.compile(f"(?:^|(?<=[\\s\\W\\d]))[{PRE_KARS}]")
_KAR_AT_WORD_START = re.compile(f"(?:^|(?<=[\\s]))[{PRE_KARS}{POST_KARS}{HASANTA}]")
_DOUBLE_KAR = re.compile(f"[{PRE_KARS}{POST_KARS}]{{2,}}")


def is_bengali_char(ch: str) -> bool:
    return _BENGALI_RANGE[0] <= ch <= _BENGALI_RANGE[1]


def bengali_ratio(text: str) -> float:
    """Share of letters in `text` that are Bengali (0.0 when there are no letters)."""
    letters = [c for c in text if c.isalpha() or is_bengali_char(c)]
    if not letters:
        return 0.0
    return sum(is_bengali_char(c) for c in letters) / len(letters)


def detect_lang(text: str) -> str:
    """'bn' or 'en' by majority script."""
    return "bn" if bengali_ratio(text) >= 0.5 else "en"


def compose_split_vowels(text: str) -> str:
    """ে + া → ো and ে + ৗ → ৌ (legacy encodings and visual order emit them split)."""
    return text.replace("ো", "ো").replace("ৌ", "ৌ")


def move_pre_kars(text: str) -> str:
    """Move pre-base vowel signs from before their consonant cluster to after it."""
    return compose_split_vowels(_PRE_KAR_BEFORE_CLUSTER.sub(r"\2\1", text))


def looks_visual_order(text: str) -> bool:
    """True when pre-base vowel signs often start words: a sign of visual (glyph) order.

    In correctly ordered Unicode a dependent vowel never begins a word, so a high rate of
    word-initial ি/ে/ৈ means the PDF's text layer was written in drawing order.
    """
    pre = sum(text.count(k) for k in PRE_KARS)
    if pre < 3:
        return False
    return len(_PRE_KAR_AT_WORD_START.findall(text)) / pre > 0.3


def fix_visual_order(text: str) -> str:
    return move_pre_kars(text) if looks_visual_order(text) else text


_PIPE_DANDA = re.compile(r"(?<=[ঀ-৿])\s?[|৷]")


def normalize_ocr(text: str) -> str:
    """Fix OCR look-alikes: '৷' (U+09F7) or '|' after Bengali text is really a danda '।'."""
    return _PIPE_DANDA.sub("।", text)


def invalid_sequence_ratio(text: str) -> float:
    """Rough share of Bengali words that are malformed (kar at word start, doubled kars)."""
    words = [w for w in text.split() if any(is_bengali_char(c) for c in w)]
    if not words:
        return 0.0
    bad = sum(1 for w in words if _KAR_AT_WORD_START.match(w) or _DOUBLE_KAR.search(w))
    return bad / len(words)
