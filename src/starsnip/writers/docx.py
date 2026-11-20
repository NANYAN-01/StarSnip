"""Minimal OOXML .docx writer (stdlib only): headings, paragraphs, lists, tables."""

import io
import zipfile
from xml.sax.saxutils import escape

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

HEAD_SIZES = {1: 40, 2: 34, 3: 30, 4: 26, 5: 24, 6: 22}


def _paragraph(text: str, bold: bool = False, size: int = None) -> str:
    run_props = ""
    if bold or size:
        run_props = "<w:rPr>" + ("<w:b/>" if bold else "") + (
            '<w:sz w:val="%d"/>' % size if size else "") + "</w:rPr>"
    return ("<w:p><w:r>%s<w:t xml:space=\"preserve\">%s</w:t></w:r></w:p>"
            % (run_props, escape(text)))


def _table(rows) -> str:
    borders = ("<w:tblBorders>"
               '<w:top w:val="single" w:sz="4" w:color="999999"/>'
               '<w:left w:val="single" w:sz="4" w:color="999999"/>'
               '<w:bottom w:val="single" w:sz="4" w:color="999999"/>'
               '<w:right w:val="single" w:sz="4" w:color="999999"/>'
               '<w:insideH w:val="single" w:sz="4" w:color="999999"/>'
               '<w:insideV w:val="single" w:sz="4" w:color="999999"/>'
               "</w:tblBorders>")
    parts = ["<w:tbl><w:tblPr>" + borders + "</w:tblPr>"]
    for row in rows:
        parts.append("<w:tr>")
        for cell in row:
            parts.append("<w:tc>" + _paragraph(cell or "") + "</w:tc>")
        parts.append("</w:tr>")
    parts.append("</w:tbl>")
    return "".join(parts)


def build_docx(blocks) -> bytes:
    body = []
    for block in blocks:
        kind = block["type"]
        if kind == "heading":
            body.append(_paragraph(block["text"], bold=True,
                                   size=HEAD_SIZES.get(block["level"], 24)))
        elif kind == "paragraph":
            body.append(_paragraph(block["text"]))
        elif kind == "list":
            for item in block["items"]:
                body.append(_paragraph("• " + item))
        elif kind == "table":
            body.append(_table(block["rows"]))
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(body) + "<w:sectPr/></w:body></w:document>")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", document)
    return buf.getvalue()
