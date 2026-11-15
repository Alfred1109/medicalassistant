"""CSV escaping shared by every exporter.

Spreadsheet programs treat a leading ``=``, ``+``, ``-`` or ``@`` (also after
leading whitespace) as the start of a formula, so a clinical value carrying
such a prefix is prefixed with an apostrophe before it reaches the file. One
rule for every exporter, so a new export cannot silently ship without it.
"""

import csv
import io

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")


def csv_safe(value):
    """Return a value safe to place in a spreadsheet cell.

    Numbers are returned as-is: they cannot be formulas, and a leading ``-``
    on a numeric column would be read as text once an apostrophe is added.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        text = str(value)
    elif isinstance(value, (int, float)):
        return str(value)
    else:
        text = str(value)
    # Spreadsheet programs also recognize formulas after leading whitespace.
    if text.lstrip().startswith(_FORMULA_PREFIXES) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def csv_cell(value):
    """Escape one cell for a hand-built CSV row (quoting included)."""
    text = csv_safe(value)
    if any(character in text for character in ',"\n'):
        return '"' + text.replace('"', '""') + '"'
    return text


def csv_text(rows):
    """Render rows as CSV text with line feeds as the row separator."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    for row in rows:
        writer.writerow([csv_safe(cell) for cell in row])
    return stream.getvalue()
