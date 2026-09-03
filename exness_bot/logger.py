"""Self-contained logger so exness_bot does not depend on the research project's
log/ package (which hardcodes a file path and needs colorama)."""

import logging
import os
import sys

_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

_logger = logging.getLogger("exness_bot")
_logger.setLevel(logging.INFO)

if not _logger.handlers:
    _fh = logging.FileHandler(os.path.join(_LOG_DIR, "bot.log"))
    _fh.setFormatter(_fmt)
    _logger.addHandler(_fh)

    _ch = logging.StreamHandler(sys.stdout)
    _ch.setFormatter(_fmt)
    _logger.addHandler(_ch)


class _Wrap:
    logger = _logger


log = _Wrap()
