#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2024 Olivier Korach
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
""" sonarcloud tests """

import os
import sys
from unittest.mock import patch
import pytest

import utilities as util
from sonar import errcodes, exceptions
from sonar import organizations
import cli.options as opt
from cli import config

CMD = "config.py"
SC_OPTS = [f"-{opt.URL_SHORT}", "https://sonarcloud.io", f"-{opt.TOKEN_SHORT}", os.getenv("SONAR_TOKEN_SONARCLOUD")]

OPTS = [CMD] + SC_OPTS + [f"-{opt.EXPORT_SHORT}", f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]
MY_ORG_1 = "okorach"
MY_ORG_2 = "okorach-github"


def test_sc_config_export() -> None:
    """test_sc_config_export"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS + [f"-{opt.ORG_SHORT}", "okorach"]):
            config.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_sc_config_export_no_org() -> None:
    """test_sc_config_export"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS):
            config.main()
    assert int(str(e.value)) == errcodes.ARGS_ERROR
    assert not os.path.isfile(util.JSON_FILE)


def test_org_search() -> None:
    """test_org_search"""
    org_list = organizations.search(endpoint=util.SC)
    assert MY_ORG_1 in org_list
    assert MY_ORG_2 in org_list


def test_org_get_list() -> None:
    """test_org_search"""
    org_list = organizations.get_list(endpoint=util.SC)
    assert MY_ORG_1 in org_list
    assert MY_ORG_2 in org_list

    org_list = organizations.get_list(endpoint=util.SC, key_list=[MY_ORG_1])
    assert MY_ORG_1 in org_list
    assert MY_ORG_2 not in org_list


def test_org_get_non_existing() -> None:
    """test_org_search_sq"""
    with pytest.raises(exceptions.ObjectNotFound):
        _ = organizations.Organization.get_object(endpoint=util.SC, key="oko_foo_bar")

    with pytest.raises(exceptions.ObjectNotFound):
        _ = organizations.get_list(endpoint=util.SC, key_list=["oko_foo_bar"])


def test_org_str() -> None:
    """test_org_str"""
    org = organizations.Organization.get_object(endpoint=util.SC, key=MY_ORG_1)
    assert str(org) == f"organization key '{MY_ORG_1}'"


def test_org_export() -> None:
    """test_org_export"""
    org = organizations.Organization.get_object(endpoint=util.SC, key=MY_ORG_1)
    exp = org.export()
    assert "newCodePeriod" in exp


def test_org_attr() -> None:
    """test_org_attr"""
    org = organizations.Organization.get_object(endpoint=util.SC, key=MY_ORG_1)
    assert org.key == MY_ORG_1
    assert org.name == "Olivier Korach"
    assert org._json["url"] == "https://github.com/okorach"
    (nc_type, nc_val) = org.new_code_period()
    assert nc_type == "PREVIOUS_VERSION"
    assert org.subscription() == "FREE"
    assert org.alm()["key"] == "github"


def test_org_search_sq() -> None:
    """test_org_search_sq"""
    with pytest.raises(exceptions.UnsupportedOperation):
        _ = organizations.search(endpoint=util.SQ)

    with pytest.raises(exceptions.UnsupportedOperation):
        _ = organizations.get_list(endpoint=util.SQ)
