"""History store tests: add/search/delete/prune/clear with temp dir."""

import os
import sys
import tempfile

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import png
from starsnip.history import History

THUMB = png.encode_png(2, 2, bytes([0, 0, 255, 255] * 4))


def main():
    base = tempfile.mkdtemp(prefix="starsnip_hist_")
    hist = History(base_dir=base, keep=20)

    rid = hist.add("hotkey", "text", "glm-ocr:latest", 1900,
                   "上海分公司 合计 34615.50", thumb_png=THUMB,
                   meta={"size": [800, 200]})
    assert rid > 0
    row = hist.get(rid)
    assert row["text"].find("34615.50") >= 0
    assert os.path.isfile(hist.thumb_file(row["thumb_path"]))
    print("add ok, thumb:", row["thumb_path"])

    hist.add("file", "text", "qwen2.5vl:7b", 3200, "Invoice No. 20260901")
    hits = hist.search("34615")
    assert len(hits) == 1 and hits[0]["id"] == rid
    assert len(hist.search("glm-ocr")) == 1
    assert len(hist.search()) == 2
    print("search ok")

    for i in range(25):
        hist.add("hotkey", "text", "m", 10, "filler %d" % i)
    assert len(hist.search(limit=100)) == 20, len(hist.search(limit=100))
    assert hist.get(rid) is None  # oldest pruned
    print("prune ok (keep=20)")

    last = hist.search(limit=1)[0]["id"]
    hist.delete(last)
    assert hist.get(last) is None
    print("delete ok")

    hist.clear()
    assert hist.search() == []
    assert os.listdir(hist.thumbs_dir) == []
    hist.close()
    print("test_history OK")


if __name__ == "__main__":
    main()
