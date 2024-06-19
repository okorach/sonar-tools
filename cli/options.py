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

import os
import sys
import random
import argparse

import sonar.logging as log
from sonar import errcodes, version, utilities

OPT_URL = "url"
OPT_VERBOSE = "verbosity"
OPT_SKIP_VERSION_CHECK = "skipVersionCheck"

OPT_ORGANIZATION = "organization"
OPT_MODE = "mode"
DRY_RUN = "dryrun"
CONFIRM = "confirm"
BATCH = "batch"
RUN_MODE = DRY_RUN

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

__DEFAULT_CSV_SEPARATOR = ","

FORMAT = "format"


def parse_and_check(parser: argparse.ArgumentParser, logger_name: str = None, verify_token: bool = True) -> argparse.ArgumentParser:
    """Parses arguments, applies default settings and perform common environment checks"""
    try:
        args = parser.parse_args()
    except SystemExit:
        sys.exit(errcodes.ARGS_ERROR)

    kwargs = vars(args)
    log.set_logger(filename=kwargs[LOGFILE], logger_name=logger_name)
    log.set_debug_level(kwargs[OPT_VERBOSE])
    log.info("sonar-tools version %s", version.PACKAGE_VERSION)
    if "projectKeys" in kwargs:
        kwargs["projectKeys"] = utilities.csv_to_list(kwargs["projectKeys"])
    if "metricKeys" in kwargs:
        kwargs["metricKeys"] = utilities.csv_to_list(kwargs["metricKeys"])

    # Verify version randomly once every 10 runs
    if not kwargs[OPT_SKIP_VERSION_CHECK] and random.randrange(10) == 0:
        utilities.check_last_sonar_tools_version()

    if verify_token:
        utilities.check_token(args.token, utilities.is_sonarcloud_url(kwargs[OPT_URL]))
    return args


def set_url_arg(parser):
    parser.add_argument(f"--{WITH_URL}", action="store_true", default=False, required=False, help="Add objects URLs in report")
    return parser


def add_thread_arg(parser, action):
    parser.add_argument(f"--{NBR_THREADS}", required=False, type=int, default=8, help=f"Define number of threads for {action}, default 8")
    return parser


def add_branch_arg(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Adds the branch argument to the parser"""
    parser.add_argument(
        f"-{WITH_BRANCHES_SHORT}",
        f"--{WITH_BRANCHES}",
        required=False,
        action="store_true",
        help="Also extract desired information for branches",
    )
    return parser


def add_dateformat_arg(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
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


def add_url_arg(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Adds the option to export URL of objects"""
    parser.add_argument(
        f"--{WITH_URL}",
        required=False,
        default=False,
        action="store_true",
        help="Also list the URL of the objects",
    )
    return parser


def add_import_export_arg(parser: argparse.ArgumentParser, topic: str, import_opt: bool = True, export_opt: bool = True) -> argparse.ArgumentParser:
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


def set_common_args(desc: str) -> argparse.ArgumentParser:
    """Parses options common to all sonar-tools scripts"""
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        "-t",
        "--token",
        required=False,
        default=os.getenv("SONAR_TOKEN", None),
        help="""Token to authenticate to the source SonarQube, default is environment variable $SONAR_TOKEN
        - Unauthenticated usage is not possible""",
    )
    parser.add_argument(
        "-u",
        f"--{OPT_URL}",
        required=False,
        default=os.getenv("SONAR_HOST_URL", "http://localhost:9000"),
        help="""Root URL of the source SonarQube or SonarCloud server,
        default is environment variable $SONAR_HOST_URL or http://localhost:9000 if not set""",
    )
    parser.add_argument(
        "-o",
        f"--{OPT_ORGANIZATION}",
        required=False,
        help="SonarCloud organization when using sonar-tools with SonarCloud",
    )
    parser.add_argument(
        "-v",
        f"--{OPT_VERBOSE}",
        required=False,
        choices=["WARN", "INFO", "DEBUG"],
        default="INFO",
        help="Logging verbosity level",
    )
    parser.add_argument(
        "-c",
        "--clientCert",
        required=False,
        default=None,
        help="Optional client certificate file (as .pem file)",
    )
    parser.add_argument(
        "--httpTimeout",
        required=False,
        default=10,
        help="HTTP timeout for requests to SonarQube, 10s by default",
    )
    parser.add_argument(
        f"--{OPT_SKIP_VERSION_CHECK}",
        required=False,
        default=False,
        action="store_true",
        help="Prevents sonar-tools to occasionnally check from more recent version",
    )
    parser.add_argument(
        f"-{LOGFILE_SHORT}",
        f"--{LOGFILE}",
        required=False,
        default=None,
        help="Define location of logfile, logs are only sent to stderr if not set",
    )
    return parser


def set_key_arg(parser):
    parser.add_argument(
        "-k",
        "--projectKeys",
        "--keys",
        "--projectKey",
        required=False,
        help="Commas separated keys of the objects to select",
    )
    return parser


def set_target_sonar_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    """Sets the target SonarQube CLI options"""
    parser.add_argument(
        "-U",
        "--urlTarget",
        required=False,
        help="Root URL of the target SonarQube server",
    )
    parser.add_argument(
        "-T",
        "--tokenTarget",
        required=False,
        help="Token to authenticate to target SonarQube - Unauthenticated usage is not possible",
    )
    return parser


def set_output_file_args(
    parser: argparse.ArgumentParser, json_fmt: bool = True, csv_fmt: bool = True, sarif_fmt: bool = False
) -> argparse.ArgumentParser:
    """Sets the output file CLI options"""
    parser.add_argument(
        "-f",
        "--file",
        required=False,
        default=None,
        help="Output file for the report, stdout by default",
    )
    fmt_choice = []
    if csv_fmt:
        fmt_choice.append("csv")
    if json_fmt:
        fmt_choice.append("json")
    if sarif_fmt:
        fmt_choice.append("sarif")
    if json_fmt and csv_fmt:
        parser.add_argument(
            f"--{FORMAT}",
            choices=fmt_choice,
            required=False,
            default=None,
            help="Output format for generated report.\nIf not specified, it is the output file extension if json or csv, then csv by default",
        )
    if csv_fmt:
        parser.add_argument(
            f"--{CSV_SEPARATOR}",
            required=False,
            default=__DEFAULT_CSV_SEPARATOR,
            help=f"CSV separator (for CSV output), default '{__DEFAULT_CSV_SEPARATOR}'",
        )
    return parser


def set_what(parser: argparse.ArgumentParser, what_list: list[str], operation: str) -> argparse.ArgumentParser:
    """Sets the argumant to select what to audit or to export as config"""
    parser.add_argument(
        "-w",
        "--what",
        required=False,
        default="",
        help=f"What to {operation} {','.join(what_list)}",
    )
    return parser
