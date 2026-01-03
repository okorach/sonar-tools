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

"""quality profiles tests"""

from collections.abc import Generator
import json
import pytest

import utilities as tutil
from sonar import qualityprofiles, languages, rules, exceptions, logging
import sonar.util.issue_defs as idefs
import sonar.util.qualityprofile_helper as qhelp


def test_get_object(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    qp = get_test_qp
    assert qp.name == tutil.TEMP_KEY
    assert qp.language == "py"
    qp2 = qualityprofiles.get_object(endpoint=tutil.SQ, name=tutil.TEMP_KEY, language="py")
    assert qp2 is qp


def test_get_object_non_existing() -> None:
    """Test exception raised when providing non existing portfolio key"""

    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = qualityprofiles.get_object(endpoint=tutil.SQ, name="NON-EXISTING", language="py")
    assert str(e.value).endswith("Quality Profile 'py:NON-EXISTING' not found")


def test_exists(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """Test exist"""
    _ = get_test_qp
    assert qualityprofiles.QualityProfile.exists(endpoint=tutil.SQ, name=tutil.TEMP_KEY, language="py")
    assert not qualityprofiles.QualityProfile.exists(endpoint=tutil.SQ, name="NON_EXISTING", language="py")


def test_get_list() -> None:
    """Test QP get_list"""
    qps = qualityprofiles.get_list(endpoint=tutil.SQ)
    assert len(qps) > 25


def test_create_delete(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """Test QP create delete"""
    qp = get_test_qp
    assert qp is not None

    assert qualityprofiles.QualityProfile.create(endpoint=tutil.SQ, name=tutil.TEMP_KEY, language="non-existing") is None

    with pytest.raises(exceptions.ObjectAlreadyExists):
        qualityprofiles.QualityProfile.create(endpoint=tutil.SQ, name=tutil.TEMP_KEY, language="py")
    qp.delete()
    assert not qualityprofiles.QualityProfile.exists(endpoint=tutil.SQ, name=tutil.TEMP_KEY, language="py")


def test_inheritance(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """Test addition of a project in manual mode"""
    qp = get_test_qp
    sonar_way_qp = qualityprofiles.get_object(tutil.SQ, tutil.SONAR_WAY, "py")
    assert not qp.is_child()

    assert qp.set_parent(tutil.SONAR_WAY)
    assert qp.is_child()
    assert qp.inherits_from_built_in()
    assert qp.parent_name == tutil.SONAR_WAY
    assert qp.built_in_parent() is sonar_way_qp

    with pytest.raises(exceptions.ObjectNotFound) as e:
        qp.set_parent("NON-EXISTING")
    assert str(e.value).endswith("Quality Profile 'py:NON-EXISTING' not found")
    assert not qp.set_parent(qp.name)
    assert not qp.set_parent(None)

    assert sonar_way_qp.name == qp.parent_name


def test_read(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """test_read"""
    qp = get_test_qp
    assert qp.url() == f"{tutil.SQ.external_url}/profiles/show?language=py&name={tutil.TEMP_KEY}"
    new_qp = qualityprofiles.QualityProfile.read(tutil.SQ, tutil.TEMP_KEY, "py")
    assert qp is new_qp

    assert qualityprofiles.QualityProfile.read(tutil.SQ, tutil.TEMP_KEY, "non-existing") is None


def test_set_default(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """test_set_default"""
    qp = get_test_qp
    assert not qp.is_default
    assert qp.set_as_default()
    assert qp.is_default
    sonar_way_qp = qualityprofiles.get_object(tutil.SQ, tutil.SONAR_WAY, "py")
    assert sonar_way_qp.set_as_default()
    assert sonar_way_qp.is_default
    assert not qp.is_default


def test_export() -> None:
    """test_export"""
    json_exp = qualityprofiles.export(endpoint=tutil.SQ, export_settings={})
    assert len(json_exp) > 0
    assert isinstance(json_exp, list)


def test_add_remove_rules(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """test_add_remove_rules"""
    qp = get_test_qp
    RULE1, RULE2, RULE3 = "python:S1142", "python:FunctionComplexity", "python:S139"
    ruleset = [
        {"key": RULE1, "impacts": {"maintainability": "medium"}},
        {"key": RULE2, "impacts": {"maintainability": "medium"}},
    ]
    qp.activate_rules(ruleset)
    qp_rules = qp.rules()
    assert sorted(qp_rules.keys()) == sorted([r["key"] for r in ruleset])
    qp.activate_rule(RULE3, impacts={"maintainability": "medium"})
    ruleset.append({"key": RULE3, "impacts": {"maintainability": "medium"}})
    assert sorted(qp.rules().keys()) == sorted([r["key"] for r in ruleset])

    assert len(qp.rules()) == 3
    qp.set_rules([{"key": RULE1}, {"key": RULE2}])
    assert len(qp.rules()) == 2
    qp.set_rules(ruleset)
    assert len(qp.rules()) == 3
    qp.deactivate_rules([RULE1, RULE2])
    assert len(qp.rules()) == 1

    assert qp.set_parent(tutil.SONAR_WAY)
    rulecount = len(qp.rules())
    assert rulecount > 250 if tutil.SQ.version() >= (10, 0, 0) else 200

    assert qp.deactivate_rule(RULE3)
    assert len(qp.rules()) == rulecount - 1


def test_import() -> None:
    """test_import"""
    rules.get_list(tutil.TEST_SQ)
    languages.Language.CACHE.clear()
    qualityprofiles.QualityProfile.CACHE.clear()
    # delete all quality profiles in test
    for qp in qualityprofiles.get_list(tutil.TEST_SQ, use_cache=False).values():
        if qp.name == tutil.SONAR_WAY:
            qp.set_as_default()
    qp_list = {o for o in qualityprofiles.get_list(tutil.TEST_SQ, use_cache=False).values() if not o.is_built_in and not o.is_default}
    for o in qp_list:
        o.delete()
    with open(f"{tutil.FILES_ROOT}/config.json", "r", encoding="utf-8") as f:
        json_exp = json.loads(f.read())["qualityProfiles"]
    assert qualityprofiles.import_config(tutil.TEST_SQ, {"qualityProfiles": json_exp})

    # Compare QP list
    json_name_list = sorted([qp["name"] for qp in qhelp.flatten(json_exp) if not qp.get("isBuiltIn", False)])
    qp_name_list = sorted([f"{o.language}:{o.name}" for o in qualityprofiles.get_list(tutil.TEST_SQ, use_cache=False).values() if not o.is_built_in])
    logging.debug("Imported  list = %s", str(json_name_list))
    logging.debug("SonarQube list = %s", str(qp_name_list))
    assert json_name_list == qp_name_list
    languages.Language.CACHE.clear()
    qualityprofiles.QualityProfile.CACHE.clear()


def test_audit_disabled() -> None:
    """test_audit_disabled"""
    assert len(qualityprofiles.audit(tutil.SQ, {"audit.qualityProfiles": False})) == 0
