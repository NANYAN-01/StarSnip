"""update.py 离线单测：版本比较 / 清单解析 / 三源回退 / 缓存。"""

import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

# 别把测试缓存写进真实的 %APPDATA%\StarSnip
_TMP = tempfile.mkdtemp(prefix="probe_update_")
os.environ["STARSNIP_HOME"] = _TMP

from starsnip import update  # noqa: E402

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
        print("  x %s" % msg)
    else:
        print("  v %s" % msg)


def test_parse():
    print("[版本号]")
    check(update.parse_version("v1.2.0") == (1, 2, 0), "v1.2.0")
    check(update.parse_version("1.2") == (1, 2, 0), "1.2 补零")
    check(update.parse_version("1.10.0") > update.parse_version("1.9.9"),
          "1.10 比 1.9 新（字符串比较会错）")
    check(update.parse_version("") == (0, 0, 0), "空串兜底")
    check(update.is_newer("1.2.0", "1.1.0"), "1.2.0 比 1.1.0 新")
    check(not update.is_newer("1.1.0", "1.1.0"), "同版本不算新")


def test_manifest():
    print("[清单解析]")
    info = update._manifest({"version": "1.2.0", "url": "u", "notes": "n",
                             "assets": {"exe": "e", "sha256": "s"}})
    check(info["latest"] == "1.2.0" and info["exe"] == "e"
          and info["sha256"] == "s", "自建清单字段齐全")
    info = update._manifest({"version": "1.2.0", "exe": "e2"})
    check(info["exe"] == "e2", "兼容顶层 exe")
    try:
        update._manifest({"notes": "x"})
        check(False, "缺 version 应抛错")
    except ValueError:
        check(True, "缺 version 抛错")


def test_release():
    print("[GitHub Release 解析]")
    info = update._release({"tag_name": "v1.3.0", "html_url": "h", "body": "b",
                            "assets": [{"name": "notes.txt"},
                                       {"name": "StarSnip.exe",
                                        "browser_download_url": "d",
                                        "digest": "sha256:abc"}]})
    check(info["latest"] == "v1.3.0", "取 tag_name")
    check(info["exe"] == "d", "挑出 exe 资产")
    check(info["sha256"] == "abc", "解析 sha256 digest")


def test_fallback():
    print("[三源回退]")
    orig_fetch = update._fetch
    orig_cache = (update.write_cache, update.read_cache)

    calls = []

    def fake_fetch(url, timeout=5):
        calls.append(url)
        if "api.github.com" in url:
            raise OSError("blocked")
        return json.dumps({"version": "1.2.0", "url": "u"}).encode()

    update._fetch = fake_fetch
    update.write_cache = lambda info: None
    update.read_cache = lambda: {}
    try:
        info = update.check({})
        check(info["ok"] and info["source"] == "raw", "GitHub 不可用 → 回退 raw")
        check(len(calls) == 2, "按顺序试了两个源")
        calls.clear()
        info = update.check({"update_url": "https://example.com/v.json"})
        check(info["source"] == "custom" and calls[0].endswith("v.json"),
              "自填 update_url 优先")
    finally:
        update._fetch = orig_fetch
        update.write_cache, update.read_cache = orig_cache


def test_cache():
    print("[缓存]")
    info = {"latest": "1.2.0", "url": "u", "notes": "n", "exe": "", "sha256": ""}
    update.write_cache(info)
    cached = update.read_cache()
    check(cached.get("latest") == "1.2.0", "缓存写入后能读回")
    check(update.cache_fresh(), "刚写的缓存算新鲜")
    cached["checked_at"] = 0
    with open(update.cache_path(), "w", encoding="utf-8") as f:
        json.dump(cached, f)
    check(not update.cache_fresh(), "24h 前的缓存不算新鲜")


def main():
    test_parse()
    test_manifest()
    test_release()
    test_fallback()
    test_cache()
    if failures:
        print("\nFAILED %d 项：" % len(failures))
        for item in failures:
            print("  -", item)
        return 1
    print("\ntest_update OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
