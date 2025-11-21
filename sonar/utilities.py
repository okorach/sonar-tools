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
"""

Utilities for sonar-tools

"""

from typing import Any, TextIO, Union, Optional
from collections.abc import Generator
from http import HTTPStatus
import sys
import os
import math
import contextlib
import re
import json
import datetime
from datetime import timezone
from copy import deepcopy
import requests

import Levenshtein

import sonar.logging as log
from sonar import version, errcodes, exceptions
from sonar.util import types, constants as c
import cli.options as opt


ISO_DATE_FORMAT = "%04d-%02d-%02d"
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


def check_token(token: Optional[str], is_sonarcloud: bool = False) -> None:
    """Verifies if a proper user token has been provided"""
    if token is None:
        raise exceptions.SonarException("Token is missing (Argument -t/--token)", errcodes.SONAR_API_AUTHENTICATION)
    if not is_sonarcloud and token_type(token) != "user":
        raise exceptions.SonarException(
            f"The provided token {redacted_token(token)} is a {token_type(token)} token, a user token is required for sonar-tools",
            errcodes.TOKEN_NOT_SUITED,
        )


def json_dump_debug(json_data: Union[list[str], dict[str, str]], pre_string: str = "") -> None:
    """Dumps a dict as JSON in logs"""
    log.debug("%s%s", pre_string, json_dump(json_data))


def format_date_ymd(year: int, month: int, day: int) -> str:
    """Returns a date as an ISO string"""
    return ISO_DATE_FORMAT % (year, month, day)


def format_date(somedate: datetime.datetime) -> str:
    """Returns a date as an ISO string"""
    return ISO_DATE_FORMAT % (somedate.year, somedate.month, somedate.day)


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


def age(some_date: datetime.datetime, rounded: bool = True, now: Optional[datetime.datetime] = None) -> Union[int, datetime.timedelta]:
    """returns the age (in days) of a date

    :param datetime some_date: date
    :param bool rounded: Whether to rounddown to nearest day
    :param datetime now: The current datetime. Will be computed if None is provided
    :return: The age in days, or by the second if not rounded
    :rtype: timedelta or int if rounded
    """
    if not some_date:
        return None
    if not now:
        now = datetime.datetime.now(timezone.utc).astimezone()
    delta = now - some_date
    return delta.days if rounded else delta


def get_setting(settings: dict[str, str], key: str, default: Any) -> Any:
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


def convert_to_type(value: str) -> Any:
    """Converts a potentially string value to the corresponding int or float"""
    if not isinstance(value, str):
        return value
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def none_to_zero(d: dict[str, any], key_match: str = "^.+$") -> dict[str, any]:
    """Replaces None values in a dict with 0"""
    new_d = d.copy()
    for k, v in d.items():
        if v is None and re.match(key_match, k):
            new_d[k] = 0
        elif isinstance(v, dict):
            new_d[k] = none_to_zero(v)
        elif isinstance(v, list):
            new_d[k] = [none_to_zero(elem) if isinstance(elem, dict) else elem for elem in v]
    return new_d


def remove_nones(d: Any) -> Any:
    """Removes elements of the data that are None values"""
    return clean_data(d, remove_empty=False, remove_none=True)


def clean_data(d: Any, remove_empty: bool = True, remove_none: bool = True) -> Any:
    """Recursively removes empty lists and dicts and none from a dict"""
    # log.debug("Cleaning up %s", json_dump(d))
    if isinstance(d, str):
        return convert_string(d)
    if not isinstance(d, (list, dict)):
        return d

    if isinstance(d, list):
        # Remove empty strings and nones
        if remove_empty:
            d = [elem for elem in d if not (isinstance(elem, str) and elem == "")]
        if remove_none:
            d = [elem for elem in d if elem is not None]
        return [clean_data(elem, remove_empty, remove_none) for elem in d]

    # Remove empty dict string values
    if remove_empty:
        new_d = {k: v for k, v in d.items() if not isinstance(v, str) or v != ""}
    if remove_none:
        new_d = {k: v for k, v in d.items() if v is not None}

    # Remove empty dict list or dict values
    new_d = {k: v for k, v in new_d.items() if not isinstance(v, (list, dict)) or len(v) > 0}

    # Recurse
    return {k: clean_data(v, remove_empty, remove_none) for k, v in new_d.items()}


def sort_lists(data: Any, redact_tokens: bool = True) -> Any:
    """Recursively removes empty lists and dicts and none from a dict"""
    if isinstance(data, (list, set, tuple)):
        data = list(data)
        if len(data) > 0 and isinstance(data[0], (str, int, float)):
            return sorted(data)
        return [sort_lists(elem) for elem in data]
    elif isinstance(data, dict):
        for k, v in data.items():
            if redact_tokens and k in ("token", "tokenTarget"):
                data[k] = redacted_token(v)
            if isinstance(v, set):
                v = list(v)
            if isinstance(v, list) and len(v) > 0 and isinstance(v[0], (str, int, float)):
                data[k] = sorted(v)
            elif isinstance(v, dict):
                data[k] = sort_lists(v)
    return data


