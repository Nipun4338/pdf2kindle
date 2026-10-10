"""Bijoy (SutonnyMJ family) ANSI → Unicode Bengali.

Bijoy fonts draw Bengali glyphs on Latin code points, in visual order: pre-base vowel
signs come before their consonant and the reph (©) after it. Conversion is a greedy
longest-match glyph table followed by reordering. Best-effort: tune against real books.
"""

import re

from pdf2kindle.bengali import CONSONANTS, HASANTA, POST_KARS, PRE_KARS, SIGNS, move_pre_kars

_REPH = ""  # placeholder for © until it is moved in front of its cluster

# Multi-glyph sequences first; lookup is longest-match so order here doesn't matter.
GLYPHS: dict[str, str] = {
    # conjuncts
    "i¨": "র‍্য", "ª¨": "্র্য", "¶¨": "ক্ষ্য",
    "°": "ক্ক", "±": "ক্ট", "³": "ক্ত", "K¡": "ক্ব", "µ": "ক্র", "K¥": "ক্ম", "KÐ": "ক্ল",
    "¶": "ক্ষ", "·": "ক্স", "¸": "গু", "»": "গ্ধ", "Mœ": "গ্ন", "M¥": "গ্ম", "MÐ": "গ্ল",
    "¼": "ঙ্ক", "•¶": "ঙ্ক্ষ", "•L": "ঙ্খ", "½": "ঙ্গ", "•N": "ঙ্ঘ",
    "”P": "চ্চ", "”Q": "চ্ছ", "”Q¡": "চ্ছ্ব", "”T": "চ্ঞ",
    "¾": "জ্জ", "¾¡": "জ্জ্ব", "À": "জ্ঝ", "Á": "জ্ঞ", "R¡": "জ্ব",
    "Â": "ঞ্চ", "Ã": "ঞ্ছ", "Ä": "ঞ্জ", "Å": "ঞ্ঝ",
    "Æ": "ট্ট", "U¡": "ট্ব", "U¥": "ট্ম", "Ç": "ড্ড",
    "È": "ণ্ট", "É": "ণ্ঠ", "Ê": "ণ্ড",
    "Ë": "ত্ত", "Ë¡": "ত্ত্ব", "Ì": "ত্থ", "Zœ": "ত্ন", "Z¥": "ত্ম", "Î": "ত্র",
    "Ï": "দ্দ", "×": "দ্ধ", "Ø": "দ্ব", "Ù": "দ্ম", "aŸ": "ধ্ব", "a¥": "ধ্ম",
    "›U": "ন্ট", "›V": "ন্ঠ", "›W": "ন্ড", "š¿": "ন্ত্র", "š—": "ন্ত", "š‘": "ন্তু",
    "š’": "ন্থ", "›`": "ন্দ", "›Ø": "ন্দ্ব", "Ü": "ন্ধ", "bœ": "ন্ন", "b¥": "ন্ম", "Ý": "ন্স",
    "Þ": "প্ট", "ß": "প্ত", "cœ": "প্ন", "à": "প্প", "cø": "প্ল", "á": "প্স", "d¬": "ফ্ল",
    "â": "ব্জ", "ã": "ব্দ", "ä": "ব্ধ", "eŸ": "ব্ব", "eø": "ব্ল", "å": "ভ্র",
    "gœ": "ম্ন", "¤ú": "ম্প", "ç": "ম্ফ", "¤^": "ম্ব", "¤¢": "ম্ভ", "¤£": "ম্ভ্র", "¤§": "ম্ম",
    "¤ø": "ম্ল", "i“": "রু", "iƒ": "রূ",
    "é": "ল্ক", "ê": "ল্গ", "ë": "ল্ট", "ì": "ল্ড", "í": "ল্প", "î": "ল্ফ", "j¦": "ল্ব",
    "j¥": "ল্ম", "jø": "ল্ল",
    "ï": "শু", "ð": "শ্চ", "k¦": "শ্ব", "k¥": "শ্ম", "kø": "শ্ল",
    "®Œ": "ষ্ক", "ó": "ষ্ট", "ô": "ষ্ঠ", "ò": "ষ্ণ", "®ú": "ষ্প", "õ": "ষ্ফ", "®§": "ষ্ম",
    "¯Œ": "স্ক", "÷": "স্ট", "ö": "স্খ", "¯—": "স্ত", "¯‘": "স্তু", "¯’": "স্থ", "mœ": "স্ন",
    "¯ú": "স্প", "ù": "স্ফ", "¯^": "স্ব", "¯§": "স্ম", "¯ø": "স্ল", "¯¿": "স্ত্র",
    "û": "হু", "nè": "হ্ণ", "nŸ": "হ্ব", "ý": "হ্ন", "þ": "হ্ম", "n¬": "হ্ল", "ü": "হৃ",
    # half forms and subscript glyphs
    "®": "ষ্", "¯": "স্", "¤": "ম্", "›": "ন্", "š": "ন্", "•": "ঙ্", "”": "চ্",
    "^": "্ব", "‘": "্তু", "’": "্থ", "‹": "্ক", "Œ": "্ক্র", "—": "্ত", "¨": "্য",
    "ª": "্র", "«": "্র", "Ö": "্র", "¬": "্ল", "¡": "্ব", "¢": "্ভ", "£": "্ভ্র",
    "¥": "্ম", "¦": "্ব", "§": "্ম", "Ÿ": "্ব", "œ": "্ন", "è": "্ণ", "ú": "্প",
    "&": HASANTA, "©": _REPH,
    # vowels
    "Av": "আ", "A": "অ", "B": "ই", "C": "ঈ", "D": "উ", "E": "ঊ", "F": "ঋ", "G": "এ",
    "H": "ঐ", "I": "ও", "J": "ঔ",
    # consonants
    "K": "ক", "L": "খ", "M": "গ", "N": "ঘ", "O": "ঙ", "P": "চ", "Q": "ছ", "R": "জ",
    "S": "ঝ", "T": "ঞ", "U": "ট", "V": "ঠ", "W": "ড", "X": "ঢ", "Y": "ণ", "Z": "ত",
    "_": "থ", "`": "দ", "a": "ধ", "b": "ন", "c": "প", "d": "ফ", "e": "ব", "f": "ভ",
    "g": "ম", "h": "য", "i": "র", "j": "ল", "k": "শ", "l": "ষ", "m": "স", "n": "হ",
    "o": "ড়", "p": "ঢ়", "q": "য়", "r": "ৎ", "s": "ং", "t": "ঃ", "u": "ঁ",
    # vowel signs
    "v": "া", "w": "ি", "x": "ী", "y": "ু", "z": "ু", "“": "ু", "~": "ূ", "ƒ": "ূ", "‚": "ূ",
    "…": "ৃ", "„": "ৃ", "‡": "ে", "†": "ে", "‰": "ৈ", "ˆ": "ৈ", "Š": "ৗ",
    # digits and punctuation
    "0": "০", "1": "১", "2": "২", "3": "৩", "4": "৪", "5": "৫", "6": "৬", "7": "৭",
    "8": "৮", "9": "৯", "|": "।", "$": "৳", "Ñ": "—", "Ò": "“", "Ó": "”", "Ô": "‘", "Õ": "’",
}  # fmt: skip

