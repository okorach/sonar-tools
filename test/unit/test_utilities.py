#!/usr/bin/env python3
#
# sonar-tools tests
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

"""utilities tests"""

import pytest
import sonar.utilities as sutil
import sonar.util.misc as util
from sonar import exceptions
from datetime import datetime


def test_token_type() -> None:
    """test_token_type"""
    token = "x" * 40
    assert sutil.token_type("sqt_" + token) == "user"
    assert sutil.token_type("sqa_" + token) == "global-analysis"
    assert sutil.token_type("sqp_" + token) == "project-analysis"
    assert sutil.token_type(token) == "user"
    for i in range(50):
        if i in (40, 44):
            continue
        assert sutil.token_type("x" * i) == "wrong format"


def test_check_token() -> None:
    """test_check_token"""
    with pytest.raises(exceptions.SonarException):
        sutil.check_token(None)

    token = "x" * 40
    with pytest.raises(exceptions.SonarException):
        sutil.check_token("sqa_" + token)
    with pytest.raises(exceptions.SonarException):
        sutil.check_token("sqp_" + token)
    assert sutil.check_token("squ_" + token) is None
    with pytest.raises(exceptions.SonarException):
        sutil.check_token(token[:30])
    assert sutil.check_token(token, is_sonarcloud=True) is None


def test_format_date() -> None:
    """test_format_date"""
    assert util.format_date(datetime(2024, 6, 15, 10, 22, 7)) == "2024-06-15"


def test_get_setting() -> None:
    """test_get_setting"""
    settings = {"a": 1, "b": 2}
    assert sutil.get_setting(settings, "a", 5) == 1
    assert sutil.get_setting(None, "a", 5) == 5
    assert sutil.get_setting(settings, "c", 8) == 8


def test_jvm_heap() -> None:
    """test_jvm_heap"""
    assert sutil.jvm_heap("-Xmx512M -Xms256M") == 512
    assert sutil.jvm_heap(" -Xms256M -ffoobar  -Xmx512m") == 512
    assert sutil.jvm_heap("-Xms1G -Xmx2g") == 2048
    assert sutil.jvm_heap("-Xmx10240K -Xms5120K") == 10
    assert sutil.jvm_heap("-Xmx10r") is None
    assert sutil.jvm_heap("-Xmxinvalid -Xms256M") is None
    assert sutil.jvm_heap("") is None


def test_int_memory() -> None:
    """test_int_memory"""
    assert sutil.int_memory("512 MB") == 512
    assert sutil.int_memory("2 GB") == 2048
    assert sutil.int_memory("1.5 GB") == 1536
    assert sutil.int_memory("1,5 GB") == 1536
    assert sutil.int_memory("10240 KB") == 10
    assert sutil.int_memory("10 TB") == 10 * 1024 * 1024
    assert sutil.int_memory("10 PB") == 10 * 1024 * 1024 * 1024
    assert sutil.int_memory("2048 KB") == 2
    assert sutil.int_memory("1048576 bytes") == 1
    assert sutil.int_memory("invalid") is None
    assert sutil.int_memory("") is None


def test_convert_string() -> None:
    """test_convert_string"""
    assert sutil.convert_string("yes") is True
    assert sutil.convert_string("False") is False
    assert sutil.convert_string("123") == 123
    assert sutil.convert_string("12.34") - 12.34 < 0.0001
    assert sutil.convert_string("some string") == "some string"
    assert sutil.convert_string([1, 2, 3]) == [1, 2, 3]


def test_edition_normalize() -> None:
    """test_edition_normalize"""
    assert sutil.edition_normalize("Developer Edition") == "developer"
    assert sutil.edition_normalize("enterprise edition") == "enterprise"
    assert sutil.edition_normalize("Community Edition") == "community"
    assert sutil.edition_normalize("unknown") == "unknown"
    assert sutil.edition_normalize(None) is None


def test_string_to_version() -> None:
    """test_string_to_version"""
    assert sutil.string_to_version("10.3.1") == (10, 3, 1)
    assert sutil.string_to_version("9.9.9.19342") == (9, 9, 9)
    assert sutil.string_to_version("9.9.9.19342", 2) == (9, 9)
    assert sutil.string_to_version(None) is None
    assert sutil.string_to_version("10.2") == (10, 2, 0)
    assert sutil.string_to_version("invalid") is None


def test_dict_remap() -> None:
    """test_dict_remap"""
    input_dict = {"a": 1, "b": 2, "c": 3}
    remap = {"a": "alpha", "b": "beta"}
    assert util.dict_remap(input_dict, remap) == {"alpha": 1, "beta": 2, "c": 3}
    assert util.dict_remap(None, remap) == {}


def test_list_to_dict() -> None:
    """test_list_to_dict"""
    input_list = [
        {"letter": "a", "value": 1},
        {"letter": "b", "value": 2},
        {"letter": "c", "value": 3},
    ]
    expected_dict = {
        "a": {"letter": "a", "value": 1},
        "b": {"letter": "b", "value": 2},
        "c": {"letter": "c", "value": 3},
    }
    assert util.list_to_dict(input_list, "letter", keep_in_values=True) == expected_dict
    for v in expected_dict.values():
        v.pop("letter")
    assert util.list_to_dict(input_list, "letter") == expected_dict


def test_to_days() -> None:
    """test_to_days"""
    assert sutil.to_days("10 day") == 10
    assert sutil.to_days("3 weeks") == 21
    assert sutil.to_days("2 months") == 60
    assert sutil.to_days("1 year") == 365
    assert sutil.to_days("5 invalid") is None
    assert sutil.to_days("invalid") is None


def test_none_to_zero() -> None:
    """test_none_to_zero"""
    d = {"a": {"1": None, "2": 0, "3": "foo"}, "b": [5, None, "bar"], "c": None}
    res = util.none_to_zero(d)
    assert res == {"a": {"1": 0, "2": 0, "3": "foo"}, "b": [5, 0, "bar"], "c": 0}


def test_clean_data() -> None:
    """test_clean_data"""
    d = {"a": {"1": None, "2": [], "3": "foo", "4": {}, "5": set(), "6": ()}, "b": [5, {}, [], "bar", set(), ()], "c": "5"}
    res = util.clean_data(d, remove_none=True, remove_empty=True)
    assert res == {"a": {"3": "foo"}, "b": [5, "bar"], "c": 5}


def test_sort_lists() -> None:
    """test_sort_lists"""
    d = {"c": [3, 1, 2], "b": {"y": [5, 4], "x": "foo"}, "a": "bar"}
    res = util.sort_lists(d)
    assert res == {"a": "bar", "b": {"x": "foo", "y": [4, 5]}, "c": [1, 2, 3]}


def test_csv_to_set() -> None:
    """test_csv_to_set"""
    assert util.csv_to_set("a,b,c") == {"a", "b", "c"}
    assert util.csv_to_set("") == set()
    assert util.csv_to_set(None) == set()
    assert util.csv_to_set("  a , b , c  ") == {"a", "b", "c"}
    assert util.csv_to_set([1, 2, 3]) == {1, 2, 3}


def test_list_to_csv() -> None:
    """test_list_to_csv"""
    assert util.list_to_csv(["a", "b", "c"]) == "a,b,c"
    assert util.list_to_csv([]) == ""
    assert util.list_to_csv(None) is None
    assert util.list_to_csv(["  a ", " b ", " c  "]) == "a,b,c"
    assert util.list_to_csv("  a , b , c  ") == "a,b,c"
