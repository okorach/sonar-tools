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
from sonar import branches, projects, settings, exceptions
import sonar.util.constants as c


def test_set_single_valued() -> None:
    """test_set_single_valued_setting"""
    if tutil.SQ.is_sonarcloud():
        # On SonarCloud, test a project-level integer setting: CPD minimum token count
        proj = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
        o = settings.Setting.get_object(tutil.SQ, "sonar.cpd.minimumTokens", proj)
        assert o is not None
        assert o.set(200)
        assert o.value == 200
        assert o.set(50)
        assert o.value == 50
        assert o.reset()
        assert o.is_default_value()
    else:
        o = settings.Setting.get_object(tutil.SQ, "sonar.dbcleaner.daysBeforeDeletingClosedIssues")
        assert o.value == 30
        assert o.set(60)
        assert o.value == 60
        assert o.reset()
        assert o.value == 30


def test_set_boolean() -> None:
    """test_set_boolean_setting"""
    if tutil.SQ.is_sonarcloud():
        # On SonarCloud, test a project-level boolean setting: SCM disabled
        proj = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
        o = settings.Setting.get_object(tutil.SQ, "sonar.scm.disabled", proj)
        assert o is not None
        assert o.value is False
        assert o.set(True)
        assert o.value is True
        assert o.reset()
        assert o.value is False
    else:
        o = settings.Setting.get_object(tutil.SQ, "sonar.cpd.cross_project")
        assert o.value is False
        assert o.set(True)
        assert o.value is True
        assert o.reset()
        assert o.value is False


def test_multi_valued() -> None:
    """test_multi_valued"""
    if tutil.SQ.is_sonarcloud():
        # On SonarCloud, use project-level exclusions on the live project (Python repo)
        proj = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
        o = settings.Setting.get_object(tutil.SQ, "sonar.exclusions", proj)
        assert o is not None
        orig = list(o.value) if o.value else []
        assert o.set(["**/*.foo", "**/*.bar"])
        assert sorted(o.value) == sorted(["**/*.foo", "**/*.bar"])
        assert o.set(["**/*.foo", "**/*.bar", "**/*.baz"])
        assert sorted(o.value) == sorted(["**/*.foo", "**/*.bar", "**/*.baz"])
        assert o.reset()
        assert sorted(o.value) == sorted(orig)
    else:
        proj1 = projects.Project.get_object(tutil.SQ, tutil.PROJECT_1)
        o = settings.Setting.get_object(tutil.SQ, "sonar.java.file.suffixes", proj1)
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
    if tutil.SQ.is_sonarcloud():
        pytest.skip("MQR mode is a SonarQube Server-only concept")
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
    if tutil.SQ.is_sonarcloud():
        pytest.skip("sonar.core.startTime and sonar.auth.github.apiUrl are SonarQube Server-only settings")
    o = settings.Setting.get_object(tutil.SQ, "sonar.core.startTime")
    assert o is not None
    assert not o.set("2025-01-01")
    o = settings.Setting.get_object(tutil.SQ, "sonar.auth.github.apiUrl")
    assert o is not None
    res = True if tutil.SQ.version() < (10, 0, 0) else False
    assert o.set("https://api.github.com/") == res


def test_is_default_value() -> None:
    """test_is_default_value"""
    if tutil.SQ.is_sonarcloud():
        # On SonarCloud, test project-level exclusions: default is empty
        proj = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
        o = settings.Setting.get_object(tutil.SQ, "sonar.exclusions", proj)
        assert o is not None
        assert o.is_default_value()
        assert o.set(["**/*.generated.py"])
        assert not o.is_default_value()
        assert o.reset()
        assert o.is_default_value()
    else:
        o = settings.Setting.get_object(tutil.SQ, "sonar.python.file.suffixes")
        assert o is not None
        assert o.is_default_value()
        assert o.set([".py", ".pyw", ".pyx", ".pyz"])
        assert not o.is_default_value()
        assert o.reset()
        assert o.is_default_value()


def test_visi_cache() -> None:
    """test_visi_cache"""
    if tutil.SQ.is_sonarcloud():
        pytest.skip("Project default visibility does not exist on SonarQube Cloud")
    o = settings.Setting.get_visibility(tutil.SQ)
    assert o is not None
    assert settings.Setting.get_visibility(tutil.SQ) is o


def test_set_visibility() -> None:
    """test_set_visibility"""
    if tutil.SQ.is_sonarcloud():
        pytest.skip("Project visibility cannot be changed via settings API on SonarQube Cloud")
    proj1 = projects.Project.get_object(tutil.SQ, tutil.PROJECT_1)
    settings.set_visibility(tutil.SQ, "private", component=proj1)
    o = settings.Setting.get_visibility(tutil.SQ, component=proj1)
    assert o.value == "private"
    settings.set_visibility(tutil.SQ, "public", component=proj1)
    o.refresh()
    assert o.value == "public"
    settings.set_visibility(tutil.SQ, "private", component=proj1)
    o.refresh()
    assert o.value == "private"


