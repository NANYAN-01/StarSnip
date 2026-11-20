"""DOCX / XLSX writers: build files and validate OOXML structure."""

import io
import os
import sys
import tempfile
import zipfile
from xml.dom import minidom

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import ai_writer, mdblocks
from starsnip.writers.docx import build_docx
from starsnip.writers.xlsx import build_xlsx

SAMPLE = """# 销售汇总表

统计口径:实际发货 币种:人民币(元)

| 序号 | 商品名称 | 金额(元) |
| --- | --- | --- |
| 1 | 笔记本 | 13798.00 |
| 2 | 鼠标 | 5192.00 |

- 合计 18990.00
"""


def open_zip(data, entries):
    z = zipfile.ZipFile(io.BytesIO(data))
    names = set(z.namelist())
    missing = [e for e in entries if e not in names]
    assert not missing, missing
    for name in names:
        if name.endswith(".xml") or name.endswith(".rels"):
            minidom.parseString(z.read(name))
    return z


def main():
    blocks = mdblocks.parse_blocks(SAMPLE)
    kinds = [b["type"] for b in blocks]
    assert kinds.count("heading") == 1 and "table" in kinds, kinds
    print("blocks:", kinds)

    docx = build_docx(blocks)
    z = open_zip(docx, ["[Content_Types].xml", "_rels/.rels",
                        "word/document.xml"])
    doc = z.read("word/document.xml").decode("utf-8")
    z.close()
    assert "销售汇总表" in doc and "<w:tbl>" in doc and "13798.00" in doc
    print("docx OK (%d bytes)" % len(docx))

    rows = [b["rows"] for b in blocks if b["type"] == "table"][0]
    xlsx = build_xlsx([rows])
    z = open_zip(xlsx, ["[Content_Types].xml", "_rels/.rels",
                        "xl/workbook.xml", "xl/worksheets/sheet1.xml"])
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    wb = z.read("xl/workbook.xml").decode("utf-8")
    z.close()
    assert "商品名称" in sheet and "13798.00" in sheet
    assert 't="inlineStr"' in sheet and "<v>13798.00</v>" in sheet
    assert 'name="Sheet1"' in wb
    print("xlsx OK (%d bytes, numeric cell inline)" % len(xlsx))

    # 千分位写成数值、前导零编码保持文本
    sheet2 = build_xlsx([[["编码", "金额"], ["007", "1,234.56"]]])
    z = zipfile.ZipFile(io.BytesIO(sheet2))
    s2 = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    z.close()
    assert "<v>1234.56</v>" in s2, s2
    assert "007" in s2 and "<v>007</v>" not in s2, s2
    print("xlsx numeric comma / leading zero OK")

    # 已解析出表格时导出不调模型（bogus 地址 + 1s 超时，真调必失败）
    table_md = ("| 序号 | 名称 | 金额 |\n| --- | --- | --- |\n"
                "| 1 | 苹果 | 1,234.56 |\n| 2 | 梨 | 7 |")
    out = tempfile.mkdtemp(prefix="starsnip_tbl_")
    bogus = "http://127.0.0.1:1"
    path, md = ai_writer.export(table_md, "xlsx", "dummy:1b", bogus,
                                directory=out, timeout=1)
    z = zipfile.ZipFile(path)
    sheet3 = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    z.close()
    assert "苹果" in sheet3 and "<v>1234.56</v>" in sheet3, sheet3
    assert "<v>7</v>" in sheet3, sheet3
    path, _ = ai_writer.export(table_md, "docx", "dummy:1b", bogus,
                               directory=out, timeout=1)
    z = zipfile.ZipFile(path)
    doc3 = z.read("word/document.xml").decode("utf-8")
    z.close()
    assert "<w:tbl>" in doc3 and "苹果" in doc3
    path, _ = ai_writer.export(table_md, "md", "dummy:1b", bogus,
                               directory=out, timeout=1)
    with open(path, encoding="utf-8") as f:
        assert f.read().strip() == table_md
    assert len(os.listdir(out)) == 3
    print("table export is local & exact (no LLM)")
    print("test_writers OK")


if __name__ == "__main__":
    main()
