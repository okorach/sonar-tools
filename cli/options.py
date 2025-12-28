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
from typing import Optional, Any

import sonar.logging as log
from sonar import errcodes, version, exceptions
import sonar.util.misc as util
import sonar.utilities as sutil

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

KEY_REGEXP_SHORT = "k"
KEY_REGEXP = "projectKeys"

EXPORT = "export"
EXPORT_SHORT = "e"
IMPORT = "import"
IMPORT_SHORT = "i"
VALIDATE_FILE = "validate"
CONVERT_FROM = "convertFrom"
CONVERT_TO = "convertTo"

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

BRANCH_REGEXP_SHORT = "b"
BRANCH_REGEXP = "branches"

LANGUAGES = "languages"
QP = "qualityProfiles"

FORMAT = "format"
WITH_URL = "withURL"
WITH_NAME_SHORT = "n"
WITH_NAME = "withName"
WITH_LAST_ANALYSIS_SHORT = "a"
WITH_LAST_ANALYSIS = "withLastAnalysis"
WITH_TAGS = "withTags"

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

MULTI_VALUED_OPTS = (METRIC_KEYS, RESOLUTIONS, SEVERITIES, STATUSES, TYPES, TAGS, PULL_REQUESTS, WHAT)

COMPONENT_TYPE = "compType"
PROJECTS = "projects"
PORTFOLIOS = "portfolios"
APPS = "apps"
COMPONENT_TYPES = (PROJECTS, APPS, PORTFOLIOS)


