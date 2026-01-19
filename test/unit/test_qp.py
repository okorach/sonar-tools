#
# sonar-tools tests
# Copyright (C) 2024-2026 Olivier Korach
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
from sonar import qualityprofiles, languages, rules, exceptions
import sonar.logging as log
from sonar.qualityprofiles import QualityProfile
import sonar.util.qualityprofile_helper as qhelp


def test_get_object(get_test_qp: Generator[QualityProfile]) -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    qp: QualityProfile = get_test_qp
    assert qp.name.startswith(f"{tutil.TEMP_KEY}-qualityprofile")
    assert qp.language == "py"
    qp2 = QualityProfile.get_object(endpoint=tutil.SQ, name=qp.name, language="py")
    assert qp2 is qp


def test_get_object_non_existing() -> None:
    """Test exception raised when providing non existing portfolio key"""

    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = QualityProfile.get_object(endpoint=tutil.SQ, name="NON-EXISTING", language="py")
    assert str(e.value).endswith("Quality Profile 'py:NON-EXISTING' not found")


def test_exists(get_test_qp: Generator[QualityProfile]) -> None:
    """Test exist"""
    qp = get_test_qp
    assert QualityProfile.exists(endpoint=tutil.SQ, name=qp.name, language="py")
    assert not QualityProfile.exists(endpoint=tutil.SQ, name="NON_EXISTING", language="py")


def test_get_list() -> None:
    """Test QP get_list"""
    qps = QualityProfile.search(tutil.SQ)
    assert len(qps) > 25


def test_create_delete(get_test_qp: Generator[QualityProfile]) -> None:
    """Test QP create delete"""
    qp: QualityProfile = get_test_qp
    assert qp is not None

    with pytest.raises(exceptions.ObjectNotFound):
        QualityProfile.create(endpoint=tutil.SQ, name=qp.name, language="non-existing")

    with pytest.raises(exceptions.ObjectAlreadyExists):
        QualityProfile.create(endpoint=tutil.SQ, name=qp.name, language="py")
    qp.delete()
    assert not QualityProfile.exists(endpoint=tutil.SQ, name=qp.name, language="py")


def test_inheritance(get_test_qp: Generator[QualityProfile]) -> None:
    """Test addition of a project in manual mode"""
    qp: QualityProfile = get_test_qp
    sonar_way_qp = QualityProfile.get_object(tutil.SQ, tutil.SONAR_WAY, "py")
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


def test_read(get_test_qp: Generator[QualityProfile]) -> None:
    """test_read"""
    qp: QualityProfile = get_test_qp
    assert qp.url() == f"{tutil.SQ.external_url}/profiles/show?language=py&name={qp.name}"
    new_qp = QualityProfile.get_object(tutil.SQ, qp.name, "py")
    assert qp is new_qp

    with pytest.raises(exceptions.ObjectNotFound):
        QualityProfile.get_object(tutil.SQ, qp.name, "non-existing")


def test_set_default(get_test_qp: Generator[QualityProfile]) -> None:
    """test_set_default"""
    qp: QualityProfile = get_test_qp
    assert not qp.is_default
    assert qp.set_as_default()
    assert qp.is_default
    sonar_way_qp = QualityProfile.get_object(tutil.SQ, tutil.SONAR_WAY, "py")
    assert sonar_way_qp.set_as_default()
    assert sonar_way_qp.is_default
    assert not qp.is_default


def test_export() -> None:
    """test_export"""
    json_exp = qualityprofiles.export(endpoint=tutil.SQ, export_settings={})
    assert len(json_exp) > 0
    assert isinstance(json_exp, list)


def test_add_remove_rules(get_test_qp: Generator[QualityProfile]) -> None:
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
    rules.Rule.search(tutil.TEST_SQ)
    languages.Language.CACHE.clear()
    QualityProfile.CACHE.clear()
    # Make Sonar Way the default quality profile and delete all quality profiles in test
    for qp in [qp for qp in QualityProfile.search(tutil.TEST_SQ, use_cache=False).values() if qp.name == tutil.SONAR_WAY]:
        qp.set_as_default()
    for qp in [qp for qp in QualityProfile.search(tutil.TEST_SQ, use_cache=False).values() if not qp.is_built_in and not qp.is_default]:
        qp.delete()
    # Import quality profiles from config.json
    with open(f"{tutil.FILES_ROOT}/config.json", "r", encoding="utf-8") as f:
        json_exp = json.loads(f.read())["qualityProfiles"]
    assert qualityprofiles.import_config(tutil.TEST_SQ, {"qualityProfiles": json_exp})

    # Compare QP list
    json_name_list = sorted([qp["name"] for qp in qhelp.flatten(json_exp) if not qp.get("isBuiltIn", False)])
    qp_list = QualityProfile.search(tutil.TEST_SQ, use_cache=False).values()
    log.debug("QP list = %s", [o.name for o in qp_list])
    qp_name_list = sorted([f"{o.language}:{o.name}" for o in qp_list if not o.is_built_in])
    log.debug("Imported  list = %s", str(json_name_list))
    log.debug("SonarQube list = %s", str(qp_name_list))
    assert json_name_list == qp_name_list
    languages.Language.CACHE.clear()
    QualityProfile.CACHE.clear()


def test_audit_disabled() -> None:
    """test_audit_disabled"""
    assert len(qualityprofiles.audit(tutil.SQ, {"audit.qualityProfiles": False})) == 0
