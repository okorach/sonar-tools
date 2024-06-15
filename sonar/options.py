#
# sonar-tools
# Copyright (C) 2022-2024 Olivier Korach
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

# Command line options

WITH_URL = "withURL"
WITH_NAME = "withName"
WITH_LAST_ANALYSIS = "withLastAnalysis"

WITH_BRANCHES_SHORT = "b"
WITH_BRANCHES = "withBranches"

OUTPUTFILE_SHORT = "f"
OUTPUTFILE = "file"

LOGFILE_SHORT = "l"
LOGFILE = "logfile"

WITH_HISTORY = "history"
NBR_THREADS = "threads"

DATES_WITHOUT_TIME_SHORT = "d"
DATES_WITHOUT_TIME = "datesWithoutTime"

WHAT_SETTINGS = "settings"
WHAT_USERS = "users"
WHAT_GROUPS = "groups"
WHAT_GATES = "qualitygates"
WHAT_RULES = "rules"
WHAT_PROFILES = "qualityprofiles"
WHAT_PROJECTS = "projects"
WHAT_APPS = "applications"
WHAT_PORTFOLIOS = "portfolios"
WHAT_AUDITABLE = [WHAT_SETTINGS, WHAT_USERS, WHAT_GROUPS, WHAT_GATES, WHAT_PROFILES, WHAT_PROJECTS, WHAT_APPS, WHAT_PORTFOLIOS]

CSV_SEPARATOR = "csvSeparator"
FORMAT = "format"

DEFAULT = "__default__"

# Sonar Tools error codes

ERR_SONAR_API_AUTHENTICATION = 1
ERR_SONAR_API_AUTHORIZATION = 2
ERR_SONAR_API = 3
ERR_TOKEN_MISSING = 4

ERR_NO_SUCH_KEY = 5
ERR_WRONG_SEARCH_CRITERIA = 6
ERR_UNSUPPORTED_OPERATION = 7
ERR_RULES_LOADING_FAILED = 8
ERR_SIF_AUDIT_ERROR = 9

ERR_ARGS_ERROR = 10
# if a global analysis or project analysis token is provided
ERR_TOKEN_NOT_SUITED = 11

# HTTP request timeout
ERR_REQUEST_TIMEOUT = 12


def set_url_arg(parser):
    parser.add_argument(f"--{WITH_URL}", action="store_true", default=False, required=False, help="Add objects URLs in report")
    return parser


def add_thread_arg(parser, action):
    parser.add_argument(f"--{NBR_THREADS}", required=False, type=int, default=8, help=f"Define number of threads for {action}, default 8")
    return parser


def add_branch_arg(parser: object) -> object:
    """Adds the branch argument to the parser"""
    parser.add_argument(
        f"-{WITH_BRANCHES_SHORT}",
        f"--{WITH_BRANCHES}",
        required=False,
        action="store_true",
        help="Also extract desired information for branches",
    )
    return parser


def add_dateformat_arg(parser: object) -> object:
    """Adds the date format argument to the parser"""
    parser.add_argument(
        f"-{DATES_WITHOUT_TIME_SHORT}",
        f"--{DATES_WITHOUT_TIME}",
        action="store_true",
        default=False,
        required=False,
        help="Reports timestamps only with date, not time",
    )
    return parser


def add_url_arg(parser: object) -> object:
    """Adds the option to export URL of objects"""
    parser.add_argument(
        f"--{WITH_URL}",
        required=False,
        default=False,
        action="store_true",
        help="Also list the URL of the objects",
    )
    return parser


def add_import_export_arg(parser: object, topic: str, import_opt: bool = True, export_opt: bool = True) -> object:
    """Adds the CLI params for export/import"""
    group = parser.add_mutually_exclusive_group()
    if export_opt:
        msg = ""
        if import_opt:
            msg = " (exclusive of --import)"
        group.add_argument("-e", "--export", required=False, default=False, action="store_true", help=f"To export {topic}{msg}")
    if import_opt:
        msg = ""
        if export_opt:
            msg = " (exclusive of --export)"
        group.add_argument("-i", "--import", required=False, default=False, action="store_true", help=f"To import {topic}{msg}")
    return parser
