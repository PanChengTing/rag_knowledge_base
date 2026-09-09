
import logging
import sys
from .config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False
def configure_logging()->None:
    global _configured
    if _configured:
        return
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT,datefmt=_DATE_FORMAT))

    #清除原来的日志格式，用上我们自己设置的
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    #设置输出日志的最低等级，设置为SETTINGS里面的等级
    root.setLevel(settings.log_level.upper())

    for noisy in ("uvicorn","uvicorn.error","uvicorn.access"):
        logging.getLogger(noisy).handlers.clear()
        #允许日志输出用根目录的格式
        logging.getLogger(noisy).propagate = True

    _configured = True

def get_logger(name:str)->logging.Logger:
    return logging.getLogger(name)