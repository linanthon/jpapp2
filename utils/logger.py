import logging
import inspect

_loggers = {}

def get_logger(name: str = None):
    if name is None:
        # Auto-detect caller's filename if not provided
        frame = inspect.stack()[1]
        name = os.path.splitext(os.path.basename(frame.filename))[0]

    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(f"%(asctime)s [%(levelname)s] [{name}] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    _loggers[name] = logger
    return logger