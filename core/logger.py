import logging
from typing import cast

MODEL_INPUT = 15
MODEL_OUTPUT = 16


class DtvLogger(logging.Logger):
    def model_input(self, msg, *args, **kwargs) -> None:
        if self.isEnabledFor(MODEL_INPUT):
            self._log(MODEL_INPUT, msg, args, **kwargs)

    def model_output(self, msg, *args, **kwargs) -> None:
        if self.isEnabledFor(MODEL_OUTPUT):
            self._log(MODEL_OUTPUT, msg, args, **kwargs)


def _register_custom_levels() -> None:
    if logging.getLevelName(MODEL_INPUT) == f"Level {MODEL_INPUT}":
        logging.addLevelName(MODEL_INPUT, "MODEL_INPUT")
    if logging.getLevelName(MODEL_OUTPUT) == f"Level {MODEL_OUTPUT}":
        logging.addLevelName(MODEL_OUTPUT, "MODEL_OUTPUT")

    if logging.getLoggerClass() is not DtvLogger:
        logging.setLoggerClass(DtvLogger)


class ColorFormatter(logging.Formatter):
    _RESET = "\033[0m"
    _COLORS = {
        MODEL_INPUT: "\033[31m",  # red
        MODEL_OUTPUT: "\033[32m",  # green
        logging.DEBUG: "\033[36m",  # cyan
        logging.WARNING: "\033[33m",  # yellow
        logging.ERROR: "\033[31m",  # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        color = self._COLORS.get(record.levelno)
        if not color:
            return base
        return f"{color}{base}{self._RESET}"


def setup_default_logging(level: int = MODEL_INPUT) -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        ColorFormatter(fmt="%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> DtvLogger:
    return cast(DtvLogger, logging.getLogger(name))


_register_custom_levels()
setup_default_logging()
