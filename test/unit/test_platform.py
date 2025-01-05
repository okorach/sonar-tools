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

""" platform tests """

import json
import pytest
import utilities as util

def test_system_id() -> None:
    server_id = util.SQ.server_id()
    assert server_id == util.SQ.server_id()
    assert server_id == util.SQ.server_id()

def test_db() -> None:
    assert util.SC.database() == "postgres"
    assert util.SQ.database() == "postgres"

def test_plugins() -> None:
    assert util.SC.plugins() == {}

def test_get_set_reset_settings() -> None:
    assert util.SQ.get_setting("sonar.global.exclusions") == ""

    assert util.SQ.set_setting("sonar.global.exclusions", "**/*.foo")
    assert util.SQ.get_setting("sonar.global.exclusions") == "**/*.foo"

    assert util.SQ.reset_setting("sonar.global.exclusions")
    assert util.SQ.get_setting("sonar.global.exclusions") == ""

def test_import() -> None:
    with open("test/files/config.json", "r", encoding="utf-8") as f:
        json_config = json.load(f)
    assert util.TEST_SQ.import_config(json_config) is None


def test_sys_info() -> None:
    data = util.SC.sys_info()
    assert data == { "System": {"Server ID": "sonarcloud"}}

    data = util.SQ.sys_info()
    assert "System" in data

    url = util.TEST_SQ.url
    util.TEST_SQ.url = "http://localhost:3337"
    with pytest.raises(ConnectionError):
        util.TEST_SQ.sys_info()    
    util.TEST_SQ.url = url


def test_wrong_url() -> None:
    with open("test/files/config.json", "r", encoding="utf-8") as f:
        json_config = json.load(f)
    assert util.TEST_SQ.import_config(json_config) is None
