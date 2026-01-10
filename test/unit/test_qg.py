#
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

"""quality gates tests"""

from collections.abc import Generator
import pytest

import utilities as tutil
from sonar import qualitygates, exceptions, logging
from sonar.util import constants as c


def test_get_object(get_loaded_qg: Generator[qualitygates.QualityGate]) -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    qg = get_loaded_qg
    assert qg.name.startswith(f"{tutil.TEMP_KEY}-qualitygate")
    assert str(qg) == f"quality gate '{qg.name}'"
    assert qg.url() == f"{tutil.SQ.external_url}/quality_gates/show/{qg.key}"
    qg2 = qualitygates.QualityGate.get_object(endpoint=tutil.SQ, name=qg.name)
    assert qg.projects() == {}
    assert qg2 is qg


def test_get_object_non_existing() -> None:
    """Test exception raised when providing non existing portfolio key"""

    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = qualitygates.QualityGate.get_object(endpoint=tutil.SQ, name=tutil.NON_EXISTING_KEY)
    assert str(e.value).endswith(f"Quality gate '{tutil.NON_EXISTING_KEY}' not found")


def test_exists(get_loaded_qg: Generator[qualitygates.QualityGate]) -> None:
    """Test exist"""
    qg = get_loaded_qg
    assert qualitygates.QualityGate.exists(endpoint=tutil.SQ, name=qg.name)
    assert not qualitygates.QualityGate.exists(endpoint=tutil.SQ, name=tutil.NON_EXISTING_KEY)


def test_search() -> None:
    """Test QP search"""
    assert len(qualitygates.QualityGate.search(tutil.SQ)) >= 5

def test_search_with_cache() -> None:
    """Test QP search with cache"""
    qp1 = qualitygates.QualityGate.search(tutil.SQ, use_cache=False)
    qp2 = qualitygates.QualityGate.search(tutil.SQ, use_cache=True)
    assert sorted(qp1.keys()) == sorted(qp2.keys())

def test_create_delete(get_loaded_qg: Generator[qualitygates.QualityGate]) -> None:
    """Test QG create delete"""
    qp = get_loaded_qg
    assert qp is not None

    with pytest.raises(exceptions.ObjectAlreadyExists):
        qualitygates.QualityGate.create(endpoint=tutil.SQ, name=qp.name)
    qp.delete()
    assert not qualitygates.QualityGate.exists(endpoint=tutil.SQ, name=qp.name)


def test_set_conditions(get_loaded_qg: Generator[qualitygates.QualityGate]) -> None:
    """test_set_conditions"""
    qg = get_loaded_qg
    sw = qualitygates.QualityGate.get_object(tutil.SQ, tutil.SONAR_WAY)
    assert sorted(qg.conditions(encoded=True)) == sorted(sw.conditions(encoded=True))
    qg.clear_conditions()
    assert qg.set_conditions(None)
    assert qg.set_conditions([])
    assert qg.set_conditions(["new_coverage <= 80"])
    assert qg.conditions(encoded=True) == ["new_coverage <= 80%"]
    assert qg.set_conditions(["new_coverage <= 75%"])
    assert qg.conditions(encoded=True) == ["new_coverage <= 75%"]
    qg.clear_conditions()
    assert qg.conditions() == []
    assert qg.set_conditions(["new_coverage <= 80%"])
    assert qg.conditions(encoded=True) == ["new_coverage <= 80%"]
    assert qg.set_conditions(["new_coverage <= 50%", "new_violations >= 0", "test_success_density <= 100"])
    assert qg.conditions(encoded=True) == ["new_coverage <= 50%", "new_violations >= 0", "test_success_density <= 100%"]


def test_clear_conditions(get_loaded_qg: Generator[qualitygates.QualityGate]) -> None:
    """test_clear_conditions"""
    sw = qualitygates.QualityGate.get_object(tutil.SQ, tutil.SONAR_WAY)
    assert not sw.clear_conditions()
    assert len(sw.conditions()) >= 3

    qg = get_loaded_qg
    assert len(qg.conditions()) >= 3
    assert qg.clear_conditions()
    assert len(qg.conditions()) == 0
    assert qg.conditions() == []


