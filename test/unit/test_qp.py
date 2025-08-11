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

""" quality profiles tests """

from collections.abc import Generator
import json
import pytest

import utilities as util
from sonar import qualityprofiles, rules, exceptions, logging


def test_get_object(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    qp = get_test_qp
    assert qp.name == util.TEMP_KEY
    assert qp.language == "py"
    qp2 = qualityprofiles.get_object(endpoint=util.SQ, name=util.TEMP_KEY, language="py")
    assert qp2 is qp


def test_get_object_non_existing() -> None:
    """Test exception raised when providing non existing portfolio key"""

    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = qualityprofiles.get_object(endpoint=util.SQ, name="NON-EXISTING", language="py")
    assert str(e.value).endswith("Quality Profile 'py:NON-EXISTING' not found")


def test_exists(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """Test exist"""
    _ = get_test_qp
    assert qualityprofiles.exists(endpoint=util.SQ, name=util.TEMP_KEY, language="py")
    assert not qualityprofiles.exists(endpoint=util.SQ, name="NON_EXISTING", language="py")


def test_get_list() -> None:
    """Test QP get_list"""
    qps = qualityprofiles.get_list(endpoint=util.SQ)
    assert len(qps) > 25


def test_create_delete(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """Test QP create delete"""
    qp = get_test_qp
    assert qp is not None

    assert qualityprofiles.QualityProfile.create(endpoint=util.SQ, name=util.TEMP_KEY, language="non-existing") is None

    with pytest.raises(exceptions.ObjectAlreadyExists):
        qualityprofiles.QualityProfile.create(endpoint=util.SQ, name=util.TEMP_KEY, language="py")
    qp.delete()
    assert not qualityprofiles.exists(endpoint=util.SQ, name=util.TEMP_KEY, language="py")


def test_inheritance(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """Test addition of a project in manual mode"""
    qp = get_test_qp
    sonar_way_qp = qualityprofiles.get_object(util.SQ, util.SONAR_WAY, "py")
    assert not qp.is_child()

    assert qp.set_parent(util.SONAR_WAY)
    assert qp.is_child()
    assert qp.inherits_from_built_in()
    assert qp.parent_name == util.SONAR_WAY
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
    assert qp.url() == f"{util.SQ.external_url}/profiles/show?language=py&name={util.TEMP_KEY}"
    new_qp = qualityprofiles.QualityProfile.read(util.SQ, util.TEMP_KEY, "py")
    assert qp is new_qp

    assert qualityprofiles.QualityProfile.read(util.SQ, util.TEMP_KEY, "non-existing") is None


def test_set_default(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """test_set_default"""
    qp = get_test_qp
    assert not qp.is_default
    assert qp.set_as_default()
    assert qp.is_default
    sonar_way_qp = qualityprofiles.get_object(util.SQ, util.SONAR_WAY, "py")
    assert sonar_way_qp.set_as_default()
    assert sonar_way_qp.is_default
    assert not qp.is_default


def test_export() -> None:
    """test_export"""
    json_exp = qualityprofiles.export(endpoint=util.SQ, export_settings={})
    yaml_exp = qualityprofiles.convert_for_yaml(json_exp)
    assert len(json_exp) > 0
    assert isinstance(json_exp, dict)
    assert isinstance(yaml_exp, list)
    assert len(yaml_exp) == len(json_exp)


def test_add_remove_rules(get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """test_add_remove_rules"""
    qp = get_test_qp
    RULE1, RULE2, RULE3 = "python:S1142", "python:FunctionComplexity", "python:S139"
    ruleset = [{"key": RULE1, "severities": {"MAINTAINABILITY": "MAJOR"}}, {"key": RULE2, "severities": {"MAINTAINABILITY": "MAJOR"}}]
    qp.activate_rules(ruleset)
    qp_rules = qp.rules()
    assert sorted(list(qp_rules.keys())) == sorted([r["key"] for r in ruleset])
    qp.activate_rule(RULE3, "MAJOR")
    ruleset.append({"key": RULE3, "severities": {"MAINTAINABILITY": "MAJOR"}})
    assert sorted(list(qp.rules().keys())) == sorted([r["key"] for r in ruleset])

    assert len(qp.rules()) == 3
    qp.set_rules([{"key": RULE1}, {"key": RULE2}])
    assert len(qp.rules()) == 2
    qp.set_rules(ruleset)
    assert len(qp.rules()) == 3
    qp.deactivate_rules([RULE1, RULE2])
    assert len(qp.rules()) == 1

    assert qp.set_parent(util.SONAR_WAY)
    rulecount = len(qp.rules())
    assert rulecount > 250 if util.SQ.version() >= (10, 0, 0) else 200

    assert qp.deactivate_rule(RULE3)
    assert len(qp.rules()) == rulecount - 1


def test_import() -> None:
    """test_import"""
    rules.get_list(util.TEST_SQ)
    # delete all quality profiles in test
    _ = [qp.set_as_default() for qp in qualityprofiles.get_list(util.TEST_SQ).values() if qp.name == util.SONAR_WAY]
    qp_list = set(o for o in qualityprofiles.get_list(util.TEST_SQ, use_cache=False).values() if not o.is_built_in and not o.is_default)
    _ = [o.delete() for o in qp_list]
    with open("test/files/config.json", "r", encoding="utf-8") as f:
        json_exp = json.loads(f.read())["qualityProfiles"]
    assert qualityprofiles.import_config(util.TEST_SQ, {"qualityProfiles": json_exp})

    # Compare QP list
    json_name_list = sorted([k for k, v in qualityprofiles.flatten(json_exp).items() if not v.get("isBuiltIn", False)])
    qp_name_list = sorted([f"{o.language}:{o.name}" for o in qualityprofiles.get_list(util.TEST_SQ, use_cache=False).values() if not o.is_built_in])
    logging.debug("Imported  list = %s", str(json_name_list))
    logging.debug("SonarQube list = %s", str(qp_name_list))
    assert json_name_list == qp_name_list


def test_audit_disabled() -> None:
    """test_audit_disabled"""
    assert len(qualityprofiles.audit(util.SQ, {"audit.qualityProfiles": False})) == 0