def dict_subset(d: dict[str, str], key_subset: list[str]) -> dict[str, str]:
    """Returns the subset of dict only with subset_list keys"""
    return {key: d[key] for key in key_subset if key in d}


def allowed_values_string(original_str: str, allowed_values: list[str]) -> str:
    """Returns CSV values from an allowed list"""
    return list_to_csv([v for v in csv_to_list(original_str) if v in allowed_values])


def json_dump(jsondata: Union[list[str], dict[str, str]], indent: int = 3, redact_tokens: bool = True, sort_keys: bool = False) -> str:
    """JSON dump helper"""
    newdata = sort_lists(deepcopy(jsondata), redact_tokens=redact_tokens)
    return json.dumps(newdata, indent=indent, sort_keys=sort_keys, separators=(",", ": "))


def csv_to_list(string: Optional[str], separator: str = ",") -> list[str]:
    """Converts a csv string to a list"""
    if isinstance(string, (list, tuple, set)):
        return list(string)
    if not string or re.match(r"^\s*$", string):
        return []
    return [s.strip() for s in string.split(separator)]


def csv_to_set(string: Optional[str], separator: str = ",") -> set[str]:
    """Converts a csv string to a set"""
    if isinstance(string, (list, tuple, set)):
        return set(string)
    if not string or re.match(r"^\s*$", string):
        return set()
    return {s.strip() for s in string.split(separator)}


def csv_to_regexp(string: Optional[str], separator: str = ",") -> str:
    """Converts a csv string to a regexp"""
    return list_to_regexp([s.strip() for s in string.split(separator)])


def list_to_regexp(str_list: list[str]) -> str:
    """Converts a list to a regexp"""
    return "(" + "|".join(str_list) + ")" if len(str_list) > 0 else ""


def list_to_csv(array: Union[None, str, float, list[str], set[str], tuple[str]], separator: str = ",", check_for_separator: bool = False) -> Any:
    """Converts a list of strings to CSV"""
    if isinstance(array, str):
        return csv_normalize(array, separator) if " " in array else array
    if array is None:
        return None
    if isinstance(array, (list, set, tuple)) and all(isinstance(e, str) for e in array):
        if check_for_separator:
            # Don't convert to string if one array item contains the string separator
            s = separator.strip()
            for item in array:
                if s in item:
                    return array
        return separator.join([v.strip() for v in array])
    return array


def csv_normalize(string: str, separator: str = ",") -> str:
    """Normalizes a CSV string (no spaces next to separators)"""
    return list_to_csv(csv_to_list(string, separator))


def intersection(list1: list[any], list2: list[any]) -> list[any]:
    """Computes intersection of 2 lists"""
    # FIXME - This should be sets
    return [value for value in list1 if value in list2]


def union(list1: list[any], list2: list[any]) -> list[any]:
    """Computes union of 2 lists"""
    # FIXME - This should be sets
    return list1 + [value for value in list2 if value not in list1]


def difference(list1: list[Any], list2: list[Any]) -> list[Any]:
    """Computes difference of 2 lists"""
    # FIXME - This should be sets
    return list(set(list1) - set(list2))


def quote(string: str, sep: str) -> str:
    """Quotes a string if needed"""
    if sep in string:
        string = '"' + string.replace('"', '""') + '"'
    if "\n" in string:
        string = string.replace("\n", " ")
    return string


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
            elif unit == "G":
                return val * 1024
            elif unit == "K":
                return val // 1024
        except ValueError:
            log.warning("JVM -Xmx heap specified seems invalid in '%s'", cmdline)
            return None
    log.warning("No JVM heap memory settings specified in '%s'", cmdline)
    return None


def int_memory(string: str) -> Union[int, None]:
    """Converts memory from string to int in MB"""
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


def dict_add(dict1: dict[str, int], dict2: dict[str, int]) -> dict[str, int]:
    """Adds values of 2 dicts"""
    return {k: dict1.get(k, 0) + dict2.get(k, 0) for k in dict1.keys() | dict2.keys()}


def final_exit(exit_code: int, err_msg: Optional[str] = None, start_time: Optional[datetime.datetime] = None) -> None:
    """Fatal exit with error msg"""
    if exit_code != errcodes.OK:
        log.fatal(err_msg)
        print(f"FATAL: {err_msg}", file=sys.stderr)
    if start_time:
        log.info("Total execution time: %s", str(datetime.datetime.now() - start_time))
    sys.exit(exit_code)