def test_set_new_code_period() -> None:
    """test_set_new_code_period"""
    if tutil.SQ.is_sonarcloud():
        # On SonarCloud, test org-level new code period (no project_key)
        assert settings.set_new_code_period(tutil.SQ, "NUMBER_OF_DAYS", 42)
        o = settings.get_new_code_period(tutil.SQ)
        assert o.value == "NUMBER_OF_DAYS = 42"
        # Legacy alias DAYS must be normalized to NUMBER_OF_DAYS at the API boundary.
        assert settings.set_new_code_period(tutil.SQ, "DAYS", 30)
        o = settings.get_new_code_period(tutil.SQ)
        assert o.value == "NUMBER_OF_DAYS = 30"
        # Restore to PREVIOUS_VERSION
        assert settings.set_new_code_period(tutil.SQ, "PREVIOUS_VERSION", None)
    else:
        proj1 = projects.Project.get_object(tutil.SQ, tutil.PROJECT_1)
        assert settings.set_new_code_period(tutil.SQ, "NUMBER_OF_DAYS", 42, component=proj1)
        o = settings.get_new_code_period(tutil.SQ, component=proj1)
        assert o.value == "NUMBER_OF_DAYS = 42"
        # Legacy alias DAYS must be normalized to NUMBER_OF_DAYS at the API boundary.
        assert settings.set_new_code_period(tutil.SQ, "DAYS", 30, component=proj1)
        o = settings.get_new_code_period(tutil.SQ, component=proj1)
        assert o.value == "NUMBER_OF_DAYS = 30"
        if tutil.SQ.version() < (10, 0, 0):
            assert settings.set_new_code_period(tutil.SQ, "SPECIFIC_ANALYSIS", "XXX", component=proj1)
            assert o.value == "SPECIFIC_ANALYSIS = XXX"
        assert settings.set_new_code_period(tutil.SQ, "PREVIOUS_VERSION", None, component=proj1)
        o.refresh()
        assert o.value == "PREVIOUS_VERSION"


def test_is_internal() -> None:
    """test_is_internal"""
    name = "sonar.filesize.limit" if tutil.SQ.is_sonarcloud() else "sonar.plugins.risk.consent"
    assert settings.Setting.get_object(tutil.SQ, name).is_internal()
    if not tutil.SQ.is_sonarcloud():
        assert not settings.Setting.get_object(tutil.SQ, "sonar.python.file.suffixes").is_internal()


def test_set_non_existing() -> None:
    """test_set_non_existing"""
    assert not settings.set_setting(tutil.SQ, "sonar.non.existing.setting", 42)


def test_new_code_to_string() -> None:
    """test_new_code_to_string - pure function, no SonarQube connection needed"""
    assert settings.new_code_to_string(30) == 30
    assert settings.new_code_to_string("NUMBER_OF_DAYS = 30") == "NUMBER_OF_DAYS = 30"
    assert settings.new_code_to_string({"inherited": True}) is None
    assert settings.new_code_to_string({"type": "PREVIOUS_VERSION"}) == "PREVIOUS_VERSION"
    assert settings.new_code_to_string({"type": "SPECIFIC_ANALYSIS", "effectiveValue": "abc123"}) == "SPECIFIC_ANALYSIS = abc123"
    assert settings.new_code_to_string({"type": "NUMBER_OF_DAYS", "value": "30"}) == "NUMBER_OF_DAYS = 30"


def test_string_to_new_code() -> None:
    """test_string_to_new_code - pure function, no SonarQube connection needed"""
    assert settings.string_to_new_code("PREVIOUS_VERSION") == ["PREVIOUS_VERSION"]
    assert settings.string_to_new_code("NUMBER_OF_DAYS = 30") == ["NUMBER_OF_DAYS", "30"]
    assert settings.string_to_new_code("SPECIFIC_ANALYSIS = abc123") == ["SPECIFIC_ANALYSIS", "abc123"]
    assert settings.string_to_new_code("REFERENCE_BRANCH = main") == ["REFERENCE_BRANCH", "main"]


