"""Minimal OOXML .xlsx writer (stdlib only), one worksheet per markdown table."""

import io
import re
import zipfile
from xml.sax.saxutils import escape

# 纯数字才写成数值单元格：保留 "007" 这类前导零编码为文本，
# "1,234.56" 这类千分位写法转成数值（Excel 里才对得上金额列）
_NUMERIC = re.compile(r"^-?(?:0|[1-9]\d*)(?:\.\d+)?$")
_NUMERIC_COMMA = re.compile(r"^-?(?:0|[1-9]\d{0,2})(?:,\d{3})+(?:\.\d+)?$")


def _col_name(idx: int) -> str:
    name = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        name = chr(65 + rem) + name
    return name


def _cell(ref: str, value: str) -> str:
    text = (value or "").strip()
    if _NUMERIC.match(text):
        return '<c r="%s"><v>%s</v></c>' % (ref, text)
    if _NUMERIC_COMMA.match(text):
        return '<c r="%s"><v>%s</v></c>' % (ref, text.replace(",", ""))
    return ('<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
            % (ref, escape(text)))


def _sheet_xml(rows) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             "<sheetData>"]
    for r, row in enumerate(rows, start=1):
        cells = "".join(_cell("%s%d" % (_col_name(c), r), val)
                        for c, val in enumerate(row))
        parts.append('<row r="%d">%s</row>' % (r, cells))
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


def build_xlsx(sheets) -> bytes:
    """sheets: list of list-of-rows (list of list of cells)."""
    if not sheets:
        sheets = [[["(empty)"]]]
    names = ["Sheet%d" % (i + 1) for i in range(len(sheets))]
    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
    for i in range(1, len(sheets) + 1):
        content_types.append(
            '<Override PartName="/xl/worksheets/sheet%d.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i)
    content_types.append("</Types>")

    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                "<sheets>" + "".join(
                    '<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                    % (names[i], i + 1, i + 1) for i in range(len(sheets)))
                + "</sheets></workbook>")

    rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i in range(1, len(sheets) + 1):
        rels.append('<Relationship Id="rId%d" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                    'Target="worksheets/sheet%d.xml"/>' % (i, i))
    rels.append("</Relationships>")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(content_types))
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" '
                   'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                   'Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", "".join(rels))
        for i, rows in enumerate(sheets, start=1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, _sheet_xml(rows))
    return buf.getvalue()