def convert_string(value: str) -> Union[str, int, float, bool]:
    """Converst strings to corresponding types"""
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


@contextlib.contextmanager
def open_file(file: Optional[str] = None, mode: str = "w") -> Generator[TextIO, None, None]:
    """Opens a file if not None or -, otherwise stdout"""
    if file and file != "-":
        log.debug("Opening file '%s' in directory '%s'", file, os.getcwd())
        fd = open(file=file, mode=mode, encoding="utf-8", newline="")
    else:
        log.debug("Writing to stdout")
        fd = sys.stdout
    try:
        yield fd
    finally:
        if fd is not sys.stdout:
            fd.close()


def search_by_name(
    endpoint: object, name: str, api: str, returned_field: str, extra_params: Optional[dict[str, str]] = None
) -> Union[dict[str, str], None]:
    """Searches a object by name"""
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
            log.debug("No error found in Response %s", json_dump(json_res))
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


def object_key(key_or_obj: Union[str, object]) -> str:
    """Returns the key of an object of an object key"""
    if isinstance(key_or_obj, str):
        return key_or_obj
    else:
        return key_or_obj.key


def check_what(what: Union[str, list[str]], allowed_values: list[str], operation: str = "processed") -> list[str]:
    """Check if what is requested is in allowed values"""
    if what == "":
        return allowed_values
    what = csv_to_list(what)
    w = next((w for w in what if w not in allowed_values), None)
    if w:
        final_exit(
            errcodes.ARGS_ERROR,
            f"'{w}' is not something that can be {operation}, chose among {','.join(allowed_values)}",
        )
    return what


