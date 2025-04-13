#
# sonar-tools
# Copyright (C) 2022-2025 Olivier Korach
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
from argparse import ArgumentParser

import sonar.logging as log
from sonar import errcodes, version, utilities, exceptions

# Command line options

URL_SHORT = "u"
URL = "url"

URL_TARGET_SHORT = "U"
URL_TARGET = "urlTarget"

TOKEN_SHORT = "t"
TOKEN = "token"
TOKEN_TARGET_SHORT = "T"
TOKEN_TARGET = "tokenTarget"

ORG_SHORT = "o"
ORG = "organization"
ORG_TARGET_SHORT = "O"
ORG_TARGET = "organizationTarget"

VERBOSE_SHORT = "v"
VERBOSE = "verbosity"

HTTP_TIMEOUT = "httpTimeout"
SKIP_VERSION_CHECK = "skipVersionCheck"
CERT_SHORT = "c"
CERT = "clientCert"

REPORT_FILE_SHORT = "f"
REPORT_FILE = "file"

KEYS_SHORT = "k"
KEYS = "projectKeys"

EXPORT = "export"
EXPORT_SHORT = "e"
IMPORT = "import"
IMPORT_SHORT = "i"

METRIC_KEYS_SHORT = "m"
METRIC_KEYS = "metricKeys"

RESOLUTIONS = "resolutions"
SEVERITIES = "severities"
STATUSES = "statuses"
TYPES = "types"


NBR_THREADS = "threads"

BRANCHES_SHORT = "b"
BRANCHES = "branches"

TAGS = "tags"

PULL_REQUESTS_SHORT = "p"
PULL_REQUESTS = "pullRequests"

WITH_BRANCHES_SHORT = "b"
WITH_BRANCHES = "withBranches"

LANGUAGES = "languages"
QP = "qualityProfiles"

PORTFOLIOS = "portfolios"

FORMAT = "format"
WITH_URL = "withURL"
WITH_NAME_SHORT = "n"
WITH_NAME = "withName"
WITH_LAST_ANALYSIS_SHORT = "a"
WITH_LAST_ANALYSIS = "withLastAnalysis"

DATE_AFTER = "createdAfter"
DATE_BEFORE = "createdBefore"
DATES_WITHOUT_TIME_SHORT = "d"
DATES_WITHOUT_TIME = "datesWithoutTime"

LOGFILE_SHORT = "l"
LOGFILE = "logfile"

CSV_SEPARATOR = "csvSeparator"
USE_FINDINGS = "useFindings"

__DEFAULT_CSV_SEPARATOR = ","


OPT_MODE = "mode"
DRY_RUN = "dryrun"
CONFIRM = "confirm"
BATCH = "batch"
RUN_MODE = DRY_RUN

LANGUAGE_MAPPING = {
    "python": "py",
    "csharp": "cs",
    "c#": "cs",
    "javascript": "js",
    "typescript": "ts",
    "objective-c": "objc",
    "objectivec": "objc",
    "html": "web",
    "pl1": "pli",
}

WITH_HISTORY = "history"

WHAT = "what"
WHAT_SETTINGS = "settings"
WHAT_USERS = "users"
WHAT_GROUPS = "groups"
WHAT_GATES = "qualitygates"
WHAT_RULES = "rules"
WHAT_PROFILES = "qualityprofiles"
WHAT_PROJECTS = "projects"
WHAT_APPS = "applications"
WHAT_PORTFOLIOS = "portfolios"

MULTI_VALUED_OPTS = (KEYS, METRIC_KEYS, RESOLUTIONS, SEVERITIES, STATUSES, TYPES, TAGS, BRANCHES, PULL_REQUESTS, WHAT)

COMPONENT_TYPE = "compType"
COMPONENT_TYPES = ("projects", "apps", "portfolios")


