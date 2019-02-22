"""
_module_: `mast.logging`

This module provides two major objects:

1. `make_logger`: A function which will return a `logging.Logger`
instance which is configured with a
`logging.handlers.TimedRotatingFileHandler` handler. See the
functions documentation for more details
2. `logged`: A decorator which will log the execution of a function
including the arguments passed in along with the return value. See
[the decorators documentation](#logged) for more details.

Usage:

    :::python
    from mast.logging import make_logger, logged

    logger = make_logger("my_module")
    logger.info("Informational message")

    @logged("my_module.function_1")
    def function_1(args):
        do_something(args)

    function_1("some_value")
"""


import logging
from functools import wraps
from mast.timestamp import Timestamp
from logging.handlers import RotatingFileHandler
from mast.config import get_configs_dict
import getpass
import os

mast_home = os.environ["MAST_HOME"]
__version__ = "{}-0".format(os.environ["MAST_VERSION"])

config = get_configs_dict()
config = config["logging.conf"]
level = int(config["logging"]["level"])
max_bytes = config["logging"]["max_bytes"]
backup_count = int(config["logging"]["backup_count"])
delay = bool(config["logging"]["delay"])
propagate = bool(config["logging"]["propagate"])


filemode = "w"
_format = "; ".join((
    "'level'='%(levelname)s'",
    "'datetime'='%(asctime)s'",
    "'thread'='%(thread)d'",
    "'module'='%(module)s'",
    "'line'='%(lineno)d'",
    "'message'='%(message)s'"))


def make_logger(
        name,
        level=level,
        fmt=_format,
        max_bytes=max_bytes,
        backup_count=backup_count,
        delay=delay,
        propagate=propagate,
    ):
    """
    _function_: `mast.logging.make_logger(name, level=level, fmt=_format, filename=None, when=unit, interval=interval, propagate=propagate, backup_count=backup_count)`

    Returns an instance of logging.Logger configured with
    a [logging.handlers.TimedRotatingFileHandler](https://docs.python.org/2/library/logging.handlers.html#timedrotatingfilehandler)
    handler.

    Arguments passed to this function determine the format,
    level, filename, time unit, interval, backup count and
    whether to propagate messages to parent loggers (defined
    by dot seperated heirarchy ie in `mast.datapower`,
    `datapower` is a logger with a parent logger of mast).

    Parameters:

    * `name`: Required. the name of the logger instance. This follows
    conventions mentioned [here](https://docs.python.org/2/library/logging.html#logger-objects)
    * `level`: The logging level to listen for. Accepts an `int` or
    one of the logging modules convenience constants defined
    [here](https://docs.python.org/2/library/logging.html#logging-levels)
    * `fmt`: The format of the log message, see
    [here](https://docs.python.org/2/library/logging.html#formatter-objects)
    and [here](https://docs.python.org/2/library/logging.html#logrecord-attributes)
    for more details
    * `filename`: The filename to log to. Defaults to the name of the logger
    appended with `.log` in the `$MAST_HOME/var/log` directory or
    `$MAST_HOME/var/log/mastd` directory if running as `mastd`
    * `when`: The time unit to use for rolling over the log file
    as detailed [here](https://docs.python.org/2/library/logging.handlers.html#timedrotatingfilehandler)
    * `interval`: The number of time units to wait before rolling the
    log files as detailed [here](https://docs.python.org/2/library/logging.handlers.html#timedrotatingfilehandler)
    * `propagate`: Whether to propagate log messages up the ancestry chain
    (ie. if you have a logger `mast.datapower`, and propagate is set to
    `False` messages sent to the this logger will not be propagated to the
    `mast` logger). See [here](https://docs.python.org/2/library/logging.html#logging.Logger.propagate)
    for more details.
    * `backup_count`: The number of "rolled" log files to keep, see
    [here](https://docs.python.org/2/library/logging.handlers.html#timedrotatingfilehandler)
    for more details.

    Usage:

        :::python
        from mast.logging import make_logger

        logger = make_logger("my_module")
        logger.info("informational message")
        logger.debug("debug message")
    """
    t = Timestamp()
    _logger = logging.getLogger(name)
    if _logger.handlers:
        if len(_logger.handlers) >= 1:
            return _logger

    _logger.setLevel(level)
    _formatter = logging.Formatter(fmt)

    pid = os.getpid()
    directory = os.path.join(
        mast_home,
        "var",
        "log",
        getpass.getuser(),
        "{}-{}".format(t.timestamp, str(pid)),
    )
    filename = os.path.join(
        directory,
        "{}-{}.log".format(name, t.timestamp),
    )
    if not os.path.exists(directory):
        os.makedirs(directory)
    _handler = RotatingFileHandler(
        filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        delay=delay,
    )
    _handler.setFormatter(_formatter)
    _handler.setLevel(level)
    _logger.addHandler(_handler)
    _logger.propagate = propagate
    return _logger


