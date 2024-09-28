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
from typing import TextIO, Union, Optional
from http import HTTPStatus
import sys
import os
import contextlib
import re
import json
import datetime
from datetime import timezone

import requests

import sonar.logging as log
from sonar import version, errcodes


ISO_DATE_FORMAT = "%04d-%02d-%02d"
SQ_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
SQ_DATE_FORMAT = "%Y-%m-%d"
SQ_TIME_FORMAT = "%H:%M:%S"
DEFAULT = "__default__"


def check_last_sonar_tools_version() -> None:
    """Checks last version of sonar-tools on pypi and displays a warning if the currently used version is older"""
    log.info("Checking latest sonar-version on pypi.org")
    try:
        r = requests.get(url="https://pypi.org/simple/sonar-tools", headers={"Accept": "application/vnd.pypi.simple.v1+json"}, timeout=10)
        r.raise_for_status()
    except (requests.RequestException, requests.exceptions.HTTPError, requests.exceptions.Timeout) as e:
        log.info("Can't access pypi.org, error %s", str(e))
        return
    txt_version = json.loads(r.text)["versions"][-1]
    log.info("Latest sonar-tools version is %s", txt_version)
    if tuple(".".split(txt_version)) > tuple(".".split(version.PACKAGE_VERSION)):
        log.warning("A more recent version of sonar-tools (%s) is available, your are advised to upgrade", txt_version)


def token_type(token: str) -> str:
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
            errcodes.SONAR_API_AUTHENTICATION,
        )
    if not is_sonarcloud and token_type(token) != "user":
        exit_fatal(
            f"The provided token {redacted_token(token)} is a {token_type(token)} token, a user token is required for sonar-tools",
            errcodes.TOKEN_NOT_SUITED,
        )


def json_dump_debug(json_data: Union[list[str], dict[str, str]], pre_string: str = "") -> None:
    log.debug("%s%s", pre_string, json_dump(json_data))


def format_date_ymd(year: int, month: int, day: int):
    return ISO_DATE_FORMAT % (year, month, day)


def format_date(somedate: datetime.datetime) -> str:
    return ISO_DATE_FORMAT % (somedate.year, somedate.month, somedate.day)


def string_to_date(string: str) -> Union[datetime.datetime, datetime.date, str]:
    try:
        return datetime.datetime.strptime(string, SQ_DATETIME_FORMAT)
    except (ValueError, TypeError):
        try:
            return datetime.datetime.strptime(string, SQ_DATE_FORMAT).replace(tzinfo=datetime.timezone.utc)
        except (ValueError, TypeError):
            return string


def date_to_string(date: datetime.datetime, with_time=True) -> str:
    return "" if date is None else date.strftime(SQ_DATETIME_FORMAT if with_time else SQ_DATE_FORMAT)


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


def get_setting(settings: dict[str, str], key: str, default: any) -> any:
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


def convert_to_type(value: any) -> any:
    """Converts a potentially string value to the corresponding int or float"""
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


def remove_nones(d: dict[str, str]) -> dict[str, str]:
    """Removes elements of the dict that are None values"""
    if isinstance(d, dict):
        return {k: v for k, v in d.items() if v is not None}
    else:
        return d


def remove_empties(d: dict[str, any]) -> dict[str, any]:
    """Recursively removes empty lists and dicts and none from a dict"""
    # log.debug("Cleaning up %s", json_dump(d))
    new_d = d.copy()
    for k, v in d.items():
        if v is None:
            new_d.pop(k)
            continue
        if not isinstance(v, (list, dict)):
            continue
        if len(v) == 0:
            new_d.pop(k)
        elif isinstance(v, dict):
            new_d[k] = remove_empties(v)
    return new_d


def dict_subset(d: dict[str, str], subset_list: list[str]) -> dict[str, str]:
    """Returns the subset of dict only with subset_list keys"""
    return {key: d[key] for key in subset_list if key in d}


def allowed_values_string(original_str: str, allowed_values: list[str]) -> str:
    """Returns CSV values from an allowed list"""
    return list_to_csv([v for v in csv_to_list(original_str) if v in allowed_values])


def json_dump(jsondata: Union[list[str], dict[str, str]], indent: int = 3) -> str:
    """JSON dump helper"""
    return json.dumps(remove_nones(jsondata), indent=indent, sort_keys=True, separators=(",", ": "))


def csv_to_list(string: str, separator: str = ",") -> list[str]:
    """Converts a csv string to a list"""
    if isinstance(string, list):
        return string
    if isinstance(string, tuple):
        return list(string)
    if not string or re.match(r"^\s*$", string):
        return []
    return [s.strip() for s in string.split(separator)]


def list_to_csv(array: Union[None, str, int, float, list[str]], separator: str = ",", check_for_separator: bool = False) -> Optional[str]:
    """Converts a list of strings to CSV"""
    if isinstance(array, str):
        return csv_normalize(array, separator) if " " in array else array
    if array is None:
        return None
    if isinstance(array, (list, set, tuple)):
        if check_for_separator:
            # Don't convert to string if one array item contains the string separator
            s = separator.strip()
            for item in array:
                if s in item:
                    return array
        return separator.join([v.strip() for v in array])
    return str(array)


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


def difference(list1: list[any], list2: list[any]) -> list[any]:
    """Computes difference of 2 lists"""
    # FIXME - This should be sets
    return [value for value in list1 if value not in list2]


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
    for k in dict2:
        if k not in dict1:
            dict1[k] = 0
        dict1[k] += dict2[k]
    return dict1


