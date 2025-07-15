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
from requests import RequestException

import pytest
import utilities as util
from sonar import platform, settings


def test_system_id() -> None:
    server_id = util.SQ.server_id()
    assert server_id == util.SQ.server_id()
    assert server_id == util.SQ.server_id()


def test_db() -> None:
    assert util.SC.database().lower() == "postgresql"
    assert util.SQ.database().lower() == "postgresql"


def test_plugins() -> None:
    assert util.SC.plugins() == {}


def test_get_set_reset_settings() -> None:
    # util.start_logging()
    assert util.SQ.reset_setting("sonar.exclusions")
    assert util.SQ.get_setting("sonar.exclusions") == ""

    assert util.SQ.set_setting("sonar.exclusions", ["**/*.foo"])
    assert util.SQ.get_setting("sonar.exclusions") == "**/*.foo"

    assert util.SQ.set_setting("sonar.exclusions", ["**/*.foo", "**/*.bar"])
    assert util.SQ.get_setting("sonar.exclusions") == "**/*.foo, **/*.bar"

    assert util.SQ.reset_setting("sonar.exclusions")
    assert util.SQ.get_setting("sonar.exclusions") == ""


def test_import() -> None:
    with open("test/files/config.json", "r", encoding="utf-8") as f:
        json_config = json.load(f)
    json_config["globalSettings"]["generalSettings"][settings.NEW_CODE_PERIOD] = 60
    assert platform.import_config(util.TEST_SQ, json_config) is None

    json_config.pop("globalSettings")
    assert util.TEST_SQ.import_config(json_config) is None


def test_sys_info() -> None:
    data = util.SC.sys_info()
    assert data == {"System": {"Server ID": "sonarcloud"}}

    data = util.SQ.sys_info()
    assert "System" in data


def test_wrong_url() -> None:
    util.TEST_SQ.local_url = "http://localhost:3337"

    util.TEST_SQ._sys_info = None
    with pytest.raises(RequestException):
        util.TEST_SQ.sys_info()

    util.TEST_SQ.global_permissions()


def test_set_webhooks() -> None:
    assert not util.SQ.set_webhooks(None)


def test_normalize_api() -> None:
    normalized_result = "/api/projects/search"
    for input in "/projects/search", "/api/projects/search", "api/projects/search", "projects/search":
        assert platform._normalize_api(input) == normalized_result


def test_convert_for_yaml() -> None:
    with open("test/files/config.json", "r", encoding="utf-8") as f:
        json_config = json.load(f)["globalSettings"]
    yaml_json = platform.convert_for_yaml(json_config.copy())
    assert len(yaml_json) == len(json_config)