def test_decode() -> None:
    """test_decode - pure function, no SonarQube connection needed"""
    assert settings.decode(settings.NEW_CODE_PERIOD, 30) == ("NUMBER_OF_DAYS", 30)
    assert settings.decode(settings.NEW_CODE_PERIOD, "PREVIOUS_VERSION") == ("PREVIOUS_VERSION", "")
    assert settings.decode(settings.NEW_CODE_PERIOD, "NUMBER_OF_DAYS = 30") == ["NUMBER_OF_DAYS", "30"]
    assert settings.decode("sonar.something", 42) == 42
    decoded = settings.decode("sonar.java.file.suffixes", ".java,.jav")
    assert isinstance(decoded, list)
    assert ".java" in decoded
    assert ".jav" in decoded
    assert settings.decode("sonar.something.unrelated", "plain-string") == "plain-string"


def test_component_is_object() -> None:
    """Verify setting.component stores a Component object (not a string) — core of issue #2232"""
    if not tutil.SQ.is_sonarcloud():
        o_global = settings.Setting.get_object(tutil.SQ, "sonar.python.file.suffixes")
        assert o_global.component is None
        assert o_global.component_key is None
        assert o_global.is_global()

    proj_key = tutil.LIVE_PROJECT if tutil.SQ.is_sonarcloud() else tutil.PROJECT_1
    setting_key = "sonar.exclusions" if tutil.SQ.is_sonarcloud() else "sonar.java.file.suffixes"
    proj = projects.Project.get_object(tutil.SQ, proj_key)
    o = settings.Setting.get_object(tutil.SQ, setting_key, proj)
    assert isinstance(o.component, projects.Project)
    assert o.component_key == proj.key
    assert not o.is_global()


def test_is_global() -> None:
    """test_is_global"""
    o = settings.Setting.get_object(tutil.SQ, "sonar.python.file.suffixes")
    assert o.is_global()
    if not tutil.SQ.is_sonarcloud():
        proj1 = projects.Project.get_object(tutil.SQ, tutil.PROJECT_1)
        o_proj = settings.Setting.get_object(tutil.SQ, "sonar.java.file.suffixes", proj1)
        assert not o_proj.is_global()


def test_category() -> None:
    """test_category"""
    if tutil.SQ.is_sonarcloud():
        pytest.skip("category test uses SonarQube Server-only global settings")
    o = settings.Setting.get_object(tutil.SQ, "sonar.java.file.suffixes")
    assert o.category() == (settings.LANGUAGES_SETTINGS, "java")
    o = settings.Setting.get_object(tutil.SQ, "sonar.python.file.suffixes")
    assert o.category() == (settings.LANGUAGES_SETTINGS, "python")
    o = settings.Setting.get_object(tutil.SQ, "sonar.dbcleaner.daysBeforeDeletingClosedIssues")
    assert o.category() == (settings.GENERAL_SETTINGS, None)
    o = settings.Setting.get_object(tutil.SQ, "sonar.forceAuthentication")
    assert o.category() == (settings.AUTH_SETTINGS, None)


def test_to_json() -> None:
    """test_to_json"""
    if tutil.SQ.is_sonarcloud():
        pytest.skip("test_to_json uses SonarQube Server-only global settings")
    o = settings.Setting.get_object(tutil.SQ, "sonar.python.file.suffixes")
    j = o.to_json()
    assert isinstance(j, dict)
    key = "sonar.python.file.suffixes"
    assert key in j
    assert j[key]["key"] == key
    assert "value" in j[key]
    assert "defaultValue" in j[key]

    o_nc = settings.get_new_code_period(tutil.SQ)
    j_nc = o_nc.to_json()
    assert settings.NEW_CODE_PERIOD in j_nc
    assert "value" in j_nc[settings.NEW_CODE_PERIOD]


def test_search() -> None:
    """test_search"""
    result = settings.Setting.search(tutil.SQ)
    assert isinstance(result, dict)
    assert len(result) > 0
    if not tutil.SQ.is_sonarcloud():
        proj1 = projects.Project.get_object(tutil.SQ, tutil.PROJECT_1)
        result = settings.Setting.search(tutil.SQ, component=proj1)
        assert isinstance(result, dict)
        assert len(result) > 0
        for s in result.values():
            assert s.component is None or s.component_key == proj1.key


def test_new_code_period_branch() -> None:
    """test_new_code_period_branch - verify Branch object can be used as component"""
    if tutil.SQ.is_sonarcloud() or tutil.SQ.edition() not in (c.DE, c.EE, c.DCE):
        pytest.skip("Branch-level settings require SonarQube Server Developer Edition or higher")
    proj = projects.Project.get_object(tutil.SQ, tutil.PROJ_WITH_BRANCHES)
    branch = branches.Branch.get_object(tutil.SQ, proj, tutil.BRANCH_MAIN)
    o = settings.get_new_code_period(tutil.SQ, component=branch)
    assert o is not None
    assert isinstance(o.component, branches.Branch)
    assert o.component_key == proj.key
    assert o.branch == tutil.BRANCH_MAIN
