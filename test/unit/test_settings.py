# sonar-tools tests
# Copyright (C) 2026 Olivier Korach
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

"""Test of settings"""

import pytest
import utilities as tutil
from sonar import settings, exceptions


def test_set_single_valued() -> None:
    """test_set_single_valued_setting"""
    o = settings.Setting.get_object(tutil.SQ, "sonar.dbcleaner.daysBeforeDeletingClosedIssues")
    assert o.value == 30
    assert o.set(60)
    assert o.value == 60
    assert o.reset()
    assert o.value == 30


def test_set_boolean() -> None:
    """test_set_boolean_setting"""
    o = settings.Setting.get_object(tutil.SQ, "sonar.cpd.cross_project")
    assert o.value is False
    assert o.set(True)
    assert o.value is True
    assert o.reset()
    assert o.value is False


def test_multi_valued() -> None:
    """test_multi_valued"""
    o = settings.Setting.get_object(tutil.SQ, "sonar.java.file.suffixes", tutil.PROJECT_1)
    assert o.set([".jav", ".java", ".javacard"])
    assert sorted(o.value) == sorted([".jav", ".java", ".javacard"])
    assert o.set([".jav", ".java", ".javacard", ".jah"])
    assert sorted(o.value) == sorted([".jav", ".java", ".javacard", ".jah"])
    assert o.reset()
    assert sorted(o.value) == sorted([".jav", ".java"])


def test_autodetect_ai() -> None:
    """test_autodetect_ai"""
    # Even if invisible in the UI, the setting is present in the API in Community Builds
    if tutil.SQ.version() < (10, 8, 0):
        with pytest.raises(exceptions.ObjectNotFound):
            settings.Setting.get_object(tutil.SQ, "sonar.autodetect.ai.code")
        return

    o = settings.Setting.get_object(tutil.SQ, "sonar.autodetect.ai.code")
    if tutil.SQ.version() < (2025, 1, 0):
        return

    val = o.value
    assert o.set(True)
    assert o.value
    assert o.set(False)
    assert not o.value
    assert o.set(val)


def test_mqr_mode() -> None:
    """test_mqr_mode"""
    o = settings.Setting.get_object(tutil.SQ, "sonar.multi-quality-mode.enabled")
    if tutil.SQ.version() < (25, 0, 0):
        assert o is None
        return
    val = o.value
    assert o.set(True)
    assert o.value
    assert o.set(False)
    assert not o.value
    assert o.set(val)


def test_unsettable() -> None:
    """test_unsettable"""
    o = settings.Setting.get_object(tutil.SQ, "sonar.core.startTime")
    assert o is not None
    assert not o.set("2025-01-01")
    o = settings.Setting.get_object(tutil.SQ, "sonar.auth.github.apiUrl")
    assert o is not None
    res = True if tutil.SQ.version() < (10, 0, 0) else False
    assert o.set("https://api.github.com/") == res


def test_is_default_value() -> None:
    """test_is_default_value"""
    o = settings.Setting.get_object(tutil.SQ, "sonar.python.file.suffixes")
    assert o is not None
    assert o.is_default_value()
    assert o.set([".py", ".pyw", ".pyx", ".pyz"])
    assert not o.is_default_value()
    assert o.reset()
    assert o.is_default_value()


def test_visi_cache() -> None:
    """test_visi_cache"""
    o = settings.Setting.get_visibility(tutil.SQ)
    assert o is not None
    assert settings.Setting.get_visibility(tutil.SQ) is o


def test_set_visibility() -> None:
    """test_set_visibility"""
    o = settings.Setting.get_visibility(tutil.SQ, component=tutil.PROJECT_1)
    assert o.value == "private"
    settings.set_visibility(tutil.SQ, "public", component=tutil.PROJECT_1)
    o.refresh()
    assert o.value == "public"
    settings.set_visibility(tutil.SQ, "private", component=tutil.PROJECT_1)
    o.refresh()
    assert o.value == "private"


def test_set_new_code_period() -> None:
    """test_set_new_code_period"""
    assert settings.set_new_code_period(tutil.SQ, "DAYS", 42, project_key=tutil.PROJECT_1)
    o = settings.get_new_code_period(tutil.SQ, component=tutil.PROJECT_1)
    assert o.value == "DAYS = 42"
    assert settings.set_new_code_period(tutil.SQ, "SPECIFIC_ANALYSIS", "XXX", project_key=tutil.PROJECT_1)
    assert o.value == "SPECIFIC_ANALYSIS = XXX"
    assert o.reset()
    assert o.value == "PREVIOUS_VERSION"


def test_is_internal() -> None:
    """test_is_internal"""
    name = "sonar.filesize.limit" if tutil.SQ.is_sonarcloud() else "sonar.plugins.risk.consent"
    assert settings.Setting.get_object(tutil.SQ, name).is_internal()
    assert not settings.Setting.get_object(tutil.SQ, "sonar.python.file.suffixes").is_internal()


def test_set_non_existing() -> None:
    """test_set_non_existing"""
    assert not settings.set_setting(tutil.SQ, "sonar.non.existing.setting", 42)
