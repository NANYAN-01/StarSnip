"""Table parsing / export tests."""

import sys

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import ocr_core, tablefmt

MD = """```markdown
| 序号 | 商品名称 | 单价(元) | 数量 | 金额(元) |
| --- | --- | --- | --- | --- |
| 1 | 笔记本 | 6899.00 | 2 | 13798.00 |
| 2 | 鼠标 | 649.00 | 8 | 5192.00 |
```"""

ALIGNED = """序号  商品名称   单价(元)  数量  金额(元)
1    笔记本     6899.00   2     13798.00
2    鼠标       649.00    8     5192.00
合计                                  18990.00"""

PLAIN = "这是一段普通文本\n没有表格结构\n只有三行"

# glm-ocr 对表格常直接吐 HTML（有时没有 <table> 包裹）
HTML = ("<thead><tr><th>项目</th><th>预算(万元)</th></tr></thead><tbody>"
        "<tr><td>星剪</td><td>12.5</td></tr>"
        "<tr><td>合计</td><td>12.5</td></tr></tbody>")

HTML_BARE = ("<tr><td>序号</td><td>A</td><td>B</td></tr>"
             "<tr><td>1</td><td>11</td><td>12</td></tr>")

HTML_COLSPAN = ('<tr><td colspan="3">本周出入库明细</td></tr>'
                '<tr><td>日期</td><td>数量</td><td>金额</td></tr>'
                '<tr><td>08-01</td><td>3</td><td>1,234.56</td></tr>')


def main():
    rows = tablefmt.parse_table(MD)
    assert rows and len(rows) == 3, rows
    assert rows[0][1] == "商品名称"
    assert rows[2][4] == "5192.00"
    print("markdown rows:", rows)

    rows2 = tablefmt.parse_table(ALIGNED)
    assert rows2 and len(rows2) == 3, rows2
    assert rows2[1][1] == "笔记本"
    print("aligned rows:", rows2)

    assert tablefmt.parse_table(PLAIN) is None
    assert not tablefmt.looks_like_table(PLAIN)
    assert tablefmt.looks_like_table(MD)

    # HTML 表格（表头/表体包裹、裸 <tr>、跨行标题）
    html_rows = tablefmt.parse_table(HTML)
    assert html_rows == [["项目", "预算(万元)"], ["星剪", "12.5"],
                         ["合计", "12.5"]], html_rows
    bare_rows = tablefmt.parse_table(HTML_BARE)
    assert bare_rows == [["序号", "A", "B"], ["1", "11", "12"]], bare_rows
    span_rows = tablefmt.parse_table(HTML_COLSPAN)
    assert span_rows == [["日期", "数量", "金额"],
                         ["08-01", "3", "1,234.56"]], span_rows
    assert tablefmt.html_table(HTML_COLSPAN)[1] == ["本周出入库明细"]
    print("html rows:", span_rows)

    # HTML 转 Markdown 后仍能再解析，且 clean_grounding 不带标签
    md_from_html = tablefmt.html_to_markdown(HTML)
    assert md_from_html.startswith("| 项目 |"), md_from_html[:40]
    assert tablefmt.parse_table(md_from_html) == html_rows
    cleaned = ocr_core.clean_grounding(HTML)
    assert "<" not in cleaned and tablefmt.parse_table(cleaned) == html_rows
    print("html -> markdown OK")

    # 导出用的严格判定：只认 Markdown / HTML，不把空格对齐的散文当表格
    assert tablefmt.structured_table(HTML) == html_rows
    assert len(tablefmt.structured_table(MD)) == 3
    assert tablefmt.structured_table(ALIGNED) is None
    print("structured_table OK")

    # 一张图里两张表：列宽不同取第一张；被空行隔开的同一张表仍合并
    two = ("| A | B |\n| --- | --- |\n| 1 | 2 |\n\n说明文字\n\n"
           "| C | D | E |\n| --- | --- | --- |\n| 3 | 4 | 5 |")
    assert tablefmt.parse_table(two) == [["A", "B"], ["1", "2"]]
    split = "| A | B |\n| --- | --- |\n\n| 1 | 2 |"
    assert tablefmt.parse_table(split) == [["A", "B"], ["1", "2"]]
    html_two = ("<table><tr><td>A</td><td>B</td></tr>"
                "<tr><td>1</td><td>2</td></tr></table>"
                "<table><tr><td>C</td><td>D</td><td>E</td></tr>"
                "<tr><td>3</td><td>4</td><td>5</td></tr></table>")
    assert tablefmt.parse_table(html_two) == [["A", "B"], ["1", "2"]]
    print("multiple tables OK")

    tsv = tablefmt.to_tsv(rows)
    assert tsv.splitlines()[0].count("\t") == 4
    md = tablefmt.to_markdown(rows)
    assert md.splitlines()[1].startswith("| ---") or "---" in md.splitlines()[1]
    print("tsv/md export OK")
    print("test_tablefmt OK")


if __name__ == "__main__":
    main()
