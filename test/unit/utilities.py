#!/usr/bin/env python3
#
# sonar-tools tests
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

"""
    test utilities
"""

import os
import sys
import datetime
from typing import Optional
from unittest.mock import patch
import pytest

import credentials as creds
from sonar import errcodes, logging
from sonar import platform
import cli.options as opt

TEST_LOGFILE = "pytest.log"
LOGGER_COUNT = 0

LATEST = "http://localhost:10000"
LATEST_TEST = "http://localhost:10020"
LTA = "http://localhost:9000"
LATEST_CE = "http://localhost:8000"

TARGET_PLATFORM = LATEST

CSV_FILE = f"temp.{os.getpid()}.csv"
JSON_FILE = f"temp.{os.getpid()}.json"
YAML_FILE = f"temp.{os.getpid()}.yaml"

PROJECT_1 = "okorach_sonar-tools"
PROJECT_2 = "project1"
LIVE_PROJECT = PROJECT_1
NON_EXISTING_KEY = "non-existing"

TEST_KEY = "TEST"
EXISTING_QG = TEST_KEY
EXISTING_PROJECT = TEST_KEY
EXISTING_APP = TEST_KEY
EXISTING_PORTFOLIO = TEST_KEY
TEMP_KEY = "TEMP"
TEMP_KEY_2 = "TEMP2"
TEMP_KEY_3 = "TEMP3"
TEMP_NAME = "Temp Name"

STD_OPTS = [f"-{opt.URL_SHORT}", creds.TARGET_PLATFORM, f"-{opt.TOKEN_SHORT}", creds.TARGET_TOKEN]
SQS_OPTS = " ".join(STD_OPTS)

TEST_OPTS = [f"-{opt.URL_SHORT}", LATEST_TEST, f"-{opt.TOKEN_SHORT}", os.getenv("SONAR_TOKEN_ADMIN_USER")]
SQS_TEST_OPTS = " ".join(TEST_OPTS)

CE_OPTS = [f"-{opt.URL_SHORT}", LATEST_CE, f"-{opt.TOKEN_SHORT}", os.getenv("SONAR_TOKEN_ADMIN_USER")]

SC_OPTS = f'--{opt.URL} https://sonarcloud.io --{opt.TOKEN} {os.getenv("SONAR_TOKEN_SONARCLOUD")} --{opt.ORG} okorach'

SQ = platform.Platform(url=creds.TARGET_PLATFORM, token=creds.TARGET_TOKEN)
SC = platform.Platform(url="https://sonarcloud.io", token=os.getenv("SONAR_TOKEN_SONARCLOUD"))
TEST_SQ = platform.Platform(url=LATEST_TEST, token=os.getenv("SONAR_TOKEN_ADMIN_USER"))

TAGS = ["foo", "bar"]


def clean(*files: str) -> None:
    """Deletes a list of file if they exists"""
    for file in files:
        try:
            os.remove(file)
        except FileNotFoundError:
            pass


def file_empty(file: str) -> bool:
    """Returns whether a file exists and is empty"""
    if not os.path.isfile(file):
        return False
    return os.stat(file).st_size == 0


def file_not_empty(file: str) -> bool:
    """Returns whether a file exists and is not empty"""
    if not os.path.isfile(file):
        return False
    return os.stat(file).st_size > 0


def file_contains(file: str, string: str) -> bool:
    """Returns whether a file contains a given string"""
    if not os.path.isfile(file):
        return False
    with open(file=file, mode="r", encoding="utf-8") as fh:
        content = fh.read()
    return string in content


def is_datetime(value: str) -> bool:
    """Checks if a string is a date + time"""
    try:
        _ = datetime.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return False
    return True


def is_integer(value: str) -> bool:
    """Returns whether a string contains an integer"""
    return isinstance(int(value), int)


def is_url(value: str) -> bool:
    """Returns whether a string contains an URL"""
    return value.startswith("http")


def __get_args_and_file(string_arguments: str) -> tuple[Optional[str], list[str]]:
    """Gets the list arguments and output file of a sonar-tools cmd"""
    args = string_arguments.split(" ")
    try:
        file = args[args.index(f"--{opt.REPORT_FILE}") + 1]
    except ValueError:
        try:
            file = args[args.index(f"-{opt.REPORT_FILE_SHORT}") + 1]
        except ValueError:
            file = None
    return file, args


def run_cmd(func: callable, arguments: str, expected_code: int) -> Optional[str]:
    """Runs a sonar-tools command, verifies it raises the right exception, and returns the expected code"""
    logging.info("RUNNING: %s", arguments)
    file, args = __get_args_and_file(arguments)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", args):
            func()
    assert int(str(e.value)) == expected_code
    return file


def run_success_cmd(func: callable, arguments: str) -> None:
    """Runs a command that's suppose to end in success"""
    file = run_cmd(func, arguments, errcodes.OK)
    if file:
        assert file_not_empty(file)


def run_failed_cmd(func: callable, arguments: str, expected_code: int) -> None:
    """Runs a command that's suppose to end in failure"""
    file = run_cmd(func, arguments, expected_code)
    if file:
        assert not os.path.isfile(file)


def start_logging(level: str = "DEBUG") -> None:
    """start_logging"""
    global LOGGER_COUNT
    if LOGGER_COUNT == 0:
        logging.set_logger(TEST_LOGFILE)
        logging.set_debug_level(level)
        LOGGER_COUNT = 1
