#
# sonar-tools
# Copyright (C) 2022 Olivier Korach
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

    Cmd line options

"""

WITH_URL = "withURL"
WITH_NAME = "withName"
WITH_LAST_ANALYSIS = "withLastAnalysis"
WITH_BRANCHES = "withBranches"

CSV_SEPARATOR = "csvSeparator"
FORMAT = "format"

DEFAULT = "__default__"

ERR_SONAR_API_AUTHENTICATION = 1
ERR_SONAR_API_AUTHORIZATION = 2
ERR_SONAR_API = 3
ERR_TOKEN_MISSING = 4

ERR_NO_SUCH_PROJECT_KEY = 5
ERR_WRONG_SEARCH_CRITERIA = 6
ERR_UNSUPPORTED_OPERATION = 7
ERR_RULES_LOADING_FAILED = 8
ERR_SIF_AUDIT_ERROR = 9

ERR_ARGS_ERROR = 10
