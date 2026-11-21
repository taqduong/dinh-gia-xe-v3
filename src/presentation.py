"""Hiển thị thống nhất số và đơn vị tiếng Việt."""

from html import escape

BLUE = "#153B66"
ORANGE = "#E3742C"
TEAL = "#087B75"
MUTED = "#50647D"


def vi(value: float, digits: int = 1) -> str:
    return f"{value:,.{digits}f}".translate(str.maketrans(",.", ".,"))


def signed(value: float, digits: int = 1) -> str:
    return ("+" if value > 0 else "−" if value < 0 else "") + vi(abs(value), digits)


def pct(fraction: float, digits: int = 1) -> str:
    return f"{vi(100 * fraction, digits)}%"


def table_html(headers, rows) -> str:
    head = "".join(f"<th scope='col'>{escape(str(value))}</th>" for value in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in row) + "</tr>" for row in rows)
    return f"<div class='table-wrap'><table class='valuation-table'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