def __prefix(value: Any) -> Any:
    """Recursively places all keys in a dict or list by a prefixed version"""
    if isinstance(value, dict):
        return {f"_{k}": __prefix(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [__prefix(v) for v in value]
    else:
        return value


def filter_export(json_data: dict[str, Any], key_properties: list[str], full: bool) -> dict[str, Any]:
    """Filters dict for export removing or prefixing non-key properties"""
    new_json_data = {k: json_data[k] for k in key_properties if k in json_data}
    if full:
        new_json_data |= {f"_{k}": __prefix(v) for k, v in json_data.items() if k not in key_properties}
    return new_json_data


def replace_keys(key_list: list[str], new_key: str, data: dict[str, any]) -> dict[str, any]:
    """Replace a list of old keys by a new key in a dict"""
    for k in key_list:
        if k in data:
            data[new_key] = data.pop(k)
    return data


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


def class_name(obj: object) -> str:
    """Returns the class name of an object"""
    return type(obj).__name__


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


def start_clock() -> datetime.datetime:
    """Returns the now timestamp"""
    return datetime.datetime.now()


def deduct_format(fmt: Union[str, None], filename: Union[str, None], allowed_formats: tuple[str] = ("csv", "json")) -> str:
    """Deducts output format from CLI format and filename"""
    if fmt is None and filename is not None:
        fmt = filename.split(".").pop(-1).lower()
        if fmt == "yml":
            fmt = "yaml"
    if fmt not in allowed_formats:
        fmt = "csv"
    return fmt


def dict_remap(original_dict: dict[str, str], remapping: dict[str, str]) -> dict[str, str]:
    """Key old keys by new key in a dict"""
    if not original_dict:
        return {}
    return {remapping[k] if k in remapping else k: v for k, v in original_dict.items()}


def list_remap(a_list: list[str], mapping: dict[str, str]) -> list[str]:
    if not a_list or len(a_list) == 0:
        return []
    return list({mapping[v] if v in mapping else v for v in a_list})


def dict_stringify(original_dict: dict[str, str]) -> dict[str, str]:
    """Covert dict list values into CSV string"""
    if not original_dict:
        return {}
    for k, v in original_dict.copy().items():
        if isinstance(v, list):
            original_dict[k] = list_to_csv(v)
    return original_dict


def dict_reverse(map: dict[str, str]) -> dict[str, str]:
    """Reverses a dict"""
    return {v: k for k, v in map.items()}


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
            return list_to_csv(element, separator=", ")
    else:
        return element


def dict_remap_and_stringify(original_dict: dict[str, str], remapping: dict[str, str]) -> dict[str, str]:
    """Remaps keys and stringify values of a dict"""
    return dict_stringify(dict_remap(original_dict, remapping))


def list_to_dict(original_list: list[dict[str, Any]], key_field: str, keep_in_values: bool = False) -> dict[str, Any]:
    """Converts a list to dict with list key_field as dict key"""
    if original_list is None:
        return original_list
    converted_dict = {elem[key_field]: elem for elem in original_list}
    if not keep_in_values:
        for e in converted_dict.values():
            e.pop(key_field)
    return converted_dict


def dict_to_list(original_dict: dict[str, Any], key_field: str, value_field: Optional[str] = "value") -> list[dict[str, Any]]:
    """Converts a dict to list adding dict key in list key_field"""
    if original_dict is None or isinstance(original_dict, list):
        return original_dict
    return [{key_field: key, value_field: elem} if not isinstance(elem, dict) else {key_field: key, **elem} for key, elem in original_dict.items()]


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


def filename(file: Optional[str]) -> str:
    """Returns the filename or stdout if None or -"""
    return "stdout" if file is None or file == "-" else file


def to_days(time_expression: str) -> Optional[int]:
    """Converts a time expression to days, e.g. '1 day', '2 weeks', '3 months', '1 year'"""
    match = re.match(r"(\d+) (day|week|month|year)s?", time_expression)
    if not match:
        return None
    value, unit = match.groups()
    value = int(value)
    if unit == "day":
        return value
    elif unit == "week":
        return value * 7
    elif unit == "month":
        return value * 30  # Approximate month length
    elif unit == "year":
        return value * 365  # Approximate year length
    else:
        return None


def pretty_print_json(file: str) -> bool:
    """Opens and reformats a JSON file"""
    try:
        with open_file(file, mode="r") as fd:
            json_data = json.loads(fd.read())
        with open_file(file, mode="w") as fd:
            print(json_dump(json_data, sort_keys=True), file=fd)
    except json.decoder.JSONDecodeError:
        log.warning("File %s is not correct JSON, cannot pretty print", file)
        return False
    return True


def flatten(original_dict: dict[str, any]) -> dict[str, any]:
    """Flattens a recursive dict into a flat one"""
    flat_dict = {}
    for k, v in original_dict.items():
        if isinstance(v, dict):
            flat_dict |= flatten(v)
        elif isinstance(v, list):
            for elem in v:
                log.info("Flattening %s", elem)
                if "settings" in elem:
                    flat_dict |= {e["key"]: e["value"] for e in elem["settings"]}
                elif "key" in elem:
                    flat_dict |= {elem["key"]: elem["value"]}
                else:
                    log.info("Cant flatten %s", elem)
        else:
            flat_dict[k] = v
    return flat_dict


def similar_strings(key1: str, key2: str, max_distance: int = 5) -> bool:
    """Returns whether 2 project keys are similar, but not equal"""
    if key1 == key2:
        return False
    max_distance = min(len(key1) // 2, len(key2) // 2, max_distance)
    return (len(key2) >= 7 and (re.match(key2, key1))) or Levenshtein.distance(key1, key2, score_cutoff=6) <= max_distance


def sort_list_by_key(list_to_sort: list[dict[str, Any]], key: str, priority_field: Optional[str] = None) -> list[dict[str, Any]]:
    """Sorts a lits of dicts by a given key, exception for the priority field that would go first"""
    f_elem = None
    if priority_field:
        f_elem = next((elem for elem in list_to_sort if priority_field in elem), None)
    tmp_dict = {elem[key]: elem for elem in list_to_sort if elem != f_elem}
    first_elem = [f_elem] if f_elem else []
    return first_elem + list(dict(sorted(tmp_dict.items())).values())


def order_keys(original_dict: dict[str, any], *keys: str) -> dict[str, any]:
    """Orders a dict keys in a chosen order, existings keys not in *keys are pushed to the end

    :param dict[str, any] original_dict: Dict to order
    :param str *keys: List of keys in desired order
    :return: same dict with keys in desired order
    """
    ordered_dict = {}
    for key in [k for k in keys if k in original_dict]:
        ordered_dict[key] = original_dict[key]
    for key in [k for k in original_dict if k not in keys]:
        ordered_dict[key] = original_dict[key]
    return ordered_dict


def order_dict(d: dict[str, Any], *key_order: str) -> dict[str, Any]:
    """Orders keys of a dictionary in a given order"""
    new_d = {k: d[k] for k in key_order if k in d}
    return new_d | {k: v for k, v in d.items() if k not in new_d}


def order_list(list_to_order: list[str], *key_order: str) -> list[str]:
    """Orders elements of a list in a given order"""
    new_l = [k for k in key_order if k in list_to_order]
    return new_l + [k for k in list_to_order if k not in new_l]


def perms_to_list(perms: dict[str, Any]) -> list[str, Any]:
    """Converts permissions in dict format to list format"""
    if not perms or not isinstance(perms, dict):
        return perms
    list_perms = dict_to_list(perms.get("groups", {}), "group", "permissions") + dict_to_list(perms.get("users", {}), "user", "permissions")
    return [p for p in list_perms if p.get("permissions") is not None and p.get("permissions") != []]


def search_list(obj_list: list[Any], field: str, value: str) -> dict[str, Any]:
    """Returns the first dict elem in a list whose field is a given value"""
    return next((elem for elem in obj_list if elem[field] == value), None)
