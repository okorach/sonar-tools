#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2024-2025 Olivier Korach
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
    test utilities
"""

import os
import sys
import datetime
import re
import csv, json
from typing import Optional, Union
from unittest.mock import patch
import pytest

import credentials as creds
from sonar import logging, exceptions
from sonar import utilities as util
from sonar import platform
import cli.options as opt

TEST_LOGFILE = "pytest.log"
LOGGER_COUNT = 0
FILES_ROOT = "test/files/"

LATEST = "http://localhost:10000"
LTA = "http://localhost:8000"
LTS = LTA
LATEST_TEST = "http://localhost:20010"
CB = "http://localhost:7000"

CSV_FILE = f"temp.{os.getpid()}.csv"
JSON_FILE = f"temp.{os.getpid()}.json"
YAML_FILE = f"temp.{os.getpid()}.yaml"

PROJECT_0 = "okorach_sonar-tools"
PROJECT_1 = "project1"
PROJECT_2 = "project2"
PROJECT_3 = "project3"
PROJECT_4 = "project4"
PROJECT_5 = "project5"

LIVE_PROJECT = PROJECT_0
PROJ_WITH_BRANCHES = PROJECT_1
BRANCH_MAIN = "main"
BRANCH_2 = "develop"
BRANCH_3 = "some-branch"
BRANCH_4 = "feature/new-feature"
BRANCH_5 = "comma,branch"

NON_EXISTING_KEY = "non-existing"

TEST_KEY = "TEST"
EXISTING_QG = TEST_KEY
EXISTING_PROJECT = TEST_KEY
EXISTING_APP = TEST_KEY
EXISTING_PORTFOLIO = TEST_KEY
TEMP_KEY = "TEMP"
TEMP_KEY_2 = "TEMP2"
TEMP_KEY_3 = "TEMP3"
TEMP_NAME = "Temp Name"

STD_OPTS = [f"-{opt.URL_SHORT}", creds.TARGET_PLATFORM, f"-{opt.TOKEN_SHORT}", creds.TARGET_TOKEN]
SQS_OPTS = " ".join(STD_OPTS)

TEST_OPTS = [f"-{opt.URL_SHORT}", LATEST_TEST, f"-{opt.TOKEN_SHORT}", os.getenv("SONAR_TOKEN_TEST_ADMIN_USER")]
SQS_TEST_OPTS = " ".join(TEST_OPTS)

CE_OPTS = [f"-{opt.URL_SHORT}", CB, f"-{opt.TOKEN_SHORT}", creds.TARGET_TOKEN]

SC_TOKEN = os.getenv("SONAR_TOKEN_SONARCLOUD")
SC_URL = "https://sonarcloud.io"
SC_ORG = "okorach"
SC_OPTS_NO_ORG = f"--{opt.URL} {SC_URL} --{opt.TOKEN} {SC_TOKEN}"
SC_OPTS = f"{SC_OPTS_NO_ORG} --{opt.ORG} {SC_ORG}"

SQ = platform.Platform(url=creds.TARGET_PLATFORM, token=creds.TARGET_TOKEN)
SC = platform.Platform(url=SC_URL, token=SC_TOKEN, org="okorach")
TEST_SQ = platform.Platform(url=LATEST_TEST, token=os.getenv("SONAR_TOKEN_TEST_ADMIN_USER"))

TAGS = ["foo", "bar"]

SONAR_WAY = "Sonar way"


def clean(*files: Optional[str]) -> None:
    """Deletes a list of file if they exists"""
    for file in files:
        try:
            if file:
                os.remove(file)
        except FileNotFoundError:
            pass


def file_empty(file: str) -> bool:
    """Returns whether a file exists and is empty"""
    return file_exists(file) and os.stat(file).st_size == 0


def file_exists(file: str) -> bool:
    """Returns whether a file exists"""
    return os.path.isfile(file)


def file_not_empty(file: str) -> bool:
    """Returns whether a file exists and is not empty"""
    if not os.path.isfile(file):
        return False
    return os.stat(file).st_size > 0


def file_contains(file: str, string: str) -> bool:
    """Returns whether a file contains a given string"""
    if not os.path.isfile(file):
        return False
    with open(file=file, mode="r", encoding="utf-8") as fh:
        content = fh.read()
    return string in content


def is_datetime(value: str, allow_empty: bool = False) -> bool:
    """Checks if a string is a date + time"""
    if allow_empty and value == "" or value == "Never":
        return True
    try:
        d = datetime.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return False
    return isinstance(d, datetime.datetime)


def is_date(value: str, allow_empty: bool = False) -> bool:
    """Checks if a string is a date"""
    if allow_empty and value == "" or value == "Never":
        return True
    print(f"{value} {len(value)}")
    try:
        _ = datetime.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return False
    return len(value) == 10


def is_integer(value: str, allow_empty: bool = False) -> bool:
    """Returns whether a string contains an integer or is empty"""
    return (allow_empty and (value == "" or value is None)) or isinstance(int(value), int)


def is_float(value: str, allow_empty: bool = False) -> bool:
    """Returns whether a string contains a float"""
    return (allow_empty and (value == "" or value is None)) or isinstance(float(value), float)


def is_empty(value: str, allow_empty: bool = False) -> bool:
    """Returns whether a value is empty"""
    return value is None or value == ""


def is_pct(value: str, allow_empty: bool = False) -> bool:
    """Returns whether a string contains a float"""
    return (allow_empty and (value == "" or value is None)) or re.match(r"^(100|[1-9]\d|\d)\.\d\%$", value) is not None


def is_float_pct(value: str, allow_empty: bool = False) -> bool:
    """Returns whether a string contains a float between 0.0 and 1.0"""
    return (allow_empty and (value == "" or value is None)) or (is_float(value) and 0 <= float(value) <= 1)


def is_url(value: str, allow_empty: bool = False) -> bool:
    """Returns whether a string contains an URL"""
    return (allow_empty and (value == "" or value is None)) or value.startswith("http")


def __get_args_and_file(string_arguments: str) -> tuple[Optional[str], list[str], bool]:
    """Gets the list arguments and output file of a sonar-tools cmd"""
    args = __split_args(string_arguments)
    imp_cmd = False
    for option in (f"-{opt.IMPORT_SHORT}", f"--{opt.IMPORT}"):
        try:
            imp_cmd = args.index(option) is not None
            break
        except ValueError:
            pass
    index = len(args)
    file = None
    for arg in reversed(args):
        last = index
        if arg in (f"-{opt.REPORT_FILE_SHORT}", f"--{opt.REPORT_FILE}"):
            file = args[last] if last < len(args) else None
            break
        index -= 1
    return file, args, imp_cmd


def __split_args(string_arguments: str) -> list[str]:
    return [s.strip('"') for s in re.findall(r'(?:[^\s\*"]|"(?:\\.|[^"])*")+', string_arguments)]


def __get_option_index(args: Union[str, list[str]], option: str) -> Optional[str]:
    if isinstance(args, str):
        args = __split_args(args)
    return args.index(option) + 1


def __get_redacted_cmd(string_arguments: str) -> str:
    """Gets a cmd line and redacts the token"""
    args = __split_args(string_arguments)
    for option in (f"-{opt.TOKEN_SHORT}", f"--{opt.TOKEN}", "-T", "--tokenTarget"):
        try:
            ndx = __get_option_index(args, option)
            args[ndx] = util.redacted_token(args[ndx])
        except ValueError:
            pass
    return " ".join(args)


def run_cmd(func: callable, arguments: str, delete_file: bool = False) -> int:
    """Runs a sonar-tools command, and returns the expected code"""
    logging.info("RUNNING: %s", __get_redacted_cmd(arguments))
    file, args, import_cmd = __get_args_and_file(arguments)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", args):
            func()
    if delete_file and not import_cmd:
        clean(file)
    return int(str(e.value))


def start_logging(level: str = "DEBUG") -> None:
    """start_logging"""
    global LOGGER_COUNT
    if LOGGER_COUNT == 0:
        logging.set_logger(TEST_LOGFILE)
        logging.set_debug_level(level)
        LOGGER_COUNT = 1


def verify_support(editions: tuple[str, ...], func: callable, **kwargs) -> bool:
    if kwargs["endpoint"].edition() not in editions:
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = func(**kwargs)
        return False
    return True


def get_cols(header_row: list[str], *fields) -> tuple[int, ...]:
    h = header_row.copy()
    h[0] = h[0].lstrip("# ")
    return (h.index(k) for k in fields)


def csv_cols_present(csv_file: str, *col_names) -> bool:
    """Verifies that given columns of a CSV exists"""
    with open(csv_file, encoding="utf-8") as fd:
        row = next(csv.reader(fd))
    row[0] = row[0][2:]
    return all(col in row for col in col_names)


def csv_col_is_value(csv_file: str, col_name: str, *values) -> bool:
    """Verifies that the column of a CSV is a given value for all rows"""
    with open(csv_file, encoding="utf-8") as fd:
        (col,) = get_cols(next(reader := csv.reader(fd)), col_name)
        return all(row[col] in values for row in reader)


def csv_col_has_values(csv_file: str, col_name: str, *values) -> bool:
    values_to_search = list(values).copy()
    with open(csv_file, encoding="utf-8") as fd:
        (col,) = get_cols(next(reader := csv.reader(fd)), col_name)
        for line in reader:
            if line[col] in values_to_search:
                values_to_search.remove(line[col])
            if len(values_to_search) == 0:
                return True
        return False

def csv_col_count_values(csv_file: str, col_name: str, *values) -> int:
    values_to_search = list(values).copy()
    with open(csv_file, encoding="utf-8") as fd:
        (col,) = get_cols(next(reader := csv.reader(fd)), col_name)
        counter = sum(1 if line[col] in values_to_search else 0 for line in reader)
    return counter

def csv_nbr_lines(csv_file: str) -> int:
    """return nbr lines in a CSV file"""
    with open(csv_file, encoding="utf-8") as fd:
        return len(fd.readlines()) - 1  # skip header


def csv_nbr_cols(csv_file: str, nbr_cols: int) -> bool:
    """return whether all rows of a CSV have the given number of columns"""
    with open(csv_file, encoding="utf-8") as fd:
        return all(len(row) == nbr_cols for row in csv.reader(fd))


def csv_col_sorted(csv_file: str, col_name: str) -> bool:
    """return whether a CSV file is sorted by a given column"""
    with open(csv_file, encoding="utf-8") as fd:
        (col,) = get_cols(next(reader := csv.reader(fd)), col_name)
        next(reader)
        last_value = ""
        for row in reader:
            if row[col] < last_value:
                return False
            last_value = row[col]
        return True


def csv_col_match(csv_file: str, col_name: str, regexp: str) -> bool:
    """return whether a CSV column matches a regexp"""
    with open(csv_file, encoding="utf-8") as fd:
        (col,) = get_cols(next(reader := csv.reader(fd)), col_name)
        return all(re.match(rf"{regexp}", row[col]) for row in reader)


def csv_col_condition(csv_file: str, col_name: str, func: callable, allow_empty: bool = False) -> bool:
    """Return whether all lines of the CSV meet a condition on a column"""
    with open(csv_file, encoding="utf-8") as fd:
        (col,) = get_cols(next(reader := csv.reader(fd)), col_name)
        return all(func(row[col], allow_empty) for row in reader)


def csv_col_int(csv_file: str, col_name: str, allow_empty: bool = True) -> bool:
    """return whether a CSV field is an integer"""
    return csv_col_condition(csv_file, col_name, is_integer, allow_empty)


def csv_col_float(csv_file: str, col_name: str, allow_empty: bool = True) -> bool:
    """return whether a CSV col is a float"""
    return csv_col_condition(csv_file, col_name, is_float, allow_empty)


def csv_col_float_pct(csv_file: str, col_name: str, allow_empty: bool = True) -> bool:
    """return whether a CSV col is a float between 0 and 1"""
    return csv_col_condition(csv_file, col_name, is_float_pct, allow_empty)


def csv_col_pct(csv_file: str, col_name: str, allow_empty: bool = True) -> bool:
    """return whether a CSV col is an float between 0.0% and 100.0%"""
    return csv_col_condition(csv_file, col_name, is_pct, allow_empty)


def csv_col_datetime(csv_file: str, col_name: str, allow_empty: bool = True) -> bool:
    """return whether a CSV col is a datetime or empty"""
    return csv_col_condition(csv_file, col_name, is_datetime, allow_empty)


def csv_col_date(csv_file: str, col_name: str, allow_empty: bool = True) -> bool:
    """return whether a CSV col is a date or empty"""
    return csv_col_condition(csv_file, col_name, is_date, allow_empty)


def csv_col_url(csv_file: str, col_name: str, allow_empty: bool = False) -> bool:
    """return whether a CSV col is and URL"""
    return csv_col_condition(csv_file, col_name, is_url, allow_empty)


def csv_col_not_all_empty(csv_file: str, col_name: str) -> bool:
    """return whether not all values of a CSV column are empty"""
    return not csv_col_condition(csv_file, col_name, is_empty)


def json_field_sorted(json_file: str, field: str) -> bool:
    """return whether a JSON file is sorted by a given field"""
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        data = json.loads(fh.read())
    last_key = ""
    for p in data:
        if last_key > p[field]:
            return False
        last_key = p[field]
    return True


def json_fields_present(json_file: str, *fields) -> bool:
    """return whether a JSON file is present for all elements of the JSON"""
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        data = json.loads(fh.read())
    return sum(1 for p in data for field in fields if field not in p) == 0


def json_fields_absent(json_file: str, *fields) -> bool:
    """return whether a JSON file is absent for all elements of the JSON"""
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        data = json.loads(fh.read())
    return sum(1 for p in data for field in fields if field in p) == 0


def json_field_not_all_empty(csv_file: str, col_name: str) -> bool:
    """return whether not all values of a JSON are empty"""
    return not json_field_condition(csv_file, col_name, is_empty)


def json_field_match(json_file: str, field: str, regexp: str, allow_null: bool = False) -> bool:
    """return whether a JSON field matches a regexp"""
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        data = json.loads(fh.read())
    if allow_null:
        return sum(1 for p in data if field in p and p[field] is not None and not re.match(rf"{regexp}", p[field])) == 0
    else:
        return sum(1 for p in data if not re.match(rf"{regexp}", p[field])) == 0


def json_field_condition(json_file: str, field: str, func: callable, allow_null: bool = False) -> bool:
    """return whether a JSON field matches a regexp"""
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        data = json.loads(fh.read())
    if allow_null:
        return sum(1 for p in data if field in p and p[field] is not None and not func(p[field], allow_null)) == 0
    else:
        return sum(1 for p in data if not func(p[field], allow_null)) == 0


def json_field_int(json_file: str, field: str, allow_null: bool = True) -> bool:
    """return whether a JSON field is an integer"""
    return json_field_condition(json_file, field, is_integer, allow_null)


def json_field_float(json_file: str, field: str, allow_null: bool = True) -> bool:
    """return whether a JSON field is a float"""
    return json_field_condition(json_file, field, is_float, allow_null)


def json_field_float_pct(json_file: str, field: str, allow_null: bool = True) -> bool:
    """return whether a JSON field is a float between 0.0 and 1.0"""
    return json_field_condition(json_file, field, is_float_pct, allow_null)


def json_field_pct(json_file: str, field: str, allow_null: bool = True) -> bool:
    """return whether a JSON field is a % between 0.0% and 100.0%"""
    return json_field_condition(json_file, field, is_pct, allow_null)


def json_field_datetime(json_file: str, field: str, allow_null: bool = True) -> bool:
    """return whether a JSON field is a datetime or empty"""
    return json_field_condition(json_file, field, is_datetime, allow_null)


def json_field_date(json_file: str, field: str, allow_null: bool = True) -> bool:
    """return whether a JSON field is a datetime or empty"""
    return json_field_condition(json_file, field, is_date, allow_null)


def json_field_url(json_file: str, field: str, allow_null: bool = False) -> bool:
    """return whether a JSON field is and URL"""
    return json_field_condition(json_file, field, is_url, allow_null)