class ArgumentsError(exceptions.SonarException):
    """
    Arguments error
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, errcodes.ARGS_ERROR)


def __convert_args_to_lists(kwargs: dict[str, str]) -> dict[str, str]:
    """Converts arguments that may be CSV into lists"""
    for argname in MULTI_VALUED_OPTS:
        if argname in kwargs and kwargs[argname] is not None and isinstance(kwargs[argname], (str, list)) and len(kwargs[argname]) > 0:
            kwargs[argname] = util.csv_to_list(kwargs[argname])
    if kwargs.get(LANGUAGES, None) not in (None, ""):
        kwargs[LANGUAGES] = [lang.lower() for lang in util.csv_to_list(kwargs[LANGUAGES])]
        kwargs[LANGUAGES] = [LANGUAGE_MAPPING.get(lang, lang) for lang in util.csv_to_list(kwargs[LANGUAGES])]
    return kwargs


def __check_file_writeable(file: Optional[str]) -> None:
    """If not stdout, verifies that the chosen output file is writeable"""
    if file and file != "-":
        try:
            with open(file, mode="w", encoding="utf-8"):
                pass
        except (PermissionError, FileNotFoundError) as e:
            raise exceptions.SonarException(f"Can't write to file '{file}': {e}", errcodes.OS_ERROR) from e
        os.remove(file)


def parse_and_check(parser: ArgumentParser, logger_name: Optional[str] = None, verify_token: bool = True, is_migration: bool = False) -> object:
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
    log.debug("CLI arguments = %s", util.json_dump(sutil.redact_tokens(kwargs)))
    if not kwargs.get(IMPORT, False) and not kwargs.get(VALIDATE_FILE, False) and not kwargs.get(CONVERT_FROM, False):
        __check_file_writeable(kwargs.get(REPORT_FILE))
    # Verify version randomly once every 10 runs
    if not kwargs[SKIP_VERSION_CHECK] and random.randrange(10) == 0:
        sutil.check_last_version(f"https://pypi.org/simple/{tool}")
    kwargs.pop(SKIP_VERSION_CHECK, None)
    if sutil.is_sonarcloud_url(kwargs[URL]) and kwargs[ORG] is None:
        raise ArgumentsError(f"Organization (-{ORG_SHORT}) option is mandatory for SonarQube Cloud")
    if URL_TARGET in kwargs and kwargs[URL_TARGET] is None:
        kwargs[URL_TARGET] = kwargs[URL]
    if TOKEN_TARGET in kwargs and kwargs[TOKEN_TARGET] is None:
        kwargs[TOKEN_TARGET] = kwargs[TOKEN]
    if ORG_TARGET in kwargs and kwargs[ORG_TARGET] is None:
        kwargs[ORG_TARGET] = kwargs[ORG]
    if URL_TARGET in kwargs and sutil.is_sonarcloud_url(kwargs[URL_TARGET]) and kwargs[ORG_TARGET] is None:
        raise ArgumentsError(f"Organization (-{ORG_TARGET_SHORT}) option is mandatory for SonarQube Cloud")
    if verify_token:
        sutil.check_token(args.token, sutil.is_sonarcloud_url(kwargs[URL]))
    return args


def add_optional_arg(parser: ArgumentParser, *args: Any, **kwargs: Any) -> ArgumentParser:
    """Adds the branch argument to the parser"""
    kwargs = {"required": False, "default": None} | kwargs
    if kwargs.get("action") == "store_true":
        kwargs["default"] = False
    parser.add_argument(*args, **kwargs)
    return parser


def add_thread_arg(parser: ArgumentParser, action: str, default_value=8) -> ArgumentParser:
    """Adds the threads argument for CLI"""
    args = [f"--{NBR_THREADS}"]
    help_str = f"Define number of threads for {action}, default {default_value}"
    return add_optional_arg(parser, *args, type=int, default=default_value, help=help_str)


def add_branch_arg(parser: ArgumentParser) -> ArgumentParser:
    """Adds the branch argument to the parser"""
    args = [f"-{BRANCH_REGEXP_SHORT}", f"--{BRANCH_REGEXP}"]
    return add_optional_arg(parser, *args, type=str, help="Regexp to select branches that should be extracted")


def add_pull_request_arg(parser: ArgumentParser) -> ArgumentParser:
    """Adds the PR argument to the parser"""
    args = [f"-{PULL_REQUESTS_SHORT}", f"--{PULL_REQUESTS}"]
    return add_optional_arg(parser, *args, help="Use .* to export for all PRs.")


def add_dateformat_arg(parser: ArgumentParser) -> ArgumentParser:
    """Adds the date format argument to the parser"""
    args = [f"-{DATES_WITHOUT_TIME_SHORT}", f"--{DATES_WITHOUT_TIME}"]
    return add_optional_arg(parser, *args, action="store_true", help="Reports timestamps only with date, not time")


def add_url_arg(parser: ArgumentParser) -> ArgumentParser:
    """Adds the option to export URL of objects"""
    return add_optional_arg(parser, f"--{WITH_URL}", action="store_true", help="Also list the URL of the objects")


def add_import_export_arg(parser: ArgumentParser, topic: str, import_opt: bool = True, export_opt: bool = True) -> ArgumentParser:
    """Adds the CLI params for export/import"""
    group = parser.add_mutually_exclusive_group()
    if export_opt:
        msg = f" (exclusive of --{IMPORT})" if import_opt else ""
        group.add_argument(f"-{EXPORT_SHORT}", f"--{EXPORT}", required=False, default=False, action="store_true", help=f"To export {topic}{msg}")
    if import_opt:
        msg = f" (exclusive of --{EXPORT})" if export_opt else ""
        group.add_argument(f"-{IMPORT_SHORT}", f"--{IMPORT}", required=False, default=False, action="store_true", help=f"To import {topic}{msg}")
    return parser


def set_common_args(desc: str) -> ArgumentParser:
    """Parses options common to all sonar-tools scripts"""
    parser = ArgumentParser(description=desc)
    args = [f"-{TOKEN_SHORT}", f"--{TOKEN}"]
    help_str = """Token to authenticate to the source SonarQube, default is environment variable $SONAR_TOKEN
        - Unauthenticated usage is not possible"""
    parser = add_optional_arg(parser, *args, default=os.getenv("SONAR_TOKEN", None), help=help_str)

    args = [f"-{URL_SHORT}", f"--{URL}"]
    help_str = """Root URL of the source SonarQube Server or Cloud platform,
        default is environment variable $SONAR_HOST_URL or http://localhost:9000 if not set"""
    parser = add_optional_arg(parser, *args, help=help_str, default=os.getenv("SONAR_HOST_URL", "http://localhost:9000"))

    args = [f"-{ORG_SHORT}", f"--{ORG}"]
    parser = add_optional_arg(parser, *args, help="Organization when using sonar-tools with SonarQube Cloud")

    args = [f"-{VERBOSE_SHORT}", f"--{VERBOSE}"]
    parser = add_optional_arg(parser, *args, choices=["WARN", "INFO", "DEBUG"], default="INFO", help="Logging verbosity level")

    args = [f"-{CERT_SHORT}", f"--{CERT}"]
    parser = add_optional_arg(parser, *args, help="Optional client certificate file (as .pem file)")

    args = [f"--{HTTP_TIMEOUT}"]
    parser = add_optional_arg(parser, *args, default=10, help="HTTP timeout for requests to SonarQube, 10 by default (in seconds)")

    args = [f"--{SKIP_VERSION_CHECK}"]
    parser = add_optional_arg(parser, *args, action="store_true", help="Prevents sonar-tools to occasionnally check from more recent version")

    args = [f"-{LOGFILE_SHORT}", f"--{LOGFILE}"]
    parser = add_optional_arg(parser, *args, help="Define location of logfile, logs are only sent to stderr if not set")

    return parser


