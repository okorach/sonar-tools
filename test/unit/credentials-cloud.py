#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2026 Olivier Korach
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

from os import getenv
from datetime import datetime

TARGET_PLATFORM = "https://sonarcloud.io"
TARGET_TOKEN = getenv("SONAR_TOKEN_SONARCLOUD")

ISSUE_FP = "6e7537bf-fccc-4aab-962e-e2f924d44728"
ISSUE_FP_NBR_CHANGELOGS = 16

ISSUE_ACCEPTED = "c99ac40e-c2c5-43ef-bcc5-4cd077d1052f"

CHLOG_DATE = datetime(2025, 10, 12)

ISSUE_W_MULTIPLE_CHANGELOGS = "6ae41c3b-c3d2-422f-a505-d355e7b0a268"
ISSUE_W_MULTIPLE_CHANGELOGS_DATE = "2019-09-21"

NBR_PROJECTS = 8

ADMIN_USER = "okorach@github"
