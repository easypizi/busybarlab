"""EAN-13 barcode as inline SVG. The digits come from the issue number and the date."""

from __future__ import annotations

from datetime import date

L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
FIRST = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def check_digit(first12: str) -> int:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return (10 - total % 10) % 10


def digits_for(issue_no: int, day: date) -> str:
    """12 digits: country-like prefix 978, the date as YYMMDD, the issue number, then the check digit."""
    body = f"978{day:%y%m%d}{issue_no % 1000:03d}"
    return body + str(check_digit(body))


def modules(code: str) -> str:
    """The 95 bars and spaces as a string of 0 and 1."""
    first = int(code[0])
    out = "101"
    for i, ch in enumerate(code[1:7]):
        out += (L if FIRST[first][i] == "L" else G)[int(ch)]
    out += "01010"
    for ch in code[7:]:
        out += R[int(ch)]
    return out + "101"


def svg(issue_no: int, day: date, height: int = 34) -> str:
    code = digits_for(issue_no, day)
    bits = modules(code)
    guard = {0, 1, 2, 45, 46, 47, 48, 49, 92, 93, 94}
    bars = []
    i = 0
    while i < len(bits):
        if bits[i] == "1":
            j = i
            while j < len(bits) and bits[j] == "1":
                j += 1
            h = height + 3 if any(k in guard for k in range(i, j)) else height
            bars.append(f'<rect x="{i + 9}" y="0" width="{j - i}" height="{h}"/>')
            i = j
        else:
            i += 1
    text = (
        f'<text x="0" y="{height + 11}" font-size="8" font-family="Literata, serif">{code[0]}</text>'
        f'<text x="12" y="{height + 11}" font-size="8" font-family="Literata, serif" textLength="40">{code[1:7]}</text>'
        f'<text x="57" y="{height + 11}" font-size="8" font-family="Literata, serif" textLength="40">{code[7:]}</text>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 113 {height + 13}" role="img" aria-label="Issue barcode {code}">'
        f'<rect x="0" y="0" width="113" height="{height + 13}" fill="#fff"/><g fill="#000">{"".join(bars)}</g>{text}</svg>'
    )