def _format_args(args):
    """
    _function_: `mast.logging._format_args(args)`

    Used by `mast.logging.logged` to format the arguments passed to
    the decorated function.

    Parameters:

    * `args`: The arguments passed to the decorated function. They will
    coerced into a `str`, surrounded by single quotes and seperated by
    a comma.
    """
    return ", ".join(("'" + str(arg) + "'" for arg in args))


def _format_kwargs(kwargs):
    """
    _function_: `mast.logging._format_kwargs(kwargs)`

    Used by `mast.logging.logged` to format the arguments passed to
    the decorated function.

    Parameters:

    * `kwargs`: The keyword-arguments passed to the decorated function. They
    will be represented like `'key'='value',`
    """
    return str(kwargs).replace("{", "").replace("}", "").replace(": ", "=")


def _format_arguments(args, kwargs):
    """
    _function_: `mast.logging._format_arguments(args, kwargs)`

    Used by `mast.logging.logged` to format the arguments and
    keyword-arguments passed to the decorated function.

    Parameters:

    * `args`: The arguments passed to the decorated function. They will
    coerced into a `str`, surrounded by single quotes and seperated by
    a comma.
    * `kwargs`: The keyword-arguments passed to the decorated function. They
    will be represented like `'key'='value',`
    """
    arguments = ""
    if args:
        arguments += _format_args(args)
    if kwargs:
        if args:
            arguments += ", "
        arguments += _format_kwargs(kwargs)
    return arguments

def _escape(string):
    """
    _function_: `mast.logging._escape(string)`

    Returns `string` with newlines removed and with single and double quotes
    replaced with `&apos;` and `&quot;` respectively.

    Parameters:

    * `string`: The string to escape
    """
    return string.replace(
        "\n", ""
    ).replace(
        "\r", ""
    ).replace(
        "'", "&apos;"
    ).replace(
        '"', "&quot;"
    )


def logged(name="mast"):
    """
    _function_: `mast.logging.logged(name="mast")`

    This function is a decorator which will log all calls to the
    decorated function along with any arguments passed in.

    Parameters:

    * `name`: The name of the logger to use. This will be used to
    construct the name of the log file as well.

    Usage:

        :::python
        from mast.logging import logged

        @logged("my_module.function_1")
        def function_1(args):
            do_something(args)

        function_1("some_value")
    """
    def _decorator(func):

        @wraps(func)
        def _wrapper(*args, **kwargs):
            logger = make_logger(name)
            arguments = _format_arguments(args, kwargs)
            logger.info(
                "Attempting to execute {}({})".format(
                    func.__name__, arguments))
            try:
                result = func(*args, **kwargs)
            except:
                logger.exception(
                    "An unhandled exception occurred while "
                    "attempting to execute {}({})".format(
                        func.__name__,
                        arguments
                    )
                )
                raise
            _result = _escape(repr(result))
            msg = "Finished execution of {}({}). Result: {}".format(
                func.__name__,
                arguments,
                _result
            )
            logger.info(msg)
            return result
        return _wrapper
    return _decorator

logger = make_logger("mast")
dp_logger = make_logger("DataPower")
