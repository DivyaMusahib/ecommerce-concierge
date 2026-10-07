"""
Price formatting utilities."""

def format_inr(amount) -> str:
    """
    Format an integer price as Indian Rupees with Indian grouping.

    Examples:
        format_inr(124990)  -> 'Rs.1,24,990'
        format_inr(9995)    -> 'Rs.9,995'
        format_inr(500)     -> 'Rs.500'
        format_inr(0)       -> 'Rs.0'
    """
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return "Rs.0"

    if amount < 0:
        return f"-{format_inr(-amount)}"

    s = str(amount)
    if len(s) <= 3:
        return f"Rs.{s}"

    # Indian number system: last 3 digits, then groups of 2
    last3 = s[-3:]
    rest = s[:-3]
    parts = []
    while rest:
        parts.append(rest[-2:])
        rest = rest[:-2]

    return f"Rs.{','.join(reversed(parts))},{last3}"

def format_inr_symbol(amount) -> str:
    """Same as format_inr() but uses the Rs. prefix instead of symbol for ASCII safety."""
    return format_inr(amount)

def parse_inr(price_str: str) -> int:
    """
    Parse an INR string back to an integer.

    Examples:
        parse_inr('Rs.1,24,990') -> 124990
        parse_inr('Rs.9,995')    -> 9995
    """
    cleaned = price_str.replace("Rs.", "").replace(",", "").strip()
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return 0
