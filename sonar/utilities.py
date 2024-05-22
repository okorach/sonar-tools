#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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

    Utilities for sonar-tools

"""
from http import HTTPStatus
import sys
import os
import contextlib
import re
import logging
import argparse
import json
import datetime
from datetime import timezone
import random
from typing import Union
import requests
from sonar import options, version

OPT_URL = "url"
OPT_VERBOSE = "verbosity"
OPT_SKIP_VERSION_CHECK = "skipVersionCheck"
OPT_ORGANIZATION = "organization"
OPT_MODE = "mode"
DRY_RUN = "dryrun"
CONFIRM = "confirm"
BATCH = "batch"
RUN_MODE = DRY_RUN
ISO_DATE_FORMAT = "%04d-%02d-%02d"
SQ_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
SQ_DATE_FORMAT = "%Y-%m-%d"
SQ_TIME_FORMAT = "%H:%M:%S"

CSV_SEPARATOR = ","

logger = logging.getLogger("sonar-tools")
formatter = logging.Formatter("%(asctime)s | %(name)s | %(levelname)-7s | %(threadName)-15s | %(message)s")
fh = logging.FileHandler("sonar-tools.log")
ch = logging.StreamHandler()
logger.addHandler(fh)
logger.addHandler(ch)
fh.setFormatter(formatter)
ch.setFormatter(formatter)


def set_logger(name):
    global logger
    logger = logging.getLogger(name)
    new_fh = logging.FileHandler(name + ".log")
    new_ch = logging.StreamHandler()
    logger.addHandler(new_fh)
    logger.addHandler(new_ch)
    new_fh.setFormatter(formatter)
    new_ch.setFormatter(formatter)


def set_common_args(desc):
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
        "--" + OPT_VERBOSE,
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


def set_target_sonar_args(parser):
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


def set_output_file_args(parser, json_fmt: bool = True, csv_fmt: bool = True, sarif_fmt: bool = False):
    parser.add_argument(
        "-f",
        "--file",
        required=False,
        help="Output file for the report, stdout by default",
    )
    fmt_choice = []
    default_format = None
    if csv_fmt:
        fmt_choice.append("csv")
        default_format = "csv"
    if json_fmt:
        fmt_choice.append("json")
        if default_format is None:
            default_format = "json"
    if sarif_fmt:
        fmt_choice.append("sarif")
        if default_format is None:
            default_format = "sarif"
    if json_fmt and csv_fmt:
        parser.add_argument(
            "--" + options.FORMAT,
            choices=fmt_choice,
            required=False,
            default=default_format,
            help="Output format for generated report.\nIf not specified, it is the output file extension if json or csv, then csv by default",
        )
    if csv_fmt:
        parser.add_argument(
            "--" + options.CSV_SEPARATOR,
            required=False,
            default=CSV_SEPARATOR,
            help=f"CSV separator (for CSV output), default {CSV_SEPARATOR}",
        )

    return parser


def set_what(parser, what_list, operation):
    parser.add_argument(
        "-w",
        "--what",
        required=False,
        default="",
        help=f"What to {operation} {','.join(what_list)}",
    )
    return parser


def get_logging_level(level):
    if level == "DEBUG":
        lvl = logging.DEBUG
    elif level in ("WARN", "WARNING"):
        lvl = logging.WARNING
    elif level == "ERROR":
        lvl = logging.ERROR
    elif level == "CRITICAL":
        lvl = logging.CRITICAL
    else:
        lvl = logging.INFO
    return lvl


def set_debug_level(level):
    logger.setLevel(get_logging_level(level))
    logger.info("Set debug level to %s", level)


def check_last_sonar_tools_version() -> None:
    """Checks last version of sonar-tools on pypi and displays a warning if the currently used version is older"""
    logger.info("Checking latest sonar-version on pypi.org")
    try:
        r = requests.get(url="https://pypi.org/simple/sonar-tools", headers={"Accept": "application/vnd.pypi.simple.v1+json"}, timeout=10)
        r.raise_for_status()
    except (requests.RequestException, requests.exceptions.HTTPError, requests.exceptions.Timeout) as e:
        logger.info("Can't access pypi.org, error %s", str(e))
    txt_version = json.loads(r.text)["versions"][-1]
    logger.info("Latest sonar-tools version is %s", txt_version)
    if tuple(".".split(txt_version)) > tuple(".".split(version.PACKAGE_VERSION)):
        logger.warning("A more recent version of sonar-tools (%s) is available, your are advised to upgrade", txt_version)


def parse_and_check(parser: argparse.ArgumentParser, verify_token: bool = True) -> object:
    """Parses arguments and perform common environment checks"""
    args = parser.parse_args()
    kwargs = vars(args)
    set_debug_level(kwargs[OPT_VERBOSE])
    logger.info("sonar-tools version %s", version.PACKAGE_VERSION)

    # Verify version randomly once every 10 runs
    if not kwargs[OPT_SKIP_VERSION_CHECK] and random.randrange(10) == 0:
        check_last_sonar_tools_version()

    if verify_token:
        check_token(args.token, is_sonarcloud_url(kwargs[OPT_URL]))
    return args


def token_type(token):
    if token[0:4] == "sqa_":
        return "global-analysis"
    elif token[0:4] == "sqp_":
        return "project-analysis"
    else:
        return "user"


def check_token(token: str, is_sonarcloud: bool = False) -> None:
    """Verifies if a proper user token has been provided"""
    if token is None:
        exit_fatal(
            "Token is missing (Argument -t/--token)",
            options.ERR_SONAR_API_AUTHENTICATION,
        )
    if not is_sonarcloud and token_type(token) != "user":
        exit_fatal(
            f"The provided token {redacted_token(token)} is a {token_type(token)} token, a user token is required for sonar-tools",
            options.ERR_TOKEN_NOT_SUITED,
        )


def json_dump_debug(json_data, pre_string=""):
    logger.debug("%s%s", pre_string, json_dump(json_data))


def format_date_ymd(year, month, day):
    return ISO_DATE_FORMAT % (year, month, day)


def format_date(somedate):
    return ISO_DATE_FORMAT % (somedate.year, somedate.month, somedate.day)


def string_to_date(string):
    try:
        return datetime.datetime.strptime(string, SQ_DATETIME_FORMAT)
    except (ValueError, TypeError):
        return string


def date_to_string(date, with_time=True):
    return "" if date is None else date.strftime(SQ_DATETIME_FORMAT if with_time else SQ_DATE_FORMAT)


def age(some_date, rounded=True):
    """returns the age (in days) of a date

    :param some_date: date
    :type date: datetime
    :param rounded: Whether to rounddown to nearest day
    :type rounded: bool
    :return: The age in days, or by the second if not rounded
    :rtype: timedelta or int if rounded
    """
    if not some_date:
        return None
    delta = datetime.datetime.today().replace(tzinfo=timezone.utc) - some_date
    return delta.days if rounded else delta


def get_setting(settings, key, default):
    if settings is None:
        return default
    return settings.get(key, default)


def redacted_token(token):
    if token is None:
        return "-"
    if token[0:4] in ("squ_", "sqa_", "sqp_"):
        return re.sub(r"(......).*(..)", r"\1***\2", token)
    else:
        return re.sub(r"(..).*(..)", r"\1***\2", token)


def convert_to_type(value):
    try:
        newval = int(value)
        return newval
    except ValueError:
        pass
    try:
        newval = float(value)
        return newval
    except ValueError:
        pass
    return value


def remove_nones(d):
    if isinstance(d, dict):
        return {k: v for k, v in d.items() if v is not None}
    else:
        return d


def dict_subset(d, subset_list):
    """Returns the subset of dict only with subset_list keys"""
    return {key: d[key] for key in subset_list if key in d}


def allowed_values_string(original_str, allowed_values):
    return list_to_csv([v for v in csv_to_list(original_str) if v in allowed_values])


def json_dump(jsondata, indent=3):
    return json.dumps(remove_nones(jsondata), indent=indent, sort_keys=True, separators=(",", ": "))


def str_none(v):
    if v is None:
        return ""
    else:
        return str(v)


def csv_to_list(string, separator=","):
    if isinstance(string, list):
        return string
    if string is None or re.match(r"^\s*$", string):
        return []
    return [s.strip() for s in string.split(separator)]


def list_to_csv(array, separator=",", check_for_separator=False):
    if isinstance(array, str):
        return csv_normalize(array, separator) if " " in array else array
    if array is None:
        return None
    if check_for_separator:
        # Don't convert to string if one array item contains the string separator
        s = separator.strip()
        for item in array:
            if s in item:
                return array
    return separator.join([v.strip() for v in array])


def csv_normalize(string, separator=","):
    return list_to_csv(csv_to_list(string, separator))


def intersection(list1, list2):
    return [value for value in list1 if value in list2]


def union(list1, list2):
    return list1 + [value for value in list2 if value not in list1]


def difference(list1, list2):
    return [value for value in list1 if value not in list2]


def quote(string, sep):
    if sep in string:
        string = '"' + string.replace('"', '""') + '"'
    if "\n" in string:
        string = string.replace("\n", " ")
    return string


def jvm_heap(cmdline):
    for s in cmdline.split(" "):
        if not re.match("-Xmx", s):
            continue
        try:
            val = int(s[4:-1])
            unit = s[-1].upper()
            if unit == "M":
                return val
            elif unit == "G":
                return val * 1024
            elif unit == "K":
                return val // 1024
        except ValueError:
            logger.warning("JVM -Xmx heap specified seems invalid in '%s'", cmdline)
            return None
    logger.warning("No JVM heap memory settings specified in '%s'", cmdline)
    return None


def int_memory(string) -> Union[int, None]:
    (val, unit) = string.split(" ")
    # For decimal separator in some countries
    val = float(val.replace(",", "."))
    int_val = None
    if unit == "MB":
        int_val = int(val)
    elif unit == "GB":
        int_val = int(val * 1024)
    elif unit == "TB":
        int_val = int(val * 1024 * 1024)
    elif unit == "PB":
        int_val = int(val * 1024 * 1024 * 1024)
    elif unit == "EB":
        int_val = int(val * 1024 * 1024 * 1024 * 1024)
    elif unit == "KB":
        int_val = val / 1024
    elif unit == "bytes":
        int_val = val / 1024 / 1024
    return int_val


def dict_add(dict1, dict2):
    for k in dict2:
        if k not in dict1:
            dict1[k] = 0
        dict1[k] += dict2[k]
    return dict1


def exit_fatal(err_msg, exit_code):
    logger.fatal(err_msg)
    print(f"FATAL: {err_msg}", file=sys.stderr)
    sys.exit(exit_code)


def convert_string(value):
    if not isinstance(value, str):
        return value
    if value.lower() in ("yes", "true", "on"):
        value = True
    elif value.lower() in ("no", "false", "off"):
        value = False
    else:
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass
    return value


def update_json(json_data, categ, subcateg, value):
    if categ not in json_data:
        if subcateg is None:
            json_data[categ] = value
        else:
            json_data[categ] = {subcateg: value}
    elif subcateg is not None:
        if subcateg in json_data[categ]:
            json_data[categ][subcateg].update(value)
        else:
            json_data[categ][subcateg] = value
    else:
        json_data[categ].update(value)
    return json_data


def int_div_ceil(number, divider):
    return (number + divider - 1) // divider


def nbr_pages(sonar_api_json):
    if "total" in sonar_api_json:
        return int_div_ceil(sonar_api_json["total"], sonar_api_json["ps"])
    elif "paging" in sonar_api_json:
        return int_div_ceil(sonar_api_json["paging"]["total"], sonar_api_json["paging"]["pageSize"])
    else:
        return 1


@contextlib.contextmanager
def open_file(file=None, mode="w"):
    if file and file != "-":
        logger.debug("Opening file '%s'", file)
        fd = open(file=file, mode=mode, encoding="utf-8", newline="")
    else:
        logger.debug("Writing to stdout")
        fd = sys.stdout
    try:
        yield fd
    finally:
        if fd is not sys.stdout:
            fd.close()


def load_json_file(file):
    with open(file, "r", encoding="utf-8") as fd:
        return json.loads(fd.read())


def search_by_name(endpoint, name, api, returned_field, extra_params=None):
    params = {"q": name}
    if extra_params is not None:
        params.update(extra_params)
    data = json.loads(endpoint.get(api, params=params).text)
    for d in data[returned_field]:
        if d["name"] == name:
            return d
    return None


def search_by_key(endpoint, key, api, returned_field, extra_params=None):
    params = {"q": key}
    if extra_params is not None:
        params.update(extra_params)
    data = json.loads(endpoint.get(api, params=params).text)
    for d in data[returned_field]:
        if d["key"] == key:
            return d
    return None


def http_error(response: requests.models.Response) -> tuple[str, int]:
    """Returns the Sonar error code of an API HTTP response, or None if no error"""
    if response.ok:
        return None, None
    tool_msg = f"For request URL {response.request.url}\n"
    code = response.status_code
    try:
        sq_msg = " | ".join([e["msg"] for e in json.loads(response.text)["errors"]])
    except json.decoder.JSONDecodeError:
        sq_msg = ""

    if code == HTTPStatus.UNAUTHORIZED:
        tool_msg += f"HTTP error {code} - Authentication error. Is token valid ?"
        err_code = options.ERR_SONAR_API_AUTHENTICATION
    elif code == HTTPStatus.FORBIDDEN:
        tool_msg += f"HTTP error {code} - Insufficient permissions to perform operation"
        err_code = options.ERR_SONAR_API_AUTHORIZATION
    else:
        tool_msg += f"HTTP error {code} - Exiting"
        err_code = options.ERR_SONAR_API
    return err_code, f"{tool_msg}: {sq_msg}"


def log_and_exit(response: requests.models.Response) -> None:
    """If HTTP response is not OK, display an error log and exit"""
    err_code, msg = http_error(response)
    if err_code is None:
        return
    exit_fatal(msg, err_code)


def object_key(key_or_obj):
    if isinstance(key_or_obj, str):
        return key_or_obj
    else:
        return key_or_obj.key


def check_what(what, allowed_values, operation="processed"):
    if what == "":
        return allowed_values
    what = csv_to_list(what)
    for w in what:
        if w in allowed_values:
            continue
        exit_fatal(
            f"'{w}' is not something that can be {operation}, chose among {','.join(allowed_values)}",
            exit_code=options.ERR_ARGS_ERROR,
        )
    return what


def __prefix(value):
    if isinstance(value, dict):
        return {f"_{k}": __prefix(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [__prefix(v) for v in value]
    else:
        return value


def filter_export(json_data, key_properties, full):
    new_json_data = json_data.copy()
    for k in json_data:
        if k not in key_properties:
            if full and k != "actions":
                new_json_data[f"_{k}"] = __prefix(new_json_data.pop(k))
            else:
                new_json_data.pop(k)
    return new_json_data


def replace_keys(key_list, new_key, data):
    for k in key_list:
        if k in data:
            data[new_key] = data.pop(k)
    return data


def edition_normalize(edition: str) -> Union[str, None]:
    """Returns the SQ edition in a normalized way (community, developer, enterprise or datacenter)

    :param str edition: The original non normalized edition string
    :return: The normalized edition string
    :rtype: str
    """
    if edition is None:
        return None
    return edition.lower().replace("edition", "").replace(" ", "")


def string_to_version(sif_v: str, digits: int = 3, as_string: bool = False) -> Union[str, tuple[int], None]:
    """Returns the normalized SQ version as string or tuple

    :param str edition: The original non normalized edition string
    :return: The normalized edition string
    :rtype: str
    """
    if sif_v is None:
        return None

    try:
        split_version = sif_v.split(".")
    except KeyError:
        return None
    try:
        if as_string:
            return ".".join(split_version[0:digits])
        else:
            return tuple(int(n) for n in split_version[0:digits])
    except ValueError:
        return None


def is_sonarcloud_url(url: str) -> bool:
    """Returns whether an URL is the SonarCloud URL

    :param str url: The URL to examine
    :return: Whether the URL is the SonarCloud URL (in any form)
    :rtype: str
    """
    return url.rstrip("/").lower().endswith("sonarcloud.io")
