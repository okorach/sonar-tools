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

TARGET_PLATFORM = "http://localhost:9000"
TARGET_TOKEN = getenv("SONAR_TOKEN_9_ADMIN_USER")

ISSUE_FP = "AZrWSZgXG2ojjjMGNBfu"
ISSUE_FP_NBR_CHANGELOGS = 20
ISSUE_FP_CHANGELOG_DATE = datetime(2025, 12, 1)

ISSUE_ACCEPTED = "AZrWSZgXG2ojjjMGNBfw"

NBR_PROJECTS = 60

ADMIN_USER = "admin"