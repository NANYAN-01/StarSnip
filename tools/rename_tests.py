"""一次性维护脚本：把 tests/ 里的旧路径与旧模块名 starsnip 化。"""
import glob
import os
import re

ROBUST = ('import os as _os\n'
          'sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname('
          '_os.path.abspath(__file__))), "src"))')
OLD_PATH = r'sys\.path\.insert\(0, r"D:\\030\\screenocr\\src"\)'

changed = []
for fp in glob.glob(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                 "tests", "test_*.py")):
    with open(fp, "r", encoding="utf-8") as f:
        src = f.read()
    orig = src
    # 1) 硬编码路径 -> 鲁棒路径
    src = re.sub(OLD_PATH, ROBUST, src)
    # 2) test_mcp 里的 SRC 常量
    src = src.replace('SRC = r"D:\\030\\screenocr\\src"',
                      'SRC = _os.path.join(_os.path.dirname(_os.path.dirname('
                      '_os.path.abspath(__file__))), "src")\nimport os as _os')
    # 3) 模块名 / 子进程 / 环境变量 / 字符串
    src = src.replace("from screenocr", "from starsnip")
    src = src.replace("import screenocr", "import starsnip")
    src = src.replace('"-m", "screenocr"', '"-m", "starsnip"')
    src = src.replace("-m screenocr", "-m starsnip")
    src = src.replace("SCREENOCR_HOME", "STARSNIP_HOME")
    src = src.replace('"screenocr_', '"starsnip_')
    src = src.replace("screenocr.log", "starsnip.log")
    src = src.replace("ScreenOCR", "StarSnip")
    src = src.replace("screenocr --mcp", "starsnip --mcp")
    if src != orig:
        with open(fp, "w", encoding="utf-8") as f:
            f.write(src)
        changed.append(os.path.basename(fp))

print("已修改 %d 个测试文件:" % len(changed))
for c in changed:
    print("  ", c)
