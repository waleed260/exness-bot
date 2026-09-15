"""Self-contained logger: writes to exness_bot/logs/bot.log and stdout."""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys

_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

_logger = logging.getLogger("exness_bot")
_logger.setLevel(logging.INFO)

if not _logger.handlers:
    _fh = RotatingFileHandler(os.path.join(_LOG_DIR, "bot.log"), maxBytes=5 * 1024 * 1024, backupCount=3)
    _fh.setFormatter(_fmt)
    _logger.addHandler(_fh)

    _ch = logging.StreamHandler(sys.stdout)
    _ch.setFormatter(_fmt)
    _logger.addHandler(_ch)


def event(name, **fields):
    """Emit a compact JSON event without allowing credential-shaped fields."""
    safe = {}
    for key, value in fields.items():
        lowered = key.lower()
        if any(secret in lowered for secret in ("password", "api_key", "token", "secret")):
            safe[key] = "[REDACTED]"
        else:
            safe[key] = value
    _logger.info(json.dumps({"event": name, **safe}, sort_keys=True, default=str))


class _Wrap:
    logger = _logger
    event = staticmethod(event)


log = _Wrap()
