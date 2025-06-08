from os import environ
from datetime import datetime
from zoneinfo import ZoneInfo
from contextvars import ContextVar
from logging import Formatter, StreamHandler, Logger, NOTSET
from colorlog import ColoredFormatter


class SingletonMeta(type):
    _instance = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instance:
            instance = super().__call__(*args, **kwargs)
            cls._instance[cls] = instance
        return cls._instance[cls]


class DevFusionLogger(Logger, metaclass=SingletonMeta):
    correlation_id_var = ContextVar("correlation_id", default=None)
    _initialized = False

    def __init__(self):
        if DevFusionLogger._initialized:
            return

        super().__init__(name="DevFusionLogger", level=environ.get("LOG_LEVEL", NOTSET))

        Formatter.converter = self.israel_time
        local_formatter = ColoredFormatter(
            "%(log_color)s%(asctime)s | %(levelname)s | %(msg)s",
            datefmt="%d-%m-%Y, %H:%M:%S",
            log_colors={
                "DEBUG": "blue",
                "INFO": "",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )

        console_handler = StreamHandler()
        console_handler.setFormatter(local_formatter)
        self.addHandler(console_handler)

        DevFusionLogger._initialized = True

    def set_correlation_id(self, correlation_id: int) -> None:
        self.correlation_id_var.set(correlation_id)

    def get_correlation_id(self) -> str:
        return self.correlation_id_var.get()

    def israel_time(self, *args):
        return datetime.now(tz=ZoneInfo("Asia/Jerusalem")).timetuple()


logger = DevFusionLogger()
