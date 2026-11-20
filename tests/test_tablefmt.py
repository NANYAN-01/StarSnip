"""Table parsing / export tests."""

import sys

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import tablefmt

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

    tsv = tablefmt.to_tsv(rows)
    assert tsv.splitlines()[0].count("\t") == 4
    md = tablefmt.to_markdown(rows)
    assert md.splitlines()[1].startswith("| ---") or "---" in md.splitlines()[1]
    print("tsv/md export OK")
    print("test_tablefmt OK")


if __name__ == "__main__":
    main()