def set_key_arg(parser: ArgumentParser) -> ArgumentParser:
    """Adds the cmd line parameter to select object keys"""
    args = [f"-{KEY_REGEXP_SHORT}", f"--{KEY_REGEXP}", "--keys", "--projectKey"]
    return add_optional_arg(parser, *args, type=str, help="Regexp to select projects, apps or portfolios keys")


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
    """Sets the target SonarQube Server or Cloud CLI options"""
    args = [f"-{URL_TARGET_SHORT}", f"--{URL_TARGET}"]
    parser = add_optional_arg(parser, *args, help="Root URL of the target platform when using sonar-findings-sync")

    args = ["-{TOKEN_TARGET_SHORT}", f"--{TOKEN_TARGET}"]
    help_str = "Token of target platform when using sonar-findings-sync - Unauthenticated usage is not possible"
    parser = add_optional_arg(parser, *args, help=help_str)

    args = [f"-{ORG_TARGET_SHORT}", f"--{ORG_TARGET}"]
    help_str = "Organization when using sonar-findings-sync with SonarQube Cloud as target platform"
    parser = add_optional_arg(parser, *args, help=help_str)
    return parser


def set_output_file_args(parser: ArgumentParser, help_str: Optional[str] = None, allowed_formats: tuple[str, ...] = ("csv",)) -> ArgumentParser:
    """Sets the output file CLI options"""
    help_str = help_str or "Report file, stdout by default"
    parser.add_argument(f"-{REPORT_FILE_SHORT}", f"--{REPORT_FILE}", required=False, default=None, help=help_str)
    if len(allowed_formats) > 1:
        args = [f"--{FORMAT}"]
        help_str = "Output format for generated report.\nIf not specified, it is the output file extension if json, csv or yaml, then csv by default"
        parser = add_optional_arg(parser, *args, help=help_str)
    if "csv" in allowed_formats:
        args = [f"--{CSV_SEPARATOR}"]
        help_str = f"CSV separator (for CSV files), default '{__DEFAULT_CSV_SEPARATOR}'"
        parser = add_optional_arg(parser, *args, default=__DEFAULT_CSV_SEPARATOR, help=help_str)
    return parser


def set_what(parser: ArgumentParser, what_list: list[str], operation: str) -> ArgumentParser:
    """Sets the argument to select what to audit or to export as config"""
    args = ["-w", f"--{WHAT}"]
    return add_optional_arg(parser, *args, default="", help=f"What to {operation} {','.join(what_list)}")


def add_settings_arg(parser: ArgumentParser) -> ArgumentParser:
    """Adds the settings argument to the parser"""
    parser.add_argument(
        "-D",
        required=False,
        action="append",
        dest="settings",
        nargs="*",
        help="Pass configuration settings on command line (-D<setting>=<value>)",
    )
    return parser


def add_config_arg(parser: ArgumentParser, file: str) -> ArgumentParser:
    """Adds the config argument to the parser"""
    help_str = f"Creates the $HOME/{file} configuration file, if not already present or outputs to stdout if it already exist"
    add_optional_arg(parser, "--config", dest="config", action="store_true", help=help_str)
    return parser
