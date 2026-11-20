"""OCR core smoke test against the live backend (skips if unreachable)."""

import os
import sys

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip import config, ocr_core


def main():
    cfg = config.load()
    fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "fixtures", "ocr_test.png")
    with open(os.path.normpath(fixture), "rb") as f:
        png = f.read()

    primary = ocr_core.call(png, cfg["default_model"], cfg["ollama_url"],
                            prompt=cfg["prompt"], timeout=60)
    print("primary:", primary["model"], primary["mode"], "%dms" % primary["elapsed_ms"])
    if not primary["ok"]:
        print("SKIP: backend unreachable ->", primary["error"])
        return 1
    print(primary["text"])
    assert "Invoice No. 20260901" in primary["text"]
    assert "1234.56" in primary["text"]

    models = cfg["verify_models"][:2]
    results = ocr_core.call_many(png, models, cfg["ollama_url"],
                                 prompt=cfg["prompt"], timeout=60)
    for res in results:
        print("verify %-40s ok=%s %dms" % (res["model"], res["ok"],
                                           res["elapsed_ms"]))
    assert any(r["ok"] for r in results)
    ok = [r for r in results if r["ok"]]
    diff = ocr_core.disagreements(ok[0]["text"], [r["text"] for r in ok[1:]])
    print("disagreement lines:", sorted(diff))

    from starsnip import tablefmt
    table_fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "fixtures", "ocr_table.png")
    with open(os.path.normpath(table_fixture), "rb") as f:
        table_png = f.read()
    tres = ocr_core.call(table_png, cfg["default_model"], cfg["ollama_url"],
                         prompt=ocr_core.TABLE_PROMPT, timeout=60)
    rows = tablefmt.parse_table(tres["text"]) if tres["ok"] else None
    assert rows and len(rows) >= 5, "table prompt should yield markdown table"
    flat = " ".join(" ".join(r) for r in rows)
    assert "34615.50" in flat
    print("table rows=%d cols=%d" % (len(rows), len(rows[0])))
    print("test_ocr_core OK")


if __name__ == "__main__":
    sys.exit(main())
