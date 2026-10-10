import pytest

from pdf2kindle import bengali
from pdf2kindle.legacy import bijoy
from tests.fixtures import BIJOY_LINES


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        ("Avgvi", "আমার"),
        ("‡mvbvi", "সোনার"),  # ে + া around a consonant → ো
        ("‡`Š", "দৌ"),  # ে + ৗ → ৌ
        ("wK›Zz", "কিন্তু"),  # pre-base ি moves after its consonant
        ("Kg©", "কর্ম"),  # reph moves before its cluster
        ("cÖwZ‡e`b", "প্রতিবেদন"),
        ("Rb¨", "জন্য"),
        ("1971", "১৯৭১"),
        *BIJOY_LINES,
    ],
)
def test_bijoy_to_unicode(legacy, expected):
    assert bijoy.to_unicode(legacy) == expected


@pytest.mark.parametrize(
    ("font", "legacy"),
    [
        ("SutonnyMJ", True),
        ("ABCDEF+SutonnyMJ-Bold", True),
        ("AdarshaLipiMJ", True),
        ("NotoSerifBengali-Regular", False),
        ("Georgia", False),
        ("MJesty", False),
    ],
)
def test_bijoy_font_names(font, legacy):
    assert bijoy.is_bijoy_font(font) is legacy


def test_bijoy_score_separates_bijoy_from_english():
    assert bijoy.bijoy_score("Avgvi ‡mvbvi evsjv, Avwg ‡Zvgvq fv‡jvevwm|") > 0.5
    assert bijoy.bijoy_score("The keeper climbed the iron stairs every morning.") < 0.2


def test_visual_order_is_detected_and_fixed():
    visual = "িক েখলা িনেয় েস বািড় েগল"  # কি খেলা নিয়ে সে বাড়ি গেল, in glyph order
    assert bengali.looks_visual_order(visual)
    assert bengali.fix_visual_order(visual) == "কি খেলা নিয়ে সে বাড়ি গেল"


def test_logical_text_is_left_alone():
    text = "কি খেলা নিয়ে সে বাড়ি গেল"
    assert not bengali.looks_visual_order(text)
    assert bengali.fix_visual_order(text) == text
    assert bengali.invalid_sequence_ratio(text) == 0


def test_normalize_ocr_dandas():
    assert bengali.normalize_ocr("গ্রাম ছিল৷ সেই") == "গ্রাম ছিল। সেই"
    assert bengali.normalize_ocr("ছিল | সেই") == "ছিল। সেই"
    assert bengali.normalize_ocr("a | b") == "a | b"


def test_detect_lang():
    assert bengali.detect_lang("আমার সোনার বাংলা") == "bn"
    assert bengali.detect_lang("My golden Bengal") == "en"
    assert bengali.detect_lang("আমার golden বাংলা") == "bn"
