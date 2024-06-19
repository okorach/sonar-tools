#
# sonar-tools
# Copyright (C) 2024 Olivier Korach
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
""" sonar-tools logger """

import logging

__DEFAULT_LOGGER_NAME = "sonar-tools"
__DEFAULT_LOGFILE = f"{__DEFAULT_LOGGER_NAME}.log"
__DEFAULT_LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)-7s | %(threadName)-15s | %(message)s"
__FORMATTER = logging.Formatter(__DEFAULT_LOG_FORMAT)

ISO_DATE_FORMAT = "%04d-%02d-%02d"
SQ_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
SQ_DATE_FORMAT = "%Y-%m-%d"
SQ_TIME_FORMAT = "%H:%M:%S"


# By default log as sonar-tools on stderr only
logger = logging.getLogger(__DEFAULT_LOGGER_NAME)


def set_logger(filename: str = None, logger_name: str = None) -> None:
    """Sets the logging file (stderr only by default) and the logger name"""
    global logger
    if logger_name is not None:
        logger = logging.getLogger(logger_name)
    if filename is not None:
        fh = logging.FileHandler(filename)
        logger.addHandler(fh)
        fh.setFormatter(__FORMATTER)
    ch = logging.StreamHandler()
    logger.addHandler(ch)
    ch.setFormatter(__FORMATTER)
    logger.addHandler(ch)


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
    logger.debug(*params)


def info(*params) -> None:
    """INFO log"""
    logger.info(*params)


def warning(*params) -> None:
    """WARNING log"""
    logger.warning(*params)


def warn(*params) -> None:
    """WARNING log"""
    warning(*params)


def error(*params) -> None:
    """ERROR log"""
    logger.error(*params)


def critical(*params) -> None:
    """CRITICAL log"""
    logger.critical(*params)


def log(*params) -> None:
    """Log with variable log level"""
    logger.log(*params)


def set_debug_level(level: str) -> None:
    """Sets the logging level"""
    logger.setLevel(get_logging_level(level))
    logger.info("Set logging level to %s", level)