def test_permissions(get_loaded_qg: Generator[qualitygates.QualityGate]) -> None:
    """test_permissions"""
    qg = get_loaded_qg
    assert qg.set_permissions({"users": ["olivier", "michal"]})


def test_copy(get_loaded_qg: Generator[qualitygates.QualityGate]) -> None:
    """test_copy"""
    qg = get_loaded_qg
    assert qg.set_conditions(["new_coverage <= 50", "new_violations >= 0", "test_success_density <= 100%"])

    qg2 = qg.copy("TEMP_NAME2")
    assert qg2.conditions(encoded=True) == ["new_coverage <= 50%", "new_violations >= 0", "test_success_density <= 100%"]
    qg2.delete()


def test_set_as_default(get_loaded_qg: Generator[qualitygates.QualityGate]) -> None:
    """test_set_as_default"""
    qg = get_loaded_qg
    sw = qualitygates.QualityGate.get_object(tutil.SQ, tutil.SONAR_WAY)
    assert sw.is_built_in
    qg.set_conditions(["new_coverage <= 50", "new_violations >= 0", "test_success_density <= 100%"])
    assert qg.set_as_default()
    assert not sw.is_default
    assert sw.is_built_in


def test_audit(get_empty_qg: Generator[qualitygates.QualityGate]) -> None:
    """test_audit"""
    qg = get_empty_qg
    for pb in qg.audit():
        logging.debug(str(pb))
    assert len(qg.audit()) == 2
    qg.set_conditions(["new_coverage <= 50", "new_duplicated_lines_density >= 3"])
    assert len(qg.audit()) == 1
    conds = [
        "new_coverage <= 80",
        "new_duplicated_lines_density >= 3",
        "new_security_hotspots_reviewed <= 100",
        "new_technical_debt >= 1000",
        "comment_lines_density <= 10",
        "coverage <= 20",
    ]
    qg.set_conditions(conds)
    assert len(qg.audit({"audit.qualitygates.maxConditions": 5})) >= 2


def test_count():
    count = qualitygates.count(tutil.SQ)
    assert count >= 5
    qg = qualitygates.QualityGate.create(tutil.SQ, tutil.TEMP_KEY)
    assert qualitygates.count(tutil.SQ) == count + 1
    qg.delete()
    assert qualitygates.count(tutil.SQ) == count


def test_export() -> None:
    """test_export"""
    json_exp = qualitygates.export(endpoint=tutil.SQ, export_settings={})
    _PERCENTAGE_METRICS = ("density", "ratio", "percent", "security_hotspots_reviewed", "coverage")
    for qg in json_exp:
        for cond in qg.get("conditions", []):
            if any(d in cond for d in _PERCENTAGE_METRICS):
                assert cond.endswith("%")

    assert len(json_exp) > 0
    assert isinstance(json_exp, list)


def test_audit_disabled() -> None:
    """test_audit_disabled"""
    assert len(qualitygates.audit(tutil.SQ, {"audit.qualityGates": False})) == 0


def test_import_config() -> None:
    """test_import_config"""
    try:
        qg = qualitygates.QualityGate.get_object(tutil.SQ, "TEMP GATE")
        qg.delete()
    except exceptions.ObjectNotFound:
        pass
    conds = ["new_duplicated_lines_density >= 3%"]
    if tutil.SQ.version() < c.MQR_INTRO_VERSION:
        conds += [
            "new_bugs >= 0",
            "new_vulnerabilities >= 0",
            "new_maintainability_rating >= A",
        ]
    else:
        conds += [
            "new_software_quality_maintainability_rating >= A",
            "new_software_quality_reliability_issues >= 0",
            "new_software_quality_security_issues >= 0",
        ]
    conf = {"qualityGates": [{"name": "TEMP GATE", "conditions": conds}]}
    assert qualitygates.import_config(tutil.SQ, conf)
    qg = qualitygates.QualityGate.get_object(tutil.SQ, "TEMP GATE")
    assert len(qg.conditions()) == 4
    assert conf["qualityGates"][0]["conditions"] == qg.conditions(encoded=True)
    qg.delete()
