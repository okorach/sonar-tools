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

"""platform tests"""

import json
import requests.exceptions
from datetime import datetime

import pytest
import utilities as tutil
from sonar import settings
from sonar import platform
import sonar.util.update_center as uc
import sonar.util.platform_helper as phelp
from sonar.audit import rules


def test_system_id() -> None:
    server_id = tutil.SQ.server_id()
    assert server_id == tutil.SQ.server_id()
    assert server_id == tutil.SQ.server_id()


def test_db() -> None:
    assert tutil.SC.database().lower() == "postgresql"
    assert tutil.SQ.database().lower() == "postgresql"


def test_plugins() -> None:
    assert tutil.SC.plugins() == {}


def test_get_set_reset_settings() -> None:
    # util.start_logging()
    assert tutil.SQ.reset_setting("sonar.exclusions")
    assert tutil.SQ.get_setting("sonar.exclusions") == []

    assert tutil.SQ.set_setting("sonar.exclusions", ["**/*.foo"])
    assert tutil.SQ.get_setting("sonar.exclusions") == ["**/*.foo"]

    assert tutil.SQ.set_setting("sonar.exclusions", ["**/*.foo", "**/*.bar"])
    assert tutil.SQ.get_setting("sonar.exclusions") == ["**/*.foo", "**/*.bar"]

    assert tutil.SQ.reset_setting("sonar.exclusions")
    assert tutil.SQ.get_setting("sonar.exclusions") == []


def test_import() -> None:
    with open(f"{tutil.FILES_ROOT}/config.json", "r", encoding="utf-8") as f:
        json_config = json.load(f)
    nc = next((s for s in json_config["globalSettings"]["generalSettings"] if s["key"] == settings.NEW_CODE_PERIOD), None)
    nc["value"] = "NUMBER_OF_DAYS = 60"
    platform.import_config(tutil.TEST_SQ, json_config)

    json_config.pop("globalSettings")
    tutil.TEST_SQ.import_config(json_config)


def test_sys_info() -> None:
    data = tutil.SC.sys_info()
    assert data == {"System": {"Server ID": "sonarcloud"}}

    data = tutil.SQ.sys_info()
    assert "System" in data


def test_wrong_url() -> None:
    tutil.TEST_SQ.local_url = "http://localhost:3337"

    tutil.TEST_SQ._sys_info = None
    with pytest.raises(requests.exceptions.ConnectionError):
        tutil.TEST_SQ.sys_info()

    with pytest.raises(requests.exceptions.ConnectionError):
        tutil.TEST_SQ.global_permissions()


def test_set_webhooks() -> None:
    assert not tutil.SQ.set_webhooks(None)


def test_normalize_api() -> None:
    normalized_result = "/api/projects/search"
    for input in "/projects/search", "/api/projects/search", "api/projects/search", "projects/search":
        assert phelp.normalize_api(input) == normalized_result


def test_release_date() -> None:
    assert datetime(2022, 1, 1).date() < tutil.SQ.release_date() <= datetime.today().date()
    assert tutil.SC.release_date() is None


def test_version() -> None:
    """test_version"""
    if tutil.SQ.is_sonarcloud():
        assert tutil.SQ.version() == (0, 0, 0)
    else:
        assert tutil.SQ.version() >= (9, 9, 0)


def test_lta_latest() -> None:
    """Tests that problem is raised if server is not LTA or LATEST"""
    if tutil.SQ.is_sonarcloud():
        assert len(tutil.SQ.audit_lta_latest()) == 0
    else:
        lta = uc.get_lta()
        latest = uc.get_latest()
        sq_version = tutil.SQ.version()
        pbs = tutil.SQ.audit_lta_latest()
        if sq_version == lta or sq_version == latest:
            assert pbs == []
        else:
            assert len(pbs) >= 1


def test_mqr_mode() -> None:
    """Tests that MQR mode is properly return"""
    is_mqr = tutil.SQ.is_mqr_mode()
    if tutil.SQ.is_sonarcloud():
        assert is_mqr
    elif tutil.SQ.version() < (10, 2, 0):
        assert not is_mqr
