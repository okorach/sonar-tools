#
# sonar-tools
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
"""Miscellaneous utilities"""

from math import log
from typing import Union, Optional, Any
import json
import re
import datetime
import contextlib
import os
import sys
from typing import TextIO, Generator
from copy import deepcopy

ISO_DATE_FORMAT = "%04d-%02d-%02d"


def convert_string(value: str) -> Union[str, int, float, bool]:
    """Converts strings to corresponding types"""
    new_val: Any = value
    if not isinstance(value, str):
        return value
    if value.lower() in ("yes", "true", "on"):
        new_val = True
    elif value.lower() in ("no", "false", "off"):
        new_val = False
    else:
        try:
            new_val = int(value)
        except ValueError:
            try:
                new_val = float(value)
            except ValueError:
                pass
    return new_val


def convert_types(data: Any) -> Any:
    """Converts strings to corresponding types in a dictionary"""
    if isinstance(data, str):
        return convert_string(data)
    elif isinstance(data, dict):
        data = {k: convert_types(v) for k, v in data.items()}
    elif isinstance(data, list):
        data = [convert_types(elem) for elem in data]
    elif isinstance(data, tuple):
        data = tuple(convert_types(elem) for elem in data)
    elif isinstance(data, set):
        data = {convert_types(elem) for elem in data}
    return data


def clean_data(d: Any, remove_empty: bool = True, remove_none: bool = True) -> Any:
    """Recursively removes empty lists and dicts and none from a dict"""
    # log.debug("Cleaning up %s", json_dump(d))
    if isinstance(d, str):
        return convert_string(d)
    if not isinstance(d, (list, dict, set, tuple)):
        return d

    if isinstance(d, (list, set, tuple)):
        # Remove empty strings and nones
        if remove_none:
            d = [elem for elem in d if elem is not None]
        if remove_empty:
            d = [elem for elem in d if not isinstance(elem, (str, list, dict, tuple, set)) or len(elem) != 0]
        return [clean_data(elem, remove_empty, remove_none) for elem in d]

    # Remove empty dict string values
    if remove_none:
        d = {k: v for k, v in d.items() if v is not None}
    if remove_empty:
        d = {k: v for k, v in d.items() if not isinstance(v, (str, list, dict, tuple, set)) or len(v) != 0}

    # Recurse
    return {k: clean_data(v, remove_empty, remove_none) for k, v in d.items()}


def remove_nones(d: Any) -> Any:
    """Removes elements of the data that are None values"""
    return clean_data(d, remove_empty=False, remove_none=True)


def sort_lists(data: Any) -> Any:
    """Recursively sort lists in a dict or list, and redact tokens if needed"""
    if isinstance(data, (list, set, tuple)):
        if len(data) > 0 and isinstance(data[0], (str, int, float)):
            return sorted(data)
        return [sort_lists(elem) for elem in data]
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (list, set, tuple)) and len(v) > 0 and isinstance(v[0], (str, int, float)):
                data[k] = sorted(v)
            elif isinstance(v, dict):
                data[k] = sort_lists(v)
    return data


def json_dump(jsondata: Union[list[str], dict[str, str]], indent: int = 3, sort_keys: bool = False) -> str:
    """JSON dump helper"""
    newdata = sort_lists(deepcopy(jsondata))
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


def dict_subset(d: dict[str, str], key_subset: list[str]) -> dict[str, str]:
    """Returns the subset of dict only with subset_list keys"""
    return {key: d[key] for key in key_subset if key in d}


def allowed_values_string(original_str: str, allowed_values: list[str]) -> str:
    """Returns CSV values from an allowed list"""
    return list_to_csv([v for v in csv_to_list(original_str) if v in allowed_values])


def none_to_zero(d: dict[str, Any], key_match: str = "^.+$") -> dict[str, Any]:
    """Replaces None values in a dict with 0"""
    new_d = d.copy()
    for k, v in d.items():
        if v is None and re.match(key_match, k):
            new_d[k] = 0
        elif isinstance(v, dict):
            new_d[k] = none_to_zero(v)
        elif isinstance(v, list):
            v = [0 if elem is None else elem for elem in v]
            new_d[k] = [none_to_zero(elem) if isinstance(elem, dict) else elem for elem in v]
    return new_d


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