class ArgumentsError(exceptions.SonarException):
    """
    Arguments error
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.errcode = errcodes.ARGS_ERROR


def __convert_args_to_lists(kwargs: dict[str, str]) -> dict[str, str]:
    """Converts arguments that may be CSV into lists"""
    for argname in MULTI_VALUED_OPTS:
        if argname in kwargs and kwargs[argname] is not None and len(kwargs[argname]) > 0:
            kwargs[argname] = utilities.csv_to_list(kwargs[argname])
    if kwargs.get(LANGUAGES, None) not in (None, ""):
        kwargs[LANGUAGES] = [lang.lower() for lang in utilities.csv_to_list(kwargs[LANGUAGES])]
        kwargs[LANGUAGES] = [LANGUAGE_MAPPING[lang] if lang in LANGUAGE_MAPPING else lang for lang in utilities.csv_to_list(kwargs[LANGUAGES])]
    return kwargs


def __check_file_writeable(file: str) -> None:
    """If not stdout, verifies that the chosen output file is writeable"""
    if file and file != "-":
        try:
            with open(file, mode="w", encoding="utf-8"):
                pass
        except (PermissionError, FileNotFoundError) as e:
            utilities.exit_fatal(f"Can't write to file '{file}': {e}", exit_code=errcodes.OS_ERROR)
        os.remove(file)


def parse_and_check(parser: ArgumentParser, logger_name: str = None, verify_token: bool = True, is_migration: bool = False) -> object:
    """Parses arguments, applies default settings and perform common environment checks"""
    try:
        args = parser.parse_args()
    except SystemExit:
        sys.exit(errcodes.ARGS_ERROR)

    kwargs = vars(args)
    log.set_logger(filename=kwargs[LOGFILE], logger_name=logger_name)
    log.set_debug_level(kwargs.pop(VERBOSE))

    tool = "sonar-migration" if is_migration else "sonar-tools"
    vers = version.MIGRATION_TOOL_VERSION if is_migration else version.PACKAGE_VERSION
    log.info("%s version %s", tool, vers)

    if os.getenv("IN_DOCKER", "No") == "Yes":
        kwargs[URL] = kwargs[URL].replace("http://localhost", "http://host.docker.internal")
    kwargs = __convert_args_to_lists(kwargs=kwargs)
    log.debug("CLI arguments = %s", utilities.json_dump(kwargs, redact_tokens=True))
    if not kwargs.get(IMPORT, False):
        __check_file_writeable(kwargs.get(REPORT_FILE, None))
    # Verify version randomly once every 10 runs
    if not kwargs[SKIP_VERSION_CHECK] and random.randrange(10) == 0:
        utilities.check_last_version(f"https://pypi.org/simple/{tool}")
    kwargs.pop(SKIP_VERSION_CHECK, None)
    if utilities.is_sonarcloud_url(kwargs[URL]) and kwargs[ORG] is None:
        raise ArgumentsError(f"Organization (-{ORG_SHORT}) option is mandatory for SonarCloud")
    if URL_TARGET in kwargs and utilities.is_sonarcloud_url(kwargs[URL_TARGET]) and kwargs[ORG_TARGET] is None:
        raise ArgumentsError(f"Organization (-{ORG_TARGET_SHORT}) option is mandatory for SonarCloud")
    if verify_token:
        utilities.check_token(args.token, utilities.is_sonarcloud_url(kwargs[URL]))
    return args


def set_url_arg(parser: ArgumentParser) -> ArgumentParser:
    """Adds the URL argument for CLI"""
    parser.add_argument(f"--{WITH_URL}", action="store_true", default=False, required=False, help="Add objects URLs in report")
    return parser


def add_thread_arg(parser: ArgumentParser, action: str) -> ArgumentParser:
    """Adds the threads argument for CLI"""
    parser.add_argument(f"--{NBR_THREADS}", required=False, type=int, default=8, help=f"Define number of threads for {action}, default 8")
    return parser


def add_branch_arg(parser: ArgumentParser) -> ArgumentParser:
    """Adds the branch argument to the parser"""
    parser.add_argument(
        f"-{WITH_BRANCHES_SHORT}",
        f"--{WITH_BRANCHES}",
        required=False,
        action="store_true",
        help="Also extract desired information for branches",
    )
    return parser


def add_dateformat_arg(parser: ArgumentParser) -> ArgumentParser:
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


def add_url_arg(parser: ArgumentParser) -> ArgumentParser:
    """Adds the option to export URL of objects"""
    parser.add_argument(
        f"--{WITH_URL}",
        required=False,
        default=False,
        action="store_true",
        help="Also list the URL of the objects",
    )
    return parser


def add_import_export_arg(parser: ArgumentParser, topic: str, import_opt: bool = True, export_opt: bool = True) -> ArgumentParser:
    """Adds the CLI params for export/import"""
    group = parser.add_mutually_exclusive_group()
    if export_opt:
        msg = ""
        if import_opt:
            msg = f" (exclusive of --{IMPORT})"
        group.add_argument(f"-{EXPORT_SHORT}", f"--{EXPORT}", required=False, default=False, action="store_true", help=f"To export {topic}{msg}")
    if import_opt:
        msg = ""
        if export_opt:
            msg = f" (exclusive of --{EXPORT})"
        group.add_argument(f"-{IMPORT_SHORT}", f"--{IMPORT}", required=False, default=False, action="store_true", help=f"To import {topic}{msg}")
    return parser


def set_common_args(desc: str) -> ArgumentParser:
    """Parses options common to all sonar-tools scripts"""
    parser = ArgumentParser(description=desc)
    parser.add_argument(
        f"-{TOKEN_SHORT}",
        f"--{TOKEN}",
        required=False,
        default=os.getenv("SONAR_TOKEN", None),
        help="""Token to authenticate to the source SonarQube, default is environment variable $SONAR_TOKEN
        - Unauthenticated usage is not possible""",
    )
    parser.add_argument(
        f"-{URL_SHORT}",
        f"--{URL}",
        required=False,
        default=os.getenv("SONAR_HOST_URL", "http://localhost:9000"),
        help="""Root URL of the source SonarQube or SonarCloud server,
        default is environment variable $SONAR_HOST_URL or http://localhost:9000 if not set""",
    )
    parser.add_argument(
        f"-{ORG_SHORT}",
        f"--{ORG}",
        required=False,
        help="SonarCloud organization when using sonar-tools with SonarCloud",
    )
    parser.add_argument(
        f"-{VERBOSE_SHORT}",
        f"--{VERBOSE}",
        required=False,
        choices=["WARN", "INFO", "DEBUG"],
        default="INFO",
        help="Logging verbosity level",
    )
    parser.add_argument(
        f"-{CERT_SHORT}",
        f"--{CERT}",
        required=False,
        default=None,
        help="Optional client certificate file (as .pem file)",
    )
    parser.add_argument(
        f"--{HTTP_TIMEOUT}",
        required=False,
        default=10,
        help="HTTP timeout for requests to SonarQube, 10 by default (in seconds)",
    )
    parser.add_argument(
        f"--{SKIP_VERSION_CHECK}",
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


def set_key_arg(parser: ArgumentParser) -> ArgumentParser:
    """Adds the cmd line parameter to select object keys"""
    parser.add_argument(
        f"-{KEYS_SHORT}",
        f"--{KEYS}",
        "--keys",
        "--projectKey",
        required=False,
        help="Commas separated keys of the objects to select",
    )
    return parser


def add_language_arg(parser: ArgumentParser, object_types: str) -> ArgumentParser:
    """Adds the language selection option"""
    parser.add_argument(f"--{LANGUAGES}", required=False, help=f"Commas separated list of language to filter {object_types}")
    return parser


def add_component_type_arg(parser: ArgumentParser, comp_types: tuple[str] = COMPONENT_TYPES) -> ArgumentParser:
    """Adds the component type selection option"""
    group = parser.add_mutually_exclusive_group()
    for c in comp_types:
        group.add_argument(f"--{c}", required=False, dest=COMPONENT_TYPE, action="store_const", const=c, help=f"Process {c}")
    parser.set_defaults(compType=COMPONENT_TYPES[0])
    return parser


def set_target_sonar_args(parser: ArgumentParser) -> ArgumentParser:
    """Sets the target SonarQube CLI options"""
    parser.add_argument(
        f"-{URL_TARGET_SHORT}",
        f"--{URL_TARGET}",
        required=False,
        help="Root URL of the target platform when using sonar-findings-sync",
    )
    parser.add_argument(
        f"-{TOKEN_TARGET_SHORT}",
        f"--{TOKEN_TARGET}",
        required=False,
        help="Token of target platform when using sonar-findings-sync - Unauthenticated usage is not possible",
    )
    parser.add_argument(
        f"-{ORG_TARGET_SHORT}",
        f"--{ORG_TARGET}",
        required=False,
        help="Organization when using sonar-findings-sync with SonarCloud as target platform",
    )
    return parser


def set_output_file_args(parser: ArgumentParser, help_str: str = None, allowed_formats: tuple[str, ...] = ("csv",)) -> ArgumentParser:
    """Sets the output file CLI options"""
    if not help_str:
        help_str = "Report file, stdout by default"
    parser.add_argument(f"-{REPORT_FILE_SHORT}", f"--{REPORT_FILE}", required=False, default=None, help=help_str)
    if len(allowed_formats) > 1:
        parser.add_argument(
            f"--{FORMAT}",
            choices=allowed_formats,
            required=False,
            default=None,
            help="Output format for generated report.\nIf not specified, it is the output file extension if json, csv or yaml, then csv by default",
        )
    if "csv" in allowed_formats:
        parser.add_argument(
            f"--{CSV_SEPARATOR}",
            required=False,
            default=__DEFAULT_CSV_SEPARATOR,
            help=f"CSV separator (for CSV files), default '{__DEFAULT_CSV_SEPARATOR}'",
        )
    return parser


def set_what(parser: ArgumentParser, what_list: list[str], operation: str) -> ArgumentParser:
    """Sets the argument to select what to audit or to export as config"""
    parser.add_argument(
        "-w",
        f"--{WHAT}",
        required=False,
        default="",
        help=f"What to {operation} {','.join(what_list)}",
    )
    return parser
