from __future__ import annotations

import logging
from rich.logging import RichHandler

from .config import settings


def setup_logging() -> None:
    # RichHandler gives readable logs in terminal
    logging.basicConfig(
        level=getattr(logging, settings.quant_log_level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )
