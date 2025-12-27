#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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

"""Utilities for sonar-tools"""

from typing import Any, Union, Optional
from http import HTTPStatus
import sys
import os
import math
import re
import json
import datetime
import requests

import Levenshtein

import sonar.logging as log
from sonar import version, errcodes, exceptions
from sonar.util import types, constants as c
import sonar.util.misc as util

import cli.options as opt


SQ_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
SQ_DATE_FORMAT = "%Y-%m-%d"
SQ_TIME_FORMAT = "%H:%M:%S"
DEFAULT = "__default__"
WRITE_END = None


def check_last_version(package_url: str) -> None:
    """Checks last version of sonar-tools on pypi and displays a warning if the currently used version is older"""
    log.info("Checking latest sonar-version on pypi.org")
    try:
        r = requests.get(url=package_url, headers={"Accept": "application/vnd.pypi.simple.v1+json"}, timeout=10)
        r.raise_for_status()
    except Exception as e:
        log.info("Can't access pypi.org, error %s", str(e))
        return
    txt_version = json.loads(r.text)["versions"][-1]
    package_name = package_url.split("/")[-1]
    log.info("Latest %s released version is %s", package_name, txt_version)
    if tuple(".".split(txt_version)) > tuple(".".split(version.PACKAGE_VERSION)):
        log.warning("A more recent version of %s (%s) is available, your are advised to upgrade", package_name, txt_version)


def token_type(token: str) -> str:
    """Returns the type of token"""
    if len(token) not in (c.SQS_TOKEN_LENGTH, c.SQC_TOKEN_LENGTH):
        return "wrong format"
    if token[0:4] == "sqa_":
        return "global-analysis"
    if token[0:4] == "sqp_":
        return "project-analysis"
    if token[0:4] == "squ_":
        return "user"
    return "user"


def is_a_token(token: str) -> bool:
    """Returns whether a string is a token"""
    return token_type(token) != "wrong format"


def check_token(token: Optional[str], is_sonarcloud: bool = False) -> None:
    """Verifies if a proper user token has been provided"""
    if token is None:
        raise exceptions.SonarException("Token is missing (Argument -t/--token)", errcodes.SONAR_API_AUTHENTICATION)
    if not is_sonarcloud and token_type(token) != "user":
        raise exceptions.SonarException(
            f"The provided token {redacted_token(token)} is a {token_type(token)} token, a user token is required for sonar-tools",
            errcodes.TOKEN_NOT_SUITED,
        )


def redact_tokens(data: Any) -> Any:
    """Recursively redacts Sonar tokens"""
    if isinstance(data, str) and is_a_token(data):
        return redacted_token(data)
    if isinstance(data, (str, int, float)):
        return data
    if isinstance(data, (list, set, tuple)):
        return [redact_tokens(elem) for elem in data]
    elif isinstance(data, dict):
        data = data.copy()
        for k, v in data.items():
            if isinstance(v, (dict, list, tuple, set, str)):
                data[k] = redact_tokens(v)
    return data


def string_to_date(string: str) -> Union[datetime.datetime, datetime.date, str, None]:
    """Converts a string date to a date"""
    try:
        return datetime.datetime.strptime(string, SQ_DATETIME_FORMAT)
    except (ValueError, TypeError):
        try:
            return datetime.datetime.strptime(string, SQ_DATE_FORMAT).replace(tzinfo=datetime.timezone.utc)
        except (ValueError, TypeError):
            return None


def date_to_string(date: Optional[datetime.datetime], with_time: bool = True) -> str:
    """Converts a date to a string"""
    if not date:
        return ""
    return date.strftime(SQ_DATETIME_FORMAT if with_time else SQ_DATE_FORMAT)


def get_setting(settings: dict[str, Any], key: str, default: Any) -> Any:
    """Gets a setting or the default value"""
    if settings is None:
        return default
    return settings.get(key, default)


def redacted_token(token: str) -> str:
    """Redacts a token for security (before printing)"""
    if token is None:
        return "-"
    if token[0:4] in ("squ_", "sqa_", "sqp_"):
        return re.sub(r"(......).*(..)", r"\1***\2", token)
    else:
        return re.sub(r"(..).*(..)", r"\1***\2", token)


def jvm_heap(cmdline: str) -> Union[int, None]:
    """Computes JVM heap in MB from a Java cmd line string"""
    for s in cmdline.split(" "):
        if not re.match("-Xmx", s):
            continue
        try:
            val = int(s[4:-1])
            unit = s[-1].upper()
            if unit == "M":
                return val
            if unit == "G":
                return val * 1024
            if unit == "K":
                return val // 1024
        except ValueError:
            log.warning("JVM -Xmx heap specified seems invalid in '%s'", cmdline)
            return None
    log.warning("No JVM heap memory settings specified in '%s'", cmdline)
    return None


def int_memory(string: str) -> Optional[int]:
    """Converts memory from string to int in MB"""
    try:
        (val, unit) = string.split(" ")
    except ValueError:
        return None
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
    elif unit == "KB":
        int_val = int(val / 1024)
    elif unit == "bytes":
        int_val = int(val / 1024 / 1024)
    return int_val


def final_exit(exit_code: int, err_msg: Optional[str] = None, start_time: Optional[datetime.datetime] = None) -> None:
    """Fatal exit with error msg"""
    if exit_code != errcodes.OK:
        log.fatal(err_msg)
        print(f"FATAL: {err_msg}", file=sys.stderr)
    if start_time:
        log.info("Total execution time: %s", str(datetime.datetime.now() - start_time))
    sys.exit(exit_code)


def convert_string(value: str) -> Union[str, int, float, bool]:
    """Converts strings to corresponding types"""
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


def update_json(json_data: dict[str, str], categ: str, subcateg: str, value: Any) -> dict[str, str]:
    """Updates a 2 levels JSON"""
    json_data[categ] = json_data.get(categ) or {}
    if subcateg is None:
        json_data[categ].update(value)
    else:
        json_data[categ][subcateg] = json_data[categ].get(subcateg) or {}
        json_data[categ][subcateg].update(value)
    return json_data


def nbr_pages(sonar_api_json: dict[str, str], api_version: int = 1) -> int:
    """Returns nbr of pages of a paginated Sonar API call"""
    paging = "page" if api_version == 2 else "paging"
    if paging in sonar_api_json:
        return math.ceil(sonar_api_json[paging]["total"] / sonar_api_json[paging]["pageSize"])
    elif "total" in sonar_api_json:
        return math.ceil(sonar_api_json["total"] / sonar_api_json["ps"])
    else:
        return 1


def nbr_total_elements(sonar_api_json: dict[str, str], api_version: int = 1) -> int:
    """Returns nbr of elements of a paginated Sonar API call"""
    paging = "page" if api_version == 2 else "paging"
    if "total" in sonar_api_json:
        return sonar_api_json["total"]
    elif paging in sonar_api_json:
        return sonar_api_json[paging]["total"]
    else:
        return 0


def is_api_v2(api: str) -> bool:
    """Returns whether and API string is v2"""
    return api.lower().startswith("v2/") or api.lower().startswith("api/v2/")


def search_by_name(
    endpoint: object, name: str, api: str, returned_field: str, extra_params: Optional[dict[str, str]] = None
) -> Optional[dict[str, Any]]:
    """Searches a object by name and returns its JSON data"""
    params = {"q": name} | (extra_params or {})
    data = json.loads(endpoint.get(api, params=params).text)
    return next((d for d in data[returned_field] if d["name"] == name), None)


def search_by_key(endpoint: object, key: str, api: str, returned_field: str, extra_params: Optional[dict[str, str]] = None) -> types.ApiPayload:
    """Search an object by its key"""
    params = {"q": key} | (extra_params or {})
    data = json.loads(endpoint.get(api, params=params).text)
    return next((d for d in data[returned_field] if d["key"] == key), None)


def sonar_error(response: requests.models.Response) -> str:
    """Formats the error returned in a Sonar HTTP response"""
    try:
        json_res = json.loads(response.text)
        if "errors" in json_res:
            return " | ".join([e["msg"] for e in json.loads(response.text)["errors"]])
        elif "message" in json_res:
            # API v2 format
            return json_res["message"]
        else:
            log.debug("No error found in Response %s", util.json_dump(json_res))
    except json.decoder.JSONDecodeError:
        pass
    return ""


def http_error_and_code(exception: requests.HTTPError) -> tuple[int, str]:
    """Returns the Sonar error code of an API HTTP response, or None if no error"""
    response = exception.response
    if response.ok:
        return None, "No error"
    tool_msg = f"URL {response.request.url}: "
    code = response.status_code
    if code == HTTPStatus.UNAUTHORIZED:
        tool_msg += f"HTTP error {code} - Authentication error. Is token valid ?"
        err_code = errcodes.SONAR_API_AUTHENTICATION
    elif code == HTTPStatus.FORBIDDEN:
        tool_msg += f"HTTP error {code} - Insufficient permissions to perform operation"
        err_code = errcodes.SONAR_API_AUTHORIZATION
    elif code == HTTPStatus.NOT_FOUND:
        tool_msg += f"HTTP error {code} - object not found"
        err_code = errcodes.OBJECT_NOT_FOUND
    else:
        tool_msg += f"HTTP error {code} - "
        err_code = errcodes.SONAR_API
    return err_code, f"{tool_msg}: {sonar_error(response)}"


def error_msg(exception: Exception) -> str:
    """Returns the error of an Sonar API HTTP response, or None if no error"""
    if isinstance(exception, requests.HTTPError):
        _, errmsg = http_error_and_code(exception)
        return errmsg
    else:
        return str(exception)


def handle_error(e: Exception, context: str, **kwargs) -> None:
    """General handler for errors"""
    LOG_FORMAT = "%s while %s"
    if kwargs.get("catch_all", False):
        log.log(kwargs.get("log_level", log.ERROR), LOG_FORMAT, error_msg(e), context)
        return
    catch_http = kwargs.get("catch_http_errors", False)
    catch_statuses = kwargs.get("catch_http_statuses", ())
    if isinstance(e, requests.HTTPError) and (catch_http or e.response.status_code in catch_statuses):
        log.log(kwargs.get("log_level", log.ERROR), LOG_FORMAT, error_msg(e), context)
        return
    log.error(LOG_FORMAT, error_msg(e), context)
    raise e


def check_what(what: Union[str, list[str]], allowed_values: list[str], operation: str = "processed") -> list[str]:
    """Check if what is requested is in allowed values"""
    if what == "":
        return allowed_values
    what = util.csv_to_list(what)
    w = next((w for w in what if w not in allowed_values), None)
    if w:
        final_exit(
            errcodes.ARGS_ERROR,
            f"'{w}' is not something that can be {operation}, chose among {','.join(allowed_values)}",
        )
    return what


def edition_normalize(edition: str) -> Optional[str]:
    """Returns the SQ edition in a normalized way (community, developer, enterprise or datacenter)

    :param str edition: The original non normalized edition string
    :return: The normalized edition string
    :rtype: str
    """
    if edition is None:
        return None
    return edition.lower().replace("edition", "").replace(" ", "")


def string_to_version(sif_v: Optional[str], digits: int = 3) -> Optional[tuple[int, ...]]:
    """Returns the normalized SQ version as tuple"""
    if sif_v is None:
        return None
    try:
        split_version = sif_v.split(".")
        if len(split_version) < digits:
            split_version += ["0"] * (digits - len(split_version))
    except KeyError:
        return None
    try:
        return tuple(int(n) for n in split_version[0:digits])
    except ValueError:
        return None


def version_to_string(vers: tuple[int, int, int]) -> str:
    """Converts a version tuple to string"""
    return ".".join([str(n) for n in vers])


def is_sonarcloud_url(url: str) -> bool:
    """Returns whether an URL is the SonarQube Cloud URL

    :param str url: The URL to examine
    :return: Whether the URL is the SonarQube Cloud URL (in any form)
    :rtype: str
    """
    return url.rstrip("/").lower().endswith("sonarcloud.io")


def convert_args(args: object, second_platform: bool = False) -> dict[str, str]:
    """Converts CLI args int kwargs compatible with a platform"""
    kwargs = vars(args).copy()
    kwargs["org"] = kwargs.pop(opt.ORG, None)
    kwargs["cert_file"] = kwargs.pop(opt.CERT, None)

    if second_platform:
        kwargs[opt.URL] = kwargs.pop(opt.URL_TARGET, kwargs[opt.URL])
        kwargs[opt.TOKEN] = kwargs.pop(opt.TOKEN_TARGET, kwargs[opt.TOKEN])
        kwargs["org"] = kwargs.pop(opt.ORG_TARGET, kwargs.get(opt.ORG, None))
    default_timeout = 20 if is_sonarcloud_url(kwargs[opt.URL]) else 10
    kwargs["http_timeout"] = kwargs.pop(opt.HTTP_TIMEOUT, default_timeout)
    return kwargs


def inline_lists(element: Any, exception_values: tuple[str]) -> Any:
    """Recursively explores a dict and replace string lists by CSV strings, if list values do not contain commas"""
    if isinstance(element, dict):
        new_dict = element.copy()
        for k, v in element.items():
            if k not in exception_values:
                new_dict[k] = inline_lists(v, exception_values=exception_values)
        return new_dict
    elif isinstance(element, (list, set)):
        cannot_be_csv = any(not isinstance(v, str) or "," in v for v in element)
        if cannot_be_csv:
            return element
        else:
            return util.list_to_csv(element, separator=", ")
    else:
        return element


def http_error_string(status: HTTPStatus) -> str:
    """Returns the error string for a HTTPStatus code"""
    if status == HTTPStatus.UNAUTHORIZED:
        return "UNAUTHORIZED"
    elif status == HTTPStatus.FORBIDDEN:
        return "INSUFFICIENT_PERMISSIONS"
    elif status == HTTPStatus.NOT_FOUND:
        return "NOT_FOUND"
    elif status == HTTPStatus.BAD_REQUEST:
        return "BAD_REQUEST"
    elif status == HTTPStatus.INTERNAL_SERVER_ERROR:
        return "INTERNAL_SERVER_ERROR"
    else:
        return f"HTTP Error {status.value} - {status.phrase}"


def to_days(time_expression: str) -> Optional[int]:
    """Converts a time expression to days, e.g. '1 day', '2 weeks', '3 months', '1 year'"""
    match = re.match(r"(\d+) (day|week|month|year)s?", time_expression)
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    if unit == "day":
        return value
    if unit == "week":
        return value * 7
    if unit == "month":
        return value * 30  # Approximate month length
    if unit == "year":
        return value * 365  # Approximate year length
    return None


def flatten(original_dict: dict[str, any]) -> dict[str, any]:
    """Flattens a recursive dict into a flat one"""
    flat_dict = {}
    for k, v in original_dict.items():
        if isinstance(v, dict):
            flat_dict |= flatten(v)
        elif isinstance(v, list):
            for elem in v:
                log.debug("Flattening %s", elem)
                if "settings" in elem:
                    flat_dict |= {e["key"]: e["value"] for e in elem["settings"] if "value" in e}
                elif "key" in elem and "value" in elem:
                    flat_dict |= {elem["key"]: elem["value"]}
                else:
                    log.debug("Can't flatten %s", elem)
        else:
            flat_dict[k] = v
    return flat_dict


def similar_strings(key1: str, key2: str, max_distance: int = 5) -> bool:
    """Returns whether 2 project keys are similar, but not equal"""
    if key1 == key2:
        return False
    max_distance = min(len(key1) // 2, len(key2) // 2, max_distance)
    return (len(key2) >= 7 and (re.match(key2, key1))) or Levenshtein.distance(key1, key2, score_cutoff=6) <= max_distance


def perms_to_list(perms: dict[str, Any]) -> list[str, Any]:
    """Converts permissions in dict format to list format"""
    if not perms or not isinstance(perms, dict):
        return perms
    list_perms = util.dict_to_list(perms.get("groups", {}), "group", "permissions") + util.dict_to_list(perms.get("users", {}), "user", "permissions")
    return [p for p in list_perms if p.get("permissions") is not None and p.get("permissions") != []]
