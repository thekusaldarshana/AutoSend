"""Turn whatever is typed in the Excel phone cell into a WhatsApp-ready number."""
import re

_SPLIT = re.compile(r"[/,;\n\r]|\bor\b|&")


def normalize_phone(raw, default_cc: str = "94") -> tuple[str | None, str | None]:
    """Return (digits, None) on success or (None, reason) on failure.

    Digits are international format without '+', e.g. '94700000001'.
    Only the first number in a cell is used.
    """
    if raw is None:
        return None, "No phone number"
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "-"):
        return None, "No phone number"

    first = _SPLIT.split(s)[0].strip()
    # Excel sometimes stores numbers as floats: 771234567.0 or 7.71234567E8
    if re.fullmatch(r"\d+\.0+", first):
        first = first.split(".")[0]
    elif re.fullmatch(r"\d(\.\d+)?[eE]\+?\d+", first):
        try:
            first = str(int(float(first)))
        except ValueError:
            pass

    international = first.startswith("+") or first.startswith("00")
    digits = re.sub(r"\D", "", first)
    if not digits:
        return None, "No phone number"

    if digits.startswith("00"):
        digits = digits[2:]
    elif not international:
        if digits.startswith("0"):
            digits = default_cc + digits[1:]
        elif digits.startswith(default_cc) and len(digits) >= len(default_cc) + 8:
            pass
        else:
            digits = default_cc + digits

    if not (8 <= len(digits) <= 15):
        return None, "Number looks incomplete"
    if digits.startswith("94") and len(digits) != 11:
        return None, "Sri Lankan numbers have 9 digits after 94"
    return digits, None


def pretty_phone(digits: str | None) -> str:
    if not digits:
        return ""
    if digits.startswith("94") and len(digits) == 11:
        return f"+94 {digits[2:4]} {digits[4:7]} {digits[7:]}"
    return "+" + digits
