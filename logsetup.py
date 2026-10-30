"""Log com rotação, faulthandler e captura de exceções não tratadas."""
from __future__ import annotations

import faulthandler
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from appinfo import data_dir

_crash_file = None  # precisa ficar aberto durante toda a execução


def setup_logging() -> logging.Logger:
    global _crash_file
    log_dir = data_dir()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[RotatingFileHandler(log_dir / "feed.log", maxBytes=512 * 1024, backupCount=3, encoding="utf-8")],
    )
    logger = logging.getLogger("jwfeed")

    # Em um .exe --windowed não existe stderr. O faulthandler grava aqui as quedas
    # nativas (DLLs, COM), que não viram exceção Python.
    try:
        _crash_file = open(log_dir / "crash.log", "a", encoding="utf-8", buffering=1)
        faulthandler.enable(_crash_file, all_threads=True)
    except OSError:
        logger.exception("Não foi possível ativar o faulthandler")

    def log_uncaught(exc_type, exc, tb):
        logger.critical("Exceção não tratada", exc_info=(exc_type, exc, tb))

    def log_thread_uncaught(args):
        name = args.thread.name if args.thread else "?"
        logger.critical("Exceção não tratada na thread %s", name,
                        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = log_uncaught
    threading.excepthook = log_thread_uncaught
    return logger
