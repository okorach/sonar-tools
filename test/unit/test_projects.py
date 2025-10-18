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

"""projects tests"""

from collections.abc import Generator
import pytest

from sonar import projects, exceptions, qualityprofiles, qualitygates
from sonar.audit import audit_config
import sonar.util.constants as c

import utilities as tutil


def test_get_object(get_test_project: Generator[projects.Project]) -> None:
    """test_get_object"""
    proj = get_test_project
    assert str(proj) == f"project '{tutil.TEMP_KEY}'"
    with pytest.raises(exceptions.ObjectNotFound):
        projects.Project.get_object(endpoint=tutil.SQ, key=tutil.NON_EXISTING_KEY)


def test_refresh(get_test_project: Generator[projects.Project]) -> None:
    """test_refresh"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.EXISTING_PROJECT)
    proj.refresh()

    proj = get_test_project
    proj.delete()
    with pytest.raises(exceptions.ObjectNotFound):
        proj.refresh()


def test_create_delete() -> None:
    """test_create_delete"""
    proj = projects.Project.create(endpoint=tutil.SQ, key=tutil.TEMP_KEY, name="temp")
    assert proj.key == tutil.TEMP_KEY
    if tutil.SQ.edition() != c.CE:
        assert proj.main_branch().name == "main"
        proj.rename_main_branch("foobar")
        assert proj.main_branch().name == "foobar"
    else:
        assert proj.main_branch_name() == "main"
    assert proj.delete()
    with pytest.raises(exceptions.ObjectNotFound):
        proj.refresh()


def test_audit() -> None:
    """test_audit"""
    import json

    settings = {k: False for k, v in audit_config.load("sonar-audit").items() if isinstance(v, bool)}
    settings["audit.projects"] = True
    for p in (
        "minLocPerAcceptedIssue",
        "minLocPerFalsePositiveIssue",
        "maxLastAnalysisAge",
        "branches.maxLastAnalysisAge",
        "pullRequests.maxLastAnalysisAge",
        "maxNewCodeLines",
    ):
        settings[f"audit.projects.{p}"] = 0
    assert len(projects.audit(tutil.SQ, settings)) == 0
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.LIVE_PROJECT)
    settings["audit.projects.utilityLocs"] = True
    assert len(proj.audit_languages(audit_settings=settings)) == 0
    settings["audit.mode"] = "housekeeper"
    assert len(proj.audit_languages(audit_settings=settings)) == 0


def test_audit_disabled() -> None:
    """test_audit_disabled"""
    assert len(projects.audit(tutil.SQ, {"audit.projects": False})) == 0


def test_revision() -> None:
    """test_revision"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.LIVE_PROJECT)
    assert len(proj.revision()) > 8


def test_export_async() -> None:
    """test_export_async"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.LIVE_PROJECT)
    assert proj.export_zip(asynchronous=True) == ("ASYNC_SUCCESS", None)


def test_export_sync() -> None:
    """test_export_sync"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.LIVE_PROJECT)
    (res, _) = proj.export_zip(asynchronous=False)
    assert res == "SUCCESS"


def test_import_async() -> None:
    """test_import_async"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.PROJECT_1)
    if tutil.SQ.edition() == c.CE:
        with pytest.raises(exceptions.UnsupportedOperation):
            proj.import_zip(asynchronous=True)
    else:
        assert proj.import_zip(asynchronous=True) == "ASYNC_SUCCESS"


def test_import_sync() -> None:
    """test_import_sync"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.PROJECT_1)
    if tutil.SQ.edition() == c.CE:
        with pytest.raises(exceptions.UnsupportedOperation):
            proj.import_zip(asynchronous=False)
    else:
        assert proj.import_zip(asynchronous=False).startswith("FAILED")


def test_import_no_zip(get_test_project: Generator[projects.Project]) -> None:
    """test_import_no_zip"""
    if tutil.SQ.edition() == c.CE:
        pytest.skip("No zip import in Community Build")
    assert get_test_project.import_zip(asynchronous=False) == f"FAILED/ZIP_MISSING"
    get_test_project.key = "non-existing"
    res = get_test_project.import_zip(asynchronous=False)
    assert res.startsWith("FAILED/") and "not found" in res


def test_monorepo() -> None:
    """test_monorepo"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.LIVE_PROJECT)
    assert not proj.is_part_of_monorepo()
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.PROJECT_1)
    assert not proj.is_part_of_monorepo()


def test_get_findings() -> None:
    """test_get_findings"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.LIVE_PROJECT)
    with pytest.raises(exceptions.ObjectNotFound):
        proj.get_findings(branch="non-existing-branch")
    if tutil.SQ.edition() != c.CE:
        assert len(proj.get_findings(branch="develop")) > 0
    with pytest.raises(exceptions.ObjectNotFound):
        proj.get_findings(pr="1")
    assert len(proj.get_findings(pr="5")) == 0