def exit_fatal(err_msg: str, exit_code: int) -> None:
    """Fatal exit with error msg"""
    log.fatal(err_msg)
    print(f"FATAL: {err_msg}", file=sys.stderr)
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


def update_json(json_data: dict[str, str], categ: str, subcateg: str, value: any) -> dict[str, str]:
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


def int_div_ceil(number: int, divider: int) -> int:
    """Computes rounded up int division"""
    return (number + divider - 1) // divider


def nbr_pages(sonar_api_json: dict[str, str]) -> int:
    """Returns nbr of pages of a paginated Sonar API call"""
    if "total" in sonar_api_json:
        return int_div_ceil(sonar_api_json["total"], sonar_api_json["ps"])
    elif "paging" in sonar_api_json:
        return int_div_ceil(sonar_api_json["paging"]["total"], sonar_api_json["paging"]["pageSize"])
    else:
        return 1


@contextlib.contextmanager
def open_file(file: str = None, mode: str = "w") -> TextIO:
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


def search_by_name(endpoint: object, name: str, api: str, returned_field: str, extra_params: dict[str, str] = None) -> Union[dict[str, str], None]:
    """Searches a object by name"""
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


def sonar_error(response: requests.models.Response) -> str:
    """Formats the error returned in a Sonar HTTP response"""
    try:
        return " | ".join([e["msg"] for e in json.loads(response.text)["errors"]])
    except json.decoder.JSONDecodeError:
        return ""


def http_error(response: requests.models.Response) -> tuple[str, int]:
    """Returns the Sonar error code of an API HTTP response, or None if no error"""
    if response.ok:
        return None, None
    tool_msg = f"For request URL {response.request.url}\n"
    code = response.status_code
    if code == HTTPStatus.UNAUTHORIZED:
        tool_msg += f"HTTP error {code} - Authentication error. Is token valid ?"
        err_code = errcodes.SONAR_API_AUTHENTICATION
    elif code == HTTPStatus.FORBIDDEN:
        tool_msg += f"HTTP error {code} - Insufficient permissions to perform operation"
        err_code = errcodes.SONAR_API_AUTHORIZATION
    else:
        tool_msg += f"HTTP error {code} - "
        err_code = errcodes.SONAR_API
    return err_code, f"{tool_msg}: {sonar_error(response)}"


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
            exit_code=errcodes.ARGS_ERROR,
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


def version_to_string(vers: tuple[int, int, int]) -> str:
    """Converts a version tuple to string"""
    return ".".join([str(n) for n in vers])


def is_sonarcloud_url(url: str) -> bool:
    """Returns whether an URL is the SonarCloud URL

    :param str url: The URL to examine
    :return: Whether the URL is the SonarCloud URL (in any form)
    :rtype: str
    """
    return url.rstrip("/").lower().endswith("sonarcloud.io")


def class_name(obj: object) -> str:
    """Returns the class name of an object"""
    return type(obj).__name__


def convert_args(args: object, second_platform: bool = False) -> dict[str, str]:
    """Converts CLI args int kwargs compatible with a platform"""
    kwargs = vars(args).copy()
    kwargs["org"] = kwargs.pop("organization", None)
    kwargs["cert_file"] = kwargs.pop("clientCert", None)
    kwargs["http_timeout"] = kwargs.pop("httpTimeout", None)
    if second_platform:
        kwargs["url"] = kwargs.pop("urlTarget", kwargs["url"])
        kwargs["token"] = kwargs.pop("tokenTarget", kwargs["token"])
    return kwargs


def start_clock() -> datetime.datetime:
    """Returns the now timestamp"""
    return datetime.datetime.now()


def stop_clock(start_time: datetime.datetime) -> None:
    """Logs execution time"""
    log.info("Total execution time: %s", str(datetime.datetime.now() - start_time))


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
    """Adjust findings search filters based on Sonar version"""
    if not original_dict:
        return {}
    remapped_filters = original_dict.copy()
    for old, new in remapping.items():
        if old in original_dict and new not in remapped_filters:
            remapped_filters[new] = remapped_filters.pop(old)
    return remapped_filters


def list_re_value(a_list: list[str], mapping: dict[str, str]) -> list[str]:
    """Adjust findings search filters based on Sonar version"""
    if not a_list or len(a_list) == 0:
        return []
    for old, new in mapping.items():
        a_list = [new if v == old else v for v in a_list]
    return a_list


def dict_stringify(original_dict: dict[str, str]) -> dict[str, str]:
    """Covert dict list values into CSV string"""
    if not original_dict:
        return {}
    for k, v in original_dict.copy().items():
        if isinstance(v, list):
            original_dict[k] = list_to_csv(v)
    return original_dict


def inline_lists(element: any, exceptions: tuple[str]) -> any:
    """Recursively explores a dict and replace string lists by CSV strings, if list values do not contain commas"""
    if isinstance(element, dict):
        new_dict = element.copy()
        for k, v in element.items():
            if k not in exceptions:
                new_dict[k] = inline_lists(v, exceptions=exceptions)
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


def list_to_dict(original_list: list[dict[str, any]], key_field: str) -> dict[str, any]:
    """Converts a list to dict with list key_field as dict key"""
    converted_dict = {elem[key_field]: elem for elem in original_list}
    for e in converted_dict.values():
        e.pop(key_field)
    return converted_dict


def dict_to_list(original_dict: dict[str, any], key_field: str, value_field: Optional[str] = "value") -> list[str, any]:
    """Converts a dict to list adding dict key in list key_field"""
    return [{key_field: key, value_field: elem} if not isinstance(elem, dict) else {key_field: key, **elem} for key, elem in original_dict.items()]
