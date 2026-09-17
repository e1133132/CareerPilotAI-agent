from __future__ import annotations

import os
import logging


def debug(message, prefix="DEBUG"):
    if os.getenv("DEBUG", "false").lower() == "true":
        logging.getLogger(prefix.lower()).debug(message)
