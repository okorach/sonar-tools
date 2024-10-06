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
import datetime

from sonar import platform
import cli.options as opt

LATEST = "http://localhost:10000"
LATEST_TEST = "http://localhost:10020"
LTA = "http://localhost:9000"
LATEST_CE = "http://localhost:8000"

CSV_FILE = "temp.csv"
JSON_FILE = "temp.json"
YAML_FILE = "temp.yaml"

STD_OPTS = [f"-{opt.URL_SHORT}", os.getenv("SONAR_HOST_URL"), f"-{opt.TOKEN_SHORT}", os.getenv("SONAR_TOKEN_ADMIN_USER")]
TEST_OPTS = [f"-{opt.URL_SHORT}", LATEST_TEST, f"-{opt.TOKEN_SHORT}", os.getenv("SONAR_TOKEN_ADMIN_USER")]
CE_OPTS = [f"-{opt.URL_SHORT}", LATEST_CE, f"-{opt.TOKEN_SHORT}", os.getenv("SONAR_TOKEN_ADMIN_USER")]

SQ = platform.Platform(url=os.getenv("SONAR_HOST_URL"), token=os.getenv("SONAR_TOKEN_ADMIN_USER"))
SC = platform.Platform(url="https://sonarcloud.io", token=os.getenv("SONAR_TOKEN_SONARCLOUD"))
TEST_SQ = platform.Platform(url=LATEST_TEST, token=os.getenv("SONAR_TOKEN_ADMIN_USER"))


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


def clean(*files: str) -> None:
    """Deletes a list of file if they exists"""
    for file in files:
        try:
            os.remove(file)
        except FileNotFoundError:
            pass


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