def test_count_third_party_issues() -> None:
    """test_count_third_party_issues"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key="creedengo-issues")
    filters = None
    if tutil.SQ.edition() != c.CE:
        filters = {"branch": "develop"}
    if tutil.SQ.version() >= (10, 0, 0):
        assert len(proj.count_third_party_issues(filters=filters)) > 0
    if tutil.SQ.edition() != c.CE:
        assert len(proj.count_third_party_issues(filters={"branch": "non-existing-branch"})) == 0


def test_webhooks() -> None:
    """test_webhooks"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.LIVE_PROJECT)
    assert len(proj.webhooks()) == 0


def test_versions() -> None:
    """test_versions"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.LIVE_PROJECT)
    vers = proj.get_versions()
    v_list = list(vers.keys())
    assert len(v_list) > 10
    for v in "3.9", "2.11", "2.9", "v1.13":
        assert v in v_list
    if proj.endpoint.version() >= (2025, 1, 0):
        for v in "3.1", "3.4", "3.7":
            assert v in v_list


def test_count() -> None:
    """test_count"""
    assert projects.count(tutil.SQ) > 30


def test_export() -> None:
    """test_export"""
    json_exp = projects.export(endpoint=tutil.SQ, export_settings={})
    yaml_exp = projects.convert_for_yaml(json_exp)
    assert len(json_exp) > 0
    assert isinstance(json_exp, dict)
    assert isinstance(yaml_exp, list)
    assert len(yaml_exp) == len(json_exp)


def test_already_exists() -> None:
    """test_already_exists"""
    with pytest.raises(exceptions.ObjectAlreadyExists):
        projects.Project.create(endpoint=tutil.SQ, key=tutil.EXISTING_PROJECT, name="name")


def test_exists() -> None:
    assert projects.exists(tutil.SQ, tutil.LIVE_PROJECT)
    assert not projects.exists(tutil.SQ, "non-existing")


def test_binding() -> None:
    """test_binding"""
    if tutil.SQ.edition() == c.CE:
        pytest.skip("Bindings unsupported in SonarQube Community Edition")
    proj = projects.Project.get_object(tutil.SQ, "demo:github-actions-maven")
    assert proj.has_binding()
    assert proj.binding() is not None
    assert proj.binding_key().startswith("github:::okorach/demo-actions-maven")
    proj = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
    assert not proj.has_binding()
    assert proj.binding_key() is None


def test_export_wrong_key(get_test_project: Generator[projects.Project]) -> None:
    """test_export_wrong_key"""
    proj = get_test_project
    proj.key = tutil.NON_EXISTING_KEY
    with pytest.raises(exceptions.ObjectNotFound):
        proj.export_zip(asynchronous=True)
    with pytest.raises(exceptions.ObjectNotFound):
        proj.export_zip(asynchronous=False)


def test_import_wrong_key(get_test_project: Generator[projects.Project]) -> None:
    """test_import_wrong_key"""
    proj = get_test_project
    proj.key = tutil.NON_EXISTING_KEY
    if tutil.SQ.edition() in (c.EE, c.DCE):
        assert proj.import_zip(asynchronous=True) == "FAILED/PROJECT_NOT_FOUND"
        assert proj.import_zip(asynchronous=False) == "FAILED/PROJECT_NOT_FOUND"
    else:
        with pytest.raises(exceptions.UnsupportedOperation):
            proj.import_zip(asynchronous=True)
        with pytest.raises(exceptions.UnsupportedOperation):
            proj.import_zip(asynchronous=False)


def test_ci(get_test_project: Generator[projects.Project]) -> None:
    """test_ci"""
    proj = get_test_project
    assert proj.ci() == "unknown"
    proj.key = tutil.NON_EXISTING_KEY
    assert proj.ci() == "unknown"


def test_set_links(get_test_project: Generator[projects.Project]) -> None:
    """test_set_links"""
    proj = get_test_project
    proj.set_links({"links": [{"type": "custom", "name": "google", "url": "https://google.com"}]})
    proj.key = tutil.NON_EXISTING_KEY
    with pytest.raises(exceptions.ObjectNotFound):
        proj.set_links({"links": [{"type": "custom", "name": "yahoo", "url": "https://yahoo.com"}]})


def test_set_tags(get_test_project: Generator[projects.Project]) -> None:
    """test_set_tags"""
    proj = get_test_project

    assert proj.set_tags(tutil.TAGS)
    assert proj.get_tags() == sorted(tutil.TAGS)
    assert proj.set_tags(["foo"])
    assert proj.get_tags() == ["foo"]
    assert proj.set_tags([])
    assert len(proj.get_tags()) == 0
    assert not proj.set_tags(None)


def test_set_quality_gate(get_test_project: Generator[projects.Project], get_test_quality_gate: Generator[qualitygates.QualityGate]) -> None:
    """test_set_quality_gate"""
    proj = get_test_project
    qg = get_test_quality_gate
    assert proj.set_quality_gate(qg.name)
    assert not proj.set_quality_gate(None)
    with pytest.raises(exceptions.ObjectNotFound):
        proj.set_quality_gate(tutil.NON_EXISTING_KEY)

    proj.key = tutil.NON_EXISTING_KEY
    with pytest.raises(exceptions.ObjectNotFound):
        assert not proj.set_quality_gate(qg.name)


def test_ai_code_assurance(get_test_project: Generator[projects.Project]) -> None:
    """test_ai_code_assurance"""
    proj = get_test_project
    if tutil.SQ.version() < (10, 7, 0) or tutil.SQ.edition() == c.CE:
        with pytest.raises(exceptions.UnsupportedOperation):
            proj.get_ai_code_assurance()
        return
    proj = get_test_project
    assert proj.set_contains_ai_code(True)
    assert proj.get_ai_code_assurance() in (
        "CONTAINS_AI_CODE",
        "AI_CODE_ASSURED",
        "AI_CODE_ASSURANCE_ON",
        "AI_CODE_ASSURANCE_OFF",
        "AI_CODE_ASSURANCE_PASS",
        "AI_CODE_ASSURANCE_FAIL",
        "NONE",
    )
    assert proj.set_contains_ai_code(False)
    assert proj.get_ai_code_assurance() == "NONE"
    proj.key = tutil.NON_EXISTING_KEY
    with pytest.raises(exceptions.ObjectNotFound):
        proj.set_contains_ai_code(True)
    with pytest.raises(exceptions.ObjectNotFound):
        assert proj.get_ai_code_assurance()
    with pytest.raises(exceptions.ObjectNotFound):
        proj.set_contains_ai_code(False)
    with pytest.raises(exceptions.ObjectNotFound):
        proj.get_ai_code_assurance()


def test_set_quality_profile(get_test_project: Generator[projects.Project], get_test_qp: Generator[qualityprofiles.QualityProfile]) -> None:
    """test_set_quality_profile"""
    proj = get_test_project
    new_qp = get_test_qp
    assert proj.set_quality_profile(language=new_qp.language, quality_profile=new_qp.name)
    assert not proj.set_quality_profile(language="py", quality_profile=tutil.NON_EXISTING_KEY)
    assert not proj.set_quality_profile(language=tutil.NON_EXISTING_KEY, quality_profile=new_qp.name)
    proj.key = tutil.NON_EXISTING_KEY
    with pytest.raises(exceptions.ObjectNotFound):
        proj.set_quality_profile(language="py", quality_profile=new_qp.name)


def test_branch_and_pr() -> None:
    """test_branch_and_pr"""
    if tutil.SQ.edition() == c.CE:
        pytest.skip("Branches and PR unsupported in SonarQube Community Build")
    proj = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
    assert len(proj.get_branches_and_prs(filters={"branch": "*"})) >= 2
    assert len(proj.get_branches_and_prs(filters={"branch": "foobar"})) == 0
    assert len(proj.get_branches_and_prs(filters={"pullRequest": "*"})) == 2
    assert len(proj.get_branches_and_prs(filters={"pullRequest": "5"})) == 1


def test_audit_languages(get_test_project: Generator[projects.Project]) -> None:
    """test_audit_languages"""
    proj = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
    assert proj.audit_languages({"audit.projects.utilityLocs": False}) == []
    proj = get_test_project
    assert proj.audit_languages({"audit.projects.utilityLocs": True}) == []


def test_wrong_key_2(get_test_project: Generator[projects.Project]) -> None:
    """test_wrong_key"""
    proj = get_test_project
    proj.key = tutil.NON_EXISTING_KEY
    with pytest.raises(exceptions.ObjectNotFound):
        _ = proj.webhooks()
    with pytest.raises(exceptions.ObjectNotFound):
        _ = proj.links()
    # assert proj.quality_gate() is None
    with pytest.raises(exceptions.ObjectNotFound):
        proj.audit({})


def test_set_permissions(get_test_project: Generator[projects.Project]) -> None:
    """test_set_permissions"""
    proj = get_test_project
    perms = proj.permissions().to_json()
    assert "tech-leads" in perms["groups"]
    proj.set_permissions({"users": {"admin": ["admin", "user"], "olivier": ["user"]}})
    # TODO @okorach: If project default visibility is Public the permission count is different
    perms = proj.permissions().to_json()
    assert "groups" not in perms
    assert len(perms["users"]) == 2


def test_project_key(get_test_project: Generator[projects.Project]) -> None:
    """test_project_key"""
    assert get_test_project.project_key() == tutil.TEMP_KEY
