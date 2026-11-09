from datetime import date

from toy_lair_assistant.gazeta.layout import barcode


def test_known_check_digit():
    assert barcode.check_digit("400638133393") == 1
    assert barcode.check_digit("978030640615") == 7


def test_code_is_13_digits_with_valid_check():
    code = barcode.digits_for(9, date(2026, 11, 9))
    assert len(code) == 13 and code.isdigit()
    assert barcode.check_digit(code[:12]) == int(code[12])
    assert code.startswith("978261109009")


def test_modules_have_95_with_guards():
    bits = barcode.modules(barcode.digits_for(9, date(2026, 11, 9)))
    assert len(bits) == 95 and bits.startswith("101") and bits.endswith("101") and bits[45:50] == "01010"


def test_svg_is_inline_and_labelled():
    out = barcode.svg(9, date(2026, 11, 9))
    assert out.startswith("<svg") and "<rect" in out and "9782611090095"[:3] in out
