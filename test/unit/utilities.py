#!/usr/bin/env python3
#
# sonar-tools tests
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

"""
    test utilities
"""

import os
import sys
import datetime
import re
from typing import Optional, Union
from unittest.mock import patch
import pytest

import credentials as creds
from sonar import errcodes, logging
from sonar import utilities as util
from sonar import platform
import cli.options as opt

TEST_LOGFILE = "pytest.log"
LOGGER_COUNT = 0
FILES_ROOT = "test/files/"

LATEST = "http://localhost:10000"
LTA = "http://localhost:8000"
LTS = LTA

LATEST_TEST = "http://localhost:10010"

CB = "http://localhost:7000"

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

CE_OPTS = [f"-{opt.URL_SHORT}", CB, f"-{opt.TOKEN_SHORT}", os.getenv("SONAR_TOKEN_ADMIN_USER")]

SC_OPTS = f'--{opt.URL} https://sonarcloud.io --{opt.TOKEN} {os.getenv("SONAR_TOKEN_SONARCLOUD")} --{opt.ORG} okorach'

SQ = platform.Platform(url=creds.TARGET_PLATFORM, token=creds.TARGET_TOKEN)
SC = platform.Platform(url="https://sonarcloud.io", token=os.getenv("SONAR_TOKEN_SONARCLOUD"), org="okorach")
TEST_SQ = platform.Platform(url=LATEST_TEST, token=os.getenv("SONAR_TOKEN_ADMIN_USER"))

TAGS = ["foo", "bar"]

SONAR_WAY = "Sonar way"


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
    args = __split_args(string_arguments)
    for option in (f"-{opt.REPORT_FILE_SHORT}", f"--{opt.REPORT_FILE}"):
        try:
            return args[args.index(option) + 1], args
        except ValueError:
            pass
    return None, args


def __split_args(string_arguments: str) -> list[str]:
    return [s.strip('"') for s in re.findall(r'(?:[^\s\*"]|"(?:\\.|[^"])*")+', string_arguments)]


def __get_option_index(args: Union[str, list], option: str) -> Optional[str]:
    if isinstance(args, str):
        args = __split_args(args)
    return args.index(option) + 1


def __get_redacted_cmd(string_arguments: str) -> str:
    """Gets a cmd line and redacts the token"""
    args = __split_args(string_arguments)
    for option in (f"-{opt.TOKEN_SHORT}", f"--{opt.TOKEN}", "-T", "--tokenTarget"):
        try:
            ndx = __get_option_index(args, option)
            args[ndx] = util.redacted_token(args[ndx])
        except ValueError:
            pass
    return " ".join(args)


def run_cmd(func: callable, arguments: str, expected_code: int) -> Optional[str]:
    """Runs a sonar-tools command, verifies it raises the right exception, and returns the expected code"""
    logging.info("RUNNING: %s", __get_redacted_cmd(arguments))
    file, args = __get_args_and_file(arguments)
    clean(file)
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
