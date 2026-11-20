"""Logger test: writes lines and rotates at size limit."""

import os
import sys
import tempfile

import os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "src"))

from starsnip.logger import Logger


def main():
    base = tempfile.mkdtemp(prefix="starsnip_log_")
    path = os.path.join(base, "starsnip.log")
    log = Logger(path, max_bytes=200)
    log.info("hello")
    assert "hello" in open(path, encoding="utf-8").read()

    for i in range(20):
        log.info("line %d" % i)
    assert os.path.isfile(path + ".1"), "should rotate"
    print("log file:", os.path.getsize(path), "bytes; rotated:",
          os.path.getsize(path + ".1"), "bytes")
    print("test_logger OK")


if __name__ == "__main__":
    main()