_MAX_KEY = max(len(k) for k in GLYPHS)
_REPH_AFTER_CLUSTER = re.compile(
    f"([{CONSONANTS}]়?(?:{HASANTA}[{CONSONANTS}]়?)*)([{PRE_KARS}{POST_KARS}{SIGNS}]*){_REPH}"
)

# Font names that carry Bijoy-encoded text; "…MJ" is the Bijoy family suffix (SutonnyMJ,
# AdarshaLipiMJ, …).
LEGACY_FONT = re.compile(r"(sutonny|bijoy|mj\b|mj[-_,]|mj$)", re.IGNORECASE)


def is_bijoy_font(fontname: str) -> bool:
    # Drop subset prefixes like "ABCDEF+SutonnyMJ".
    return bool(LEGACY_FONT.search(fontname.split("+", 1)[-1]))


def _map_glyphs(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        for n in range(min(_MAX_KEY, len(text) - i), 0, -1):
            chunk = text[i : i + n]
            if chunk in GLYPHS:
                out.append(GLYPHS[chunk])
                i += n
                break
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def to_unicode(text: str) -> str:
    text = move_pre_kars(_map_glyphs(text))
    text = _REPH_AFTER_CLUSTER.sub(rf"র{HASANTA}\1\2", text)
    return text.replace(_REPH, f"র{HASANTA}")


def bijoy_score(text: str) -> float:
    """How strongly ASCII-ish `text` looks like unconverted Bijoy (0..1).

    Real English rarely contains ‡ © ¨ ª or 'Av', and its words are mostly lowercase
    after the first letter; Bijoy text interleaves upper/lowercase every glyph.
    """
    words = [w for w in text.split() if len(w) > 1]
    if not words:
        return 0.0
    markers = sum(text.count(m) for m in ("‡", "©", "¨", "ª", "Av", "Ö", "Ó", "Ò", "|"))
    mixed = sum(1 for w in words if re.search(r"[a-z][A-Z]", w) or re.search(r"[A-Z]v", w))
    return min(1.0, (mixed / len(words)) + markers / max(1, len(words)))
