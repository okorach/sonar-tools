#
# sonar-tools
# Copyright (C) 2024-2025 Olivier Korach
# mailto:olivier.korach AT gmail DOT com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
""" sonar-tools logging module """

import logging

CRITICAL = logging.CRITICAL
FATAL = logging.FATAL
ERROR = logging.ERROR
WARNING = logging.WARNING
WARN = logging.WARN
INFO = logging.INFO
DEBUG = logging.DEBUG
NOTSET = logging.NOTSET

__DEFAULT_LOGGER_NAME = "sonar-tools"
__LOGGER = logging.getLogger(__DEFAULT_LOGGER_NAME)
__DEFAULT_LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)-7s | %(threadName)-15s | %(message)s"
__FORMATTER = logging.Formatter(__DEFAULT_LOG_FORMAT)

ISO_DATE_FORMAT = "%04d-%02d-%02d"
SQ_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
SQ_DATE_FORMAT = "%Y-%m-%d"
SQ_TIME_FORMAT = "%H:%M:%S"


def set_logger(filename: str = None, logger_name: str = None) -> None:
    """Sets the logging file (stderr only by default) and the logger name"""
    global __LOGGER
    if logger_name is not None:
        __LOGGER = logging.getLogger(logger_name)
    if filename is not None:
        fh = logging.FileHandler(filename)
        __LOGGER.addHandler(fh)
        fh.setFormatter(__FORMATTER)
    ch = logging.StreamHandler()
    __LOGGER.addHandler(ch)
    ch.setFormatter(__FORMATTER)
    __LOGGER.addHandler(ch)


def get_logging_level(level: str) -> int:
    """Returns the int logging level corresponding to the input string"""
    if level == "DEBUG":
        lvl = logging.DEBUG
    elif level in ("WARN", "WARNING"):
        lvl = logging.WARNING
    elif level == "ERROR":
        lvl = logging.ERROR
    elif level == "CRITICAL":
        lvl = logging.CRITICAL
    else:
        lvl = logging.INFO
    return lvl


def debug(*params) -> None:
    """DEBUG log"""
    __LOGGER.debug(*params)


def info(*params) -> None:
    """INFO log"""
    __LOGGER.info(*params)


def warning(*params) -> None:
    """WARNING log"""
    __LOGGER.warning(*params)


def warn(*params) -> None:
    """WARNING log"""
    warning(*params)


def error(*params) -> None:
    """ERROR log"""
    __LOGGER.error(*params)


def critical(*params) -> None:
    """CRITICAL log"""
    __LOGGER.critical(*params)


def fatal(*params) -> None:
    """FATAL log"""
    __LOGGER.fatal(*params)


def log(*params) -> None:
    """Log with variable log level"""
    __LOGGER.log(*params)


def set_debug_level(level: str) -> None:
    """Sets the logging level"""
    __LOGGER.setLevel(get_logging_level(level))
    __LOGGER.info("Set logging level to %s", level)


def get_level() -> None:
    """Returns the logging level"""
    return __LOGGER.level