def format_date(somedate: datetime.datetime) -> str:
    """Returns a date as an ISO string"""
    return ISO_DATE_FORMAT % (somedate.year, somedate.month, somedate.day)


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
        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
    delta = now - some_date
    return delta.days if rounded else delta


def order_dict(d: dict[str, Any], *key_order: str) -> dict[str, Any]:
    """Orders keys of a dictionary in a given order"""
    new_d = {k: d[k] for k in key_order if k in d}
    return new_d | {k: v for k, v in d.items() if k not in new_d}


def __prefix(value: Any) -> Any:
    """Recursively places all keys in a dict or list by a prefixed version"""
    if isinstance(value, dict):
        return {f"_{k}": __prefix(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [__prefix(v) for v in value]
    else:
        return value


def replace_keys(key_list: list[str], new_key: str, data: dict[str, any]) -> dict[str, any]:
    """Replace a list of old keys by a new key in a dict"""
    for k in key_list:
        if k in data:
            data[new_key] = data.pop(k)
    return data


def filter_export(json_data: dict[str, Any], key_properties: Union[list[str], tuple[str, ...]], full: bool) -> dict[str, Any]:
    """Filters dict for export removing or prefixing non-key properties"""
    new_json_data = {k: json_data[k] for k in key_properties if k in json_data}
    if full:
        new_json_data |= {f"_{k}": __prefix(v) for k, v in json_data.items() if k not in key_properties}
    return new_json_data


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


def dict_add(dict1: dict[str, int], dict2: dict[str, int]) -> dict[str, int]:
    """Adds values of 2 dicts"""
    return {k: dict1.get(k, 0) + dict2.get(k, 0) for k in dict1.keys() | dict2.keys()}


def start_clock() -> datetime.datetime:
    """Returns the now timestamp"""
    return datetime.datetime.now()


def sort_list_by_key(list_to_sort: list[dict[str, Any]], key: str, priority_field: Optional[str] = None) -> list[dict[str, Any]]:
    """Sorts a list of dicts by a given key, exception for the priority field that would go first"""
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


def deduct_format(fmt: Union[str, None], filename: Union[str, None], allowed_formats: tuple[str] = ("csv", "json")) -> str:
    """Deducts output format from CLI format and filename"""
    if fmt is None and filename is not None:
        fmt = filename.split(".").pop(-1).lower()
        if fmt == "yml":
            fmt = "yaml"
    if fmt not in allowed_formats:
        fmt = "csv"
    return fmt


def dict_remap(original_dict: dict[str, Any], remapping: dict[str, str]) -> dict[str, Any]:
    """Key old keys by new key in a dict"""
    if not original_dict:
        return {}
    return {remapping.get(k, k): v for k, v in original_dict.items()}


def class_name(obj: object) -> str:
    """Returns the class name of an object"""
    return type(obj).__name__


@contextlib.contextmanager
def open_file(file: Optional[str] = None, mode: str = "w") -> Generator[TextIO, None, None]:
    """Opens a file if not None or -, otherwise stdout"""
    if file and file != "-":
        # log.debug("Opening file '%s' in directory '%s'", file, os.getcwd())
        fd = open(file=file, mode=mode, encoding="utf-8", newline="")
    else:
        # log.debug("Writing to stdout")
        fd = sys.stdout
    try:
        yield fd
    finally:
        if fd is not sys.stdout:
            fd.close()


def pretty_print_json(file: str) -> bool:
    """Opens and reformats a JSON file"""
    try:
        with open_file(file, mode="r") as fd:
            json_data = json.loads(fd.read())
        with open_file(file, mode="w") as fd:
            print(json_dump(json_data, sort_keys=True), file=fd)
    except json.decoder.JSONDecodeError:
        # log.warning("File %s is not correct JSON, cannot pretty print", file)
        return False
    return True


def search_list(obj_list: list[Any], field: str, value: str) -> dict[str, Any]:
    """Returns the first dict elem in a list whose given field is a given value"""
    return next((elem for elem in obj_list if elem[field] == value), None)
