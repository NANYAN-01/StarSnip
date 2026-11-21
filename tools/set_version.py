r"""把版本号同步到三处：__init__.py / version.json / StarSnip.version（exe 属性页）。

用法：
    .venv\Scripts\python tools\set_version.py 1.2.0
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INIT = os.path.join(ROOT, "src", "starsnip", "__init__.py")
VERSION_JSON = os.path.join(ROOT, "version.json")
SPEC_VERSION = os.path.join(ROOT, "StarSnip.version")

VS_TEMPLATE = '''VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vers},
    prodvers={vers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [StringStruct('CompanyName', 'StarSnip'),
         StringStruct('FileDescription', '星剪 StarSnip · 截图 OCR'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', 'StarSnip'),
         StringStruct('LegalCopyright', 'MIT License'),
         StringStruct('OriginalFilename', 'StarSnip.exe'),
         StringStruct('ProductName', '星剪 StarSnip'),
         StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
'''


def main(argv):
    if len(argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", argv[1]):
        print("用法：python tools/set_version.py 1.2.0")
        return 2
    version = argv[1]
    parts = tuple(int(x) for x in version.split("."))
    vers = "(%d, %d, %d, 0)" % parts

    with open(INIT, "r", encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r'__version__ = "[\d.]+"', '__version__ = "%s"' % version, text)
    with open(INIT, "w", encoding="utf-8") as f:
        f.write(text)

    data = {}
    if os.path.isfile(VERSION_JSON):
        with open(VERSION_JSON, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    data["version"] = version
    data["url"] = ("https://github.com/NANYAN-01/StarSnip/releases/tag/v%s"
                   % version)
    with open(VERSION_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    with open(SPEC_VERSION, "w", encoding="utf-8") as f:
        f.write(VS_TEMPLATE.format(version=version, vers=vers))

    print("版本已同步为 %s（__init__.py / version.json / StarSnip.version）"
          % version)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
