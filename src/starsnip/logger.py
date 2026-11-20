"""极简轮转文件日志，位于 StarSnip 数据目录下的 starsnip.log。"""

import datetime
import os

from . import paths


def default_log_path() -> str:
    return paths.log_path()


class Logger:
    def __init__(self, path: str = None, max_bytes: int = 1024 * 1024):
        self.path = path or default_log_path()
        self.max_bytes = max_bytes
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def info(self, message: str) -> None:
        line = "%s  %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             message)
        try:
            if os.path.isfile(self.path) and os.path.getsize(self.path) > self.max_bytes:
                os.replace(self.path, self.path + ".1")
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def exception(self, exc: BaseException) -> None:
        import traceback
        self.info("EXCEPTION %s: %s" % (type(exc).__name__, exc))
        self.info(traceback.format_exc())
