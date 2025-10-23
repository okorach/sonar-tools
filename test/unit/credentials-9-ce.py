#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2025 Olivier Korach
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

TARGET_PLATFORM = "http://localhost:9002"
TARGET_TOKEN = getenv("SONAR_TOKEN_9_ADMIN_USER")

ISSUE_FP = "AZoM4DiBILwvqG5NHrW2"
ISSUE_FP_NBR_CHANGELOGS = 16
ISSUE_FP_CHANGELOG_DATE = datetime(2025, 10, 23)

ISSUE_ACCEPTED = "AZI6frkTuTfDeRt_hspx"
