"""把截图/导出文件落到用户目录下的 StarSnip 子文件夹。"""

import datetime
import os

from . import paths


def timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def save_png(img, directory: str = None, prefix: str = "StarSnip") -> str:
    directory = directory or paths.pictures_dir()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "%s_%s.png" % (prefix, timestamp()))
    with open(path, "wb") as f:
        f.write(img.to_png())
    return path


def save_bytes(data: bytes, directory: str = None, extension: str = "txt",
               prefix: str = "StarSnip") -> str:
    directory = directory or paths.documents_dir()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "%s_%s.%s" % (prefix, timestamp(), extension))
    with open(path, "wb") as f:
        f.write(data)
    return path
