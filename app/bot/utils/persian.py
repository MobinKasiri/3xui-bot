"""Persian digit conversion and Toman formatting."""

_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_EN_DIGITS = "0123456789"
_TRANS = str.maketrans(_EN_DIGITS, _FA_DIGITS)


def to_persian_digits(text: str | int | float) -> str:
    return str(text).translate(_TRANS)


def format_toman(amount: int) -> str:
    """Format integer Toman amount with Persian comma-separated digits."""
    formatted = f"{amount:,}"
    return to_persian_digits(formatted)
