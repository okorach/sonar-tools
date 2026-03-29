#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2024-2026 Olivier Korach
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

import os
import sys
from datetime import datetime

_PLATFORMS = {
    "latest": {
        "TARGET_PLATFORM": "http://localhost:10000",
        "TARGET_TOKEN": os.getenv("SONAR_TOKEN_LATEST_ADMIN_USER"),
        "ORGANIZATION": None,
        "ISSUE_FP": "64e848c0-d5f4-402e-8c80-af6536041b5e",
        "ISSUE_FP_NBR_CHANGELOGS": 15,
        "ISSUE_FP_CHANGELOG_DATE": datetime(2025, 11, 2),
        "ISSUE_ACCEPTED": "b6637cb9-3be1-4160-9d08-84622a818ff6",
        "NBR_PROJECTS": 70,
        "ADMIN_USER": "admin",
        "ADMIN_GROUP": "sonar-administrators",
        "DEFAULT_USER_GROUP": "sonar-users",
    },
    "20261": {
        "TARGET_PLATFORM": "http://localhost:20261",
        "TARGET_TOKEN": os.getenv("SONAR_TOKEN_LATEST_ADMIN_USER"),
        "ORGANIZATION": None,
        "ISSUE_FP": "64e848c0-d5f4-402e-8c80-af6536041b5e",
        "ISSUE_FP_NBR_CHANGELOGS": 15,
        "ISSUE_FP_CHANGELOG_DATE": datetime(2025, 11, 2),
        "ISSUE_ACCEPTED": "b6637cb9-3be1-4160-9d08-84622a818ff6",
        "NBR_PROJECTS": 70,
        "ADMIN_USER": "admin",
        "ADMIN_GROUP": "sonar-administrators",
        "DEFAULT_USER_GROUP": "sonar-users",
    },
    "20251": {
        "TARGET_PLATFORM": "http://localhost:20251",
        "TARGET_TOKEN": os.getenv("SONAR_TOKEN_LTS_ADMIN_USER"),
        "ORGANIZATION": None,
        "ISSUE_FP": "1a5e12a2-3db8-41b3-9414-d7275371b6d3",
        "ISSUE_FP_NBR_CHANGELOGS": 31,
        "ISSUE_FP_CHANGELOG_DATE": datetime(2025, 10, 23),
        "ISSUE_ACCEPTED": "f2322714-7955-4134-923e-5353959b6e1f",
        "NBR_PROJECTS": 70,
        "ADMIN_USER": "admin",
        "ADMIN_GROUP": "sonar-administrators",
        "DEFAULT_USER_GROUP": "sonar-users",
    },
    "99": {
        "TARGET_PLATFORM": "http://localhost:9900",
        "TARGET_TOKEN": os.getenv("SONAR_TOKEN_99_ADMIN_USER"),
        "ORGANIZATION": None,
        "ISSUE_FP": "AZrWSZgXG2ojjjMGNBfu",
        "ISSUE_FP_NBR_CHANGELOGS": 20,
        "ISSUE_FP_CHANGELOG_DATE": datetime(2025, 12, 1),
        "ISSUE_ACCEPTED": "AZrWSZgXG2ojjjMGNBfw",
        "NBR_PROJECTS": 60,
        "ADMIN_USER": "admin",
        "ADMIN_GROUP": "sonar-administrators",
        "DEFAULT_USER_GROUP": "sonar-users",
    },
    "cb": {
        "TARGET_PLATFORM": "http://localhost:9000",
        "TARGET_TOKEN": os.getenv("SONAR_TOKEN_LATEST_ADMIN_USER"),
        "ORGANIZATION": None,
        "ISSUE_FP": "64e848c0-d5f4-402e-8c80-af6536041b5e",
        "ISSUE_FP_NBR_CHANGELOGS": 15,
        "ISSUE_FP_CHANGELOG_DATE": datetime(2025, 11, 2),
        "ISSUE_ACCEPTED": "e9eb08fe-bb53-443a-8a92-425589807c78",
        "NBR_PROJECTS": 70,
        "ADMIN_USER": "admin",
        "ADMIN_GROUP": "sonar-administrators",
        "DEFAULT_USER_GROUP": "sonar-users",
    },
    "cloud": {
        "TARGET_PLATFORM": "https://sonarcloud.io",
        "TARGET_TOKEN": os.getenv("SONAR_TOKEN_SONARCLOUD"),
        "ORGANIZATION": "okorach",
        "ISSUE_FP": "6e7537bf-fccc-4aab-962e-e2f924d44728",
        "ISSUE_FP_NBR_CHANGELOGS": 16,
        "ISSUE_FP_CHANGELOG_DATE": None,
        "ISSUE_ACCEPTED": "c99ac40e-c2c5-43ef-bcc5-4cd077d1052f",
        "NBR_PROJECTS": 8,
        "ADMIN_USER": "okorach@github",
        "ADMIN_GROUP": "Owners",
        "DEFAULT_USER_GROUP": "Members",
    },
}

_platform = os.environ.get("SONAR_TEST_PLATFORM", "latest")
if _platform not in _PLATFORMS:
    print(f"ERROR: Unknown test platform '{_platform}'. Valid platforms: {', '.join(_PLATFORMS)}", file=sys.stderr)
    sys.exit(1)

_cfg = _PLATFORMS[_platform]

TARGET_PLATFORM = _cfg["TARGET_PLATFORM"]
TARGET_TOKEN = _cfg["TARGET_TOKEN"]
ORGANIZATION = _cfg["ORGANIZATION"]
ISSUE_FP = _cfg["ISSUE_FP"]
ISSUE_FP_NBR_CHANGELOGS = _cfg["ISSUE_FP_NBR_CHANGELOGS"]
ISSUE_FP_CHANGELOG_DATE = _cfg["ISSUE_FP_CHANGELOG_DATE"]
ISSUE_ACCEPTED = _cfg["ISSUE_ACCEPTED"]
NBR_PROJECTS = _cfg["NBR_PROJECTS"]
ADMIN_USER = _cfg["ADMIN_USER"]
ADMIN_GROUP = _cfg["ADMIN_GROUP"]
DEFAULT_USER_GROUP = _cfg["DEFAULT_USER_GROUP"]
