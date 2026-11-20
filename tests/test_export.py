"""AI layout export test (live LLM): txt/md/docx/xlsx into a temp dir."""

import os
import sys
import tempfile
import zipfile

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import ai_writer, config

TEXT = """上海分公司 2026年8月销售汇总表
统计口径:实际发货 币种:人民币(元)
序号 商品名称 规格型号 单价(元) 数量 金额(元) 备注
1 联想ThinkPad X1 Carbon NB-X1C-2026 6899.00 2 13798.00 已发货
2 USB-C 扩展坞 4合1 USB-HUB-4K 189.50 15 2842.50 现货
合计 5 项 34615.50
制表人:李四 审核:王五 打印时间:2026-09-01 15:30:12"""


def main():
    cfg = config.load()
    out_dir = tempfile.mkdtemp(prefix="starsnip_export_")
    model = cfg.get("layout_model", "qwen3.5:4b")
    url = cfg["ollama_url"]
    paths = {}
    for fmt in ("md", "txt", "docx", "xlsx"):
        path, md = ai_writer.export(TEXT, fmt, model, url, directory=out_dir,
                                    timeout=120)
        assert os.path.isfile(path) and os.path.getsize(path) > 0, path
        paths[fmt] = path
        print("%-4s -> %s (%d bytes)" % (fmt, os.path.basename(path),
                                         os.path.getsize(path)))
        assert "上海分公司" in md or "上海" in md, md[:80]

    with open(paths["md"], encoding="utf-8") as f:
        md = f.read()
    assert "34615.50" in md or "合计" in md
    with open(paths["txt"], encoding="utf-8") as f:
        txt = f.read()
    assert "上海分公司" in txt
    for fmt in ("docx", "xlsx"):
        with zipfile.ZipFile(paths[fmt]) as z:
            assert z.testzip() is None
    print("test_export OK")


if __name__ == "__main__":
    main()
