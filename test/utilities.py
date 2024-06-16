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
from sonar import platform

LATEST = "http://localhost:9999"
LTA = "http://localhost:9000"

CSV_FILE = "temp.csv"
JSON_FILE = "temp.json"

STD_OPTS = ["-u", os.getenv("SONAR_HOST_URL"), "-t", os.getenv("SONAR_TOKEN_ADMIN_USER")]

SONARQUBE = platform.Platform(url=os.getenv("SONAR_HOST_URL"), token=os.getenv("SONAR_TOKEN_ADMIN_USER"))


def file_not_empty(file: str) -> bool:
    """Returns whether a file exists and is not empty"""
    if not os.path.isfile(file):
        return False
    return os.stat(file).st_size > 0


def clean(file: str) -> None:
    """Deletes a file if exists"""
    try:
        os.remove(file)
    except FileNotFoundError:
        pass
