#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2024 Olivier Korach
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

""" projects tests """

import pytest

import utilities as util
from sonar import projects, exceptions
from sonar.audit import config

NON_EXISTING_KEY = "NON_EXISTING"
TEST_KEY = "MY_PROJ"


def test_get_object() -> None:
    """test_get_object"""
    proj = projects.Project.get_object(endpoint=util.SQ, key=util.LIVE_PROJECT)
    assert proj.key == util.LIVE_PROJECT
    assert str(proj) == f"project '{util.LIVE_PROJECT}'"
    proj.refresh()
    with pytest.raises(exceptions.ObjectNotFound):
        projects.Project.get_object(endpoint=util.SQ, key=NON_EXISTING_KEY)


def test_create_delete() -> None:
    """test_create_delete"""
    proj = projects.Project.create(endpoint=util.SQ, key=TEST_KEY, name=TEST_KEY)
    assert proj.key == TEST_KEY
    assert proj.main_branch().name == "main"
    proj.rename_main_branch("foobar")
    assert proj.main_branch().name == "foobar"
    assert proj.delete()


def test_audit() -> None:
    """test_audit"""
    settings = {k: False for k in config.load("sonar-audit")}
    settings["audit.projects"] = True
    assert len(projects.audit(util.SQ, settings)) == 0
    proj = projects.Project.get_object(endpoint=util.SQ, key=util.LIVE_PROJECT)
    settings["audit.projects.utilityLocs"] = True
    assert len(proj.audit_languages(audit_settings=settings)) == 0


def test_revision() -> None:
    """test_revision"""
    proj = projects.Project.get_object(endpoint=util.SQ, key=util.LIVE_PROJECT)
    assert len(proj.revision()) > 8


def test_export_async() -> None:
    """test_export_async"""
    proj = projects.Project.get_object(endpoint=util.SQ, key=util.LIVE_PROJECT)
    assert proj.export_async() is not None


def test_get_findings() -> None:
    """test_get_findings"""
    proj = projects.Project.get_object(endpoint=util.SQ, key=util.LIVE_PROJECT)
    assert len(proj.get_findings(branch="non-existing-branch")) == 0
    assert len(proj.get_findings(branch="develop")) > 0
    assert len(proj.get_findings(pr="1")) == 0


def test_count_third_party_issues() -> None:
    """test_get_findings"""
    proj = projects.Project.get_object(endpoint=util.SQ, key=util.LIVE_PROJECT)
    assert len(proj.count_third_party_issues(filters={"branch": "develop"})) > 0
    assert len(proj.get_findings(branch="develop")) > 0
    assert len(proj.get_findings(pr="1")) == 0


def test_webhooks() -> None:
    """test_get_findings"""
    proj = projects.Project.get_object(endpoint=util.SQ, key=util.LIVE_PROJECT)
    assert len(proj.webhooks()) == 0


def test_count() -> None:
    """test_count"""
    assert projects.count(util.SQ) > 30


def test_convert_for_yaml() -> None:
    """test_convert_for_yaml"""
    a_json = projects.export(endpoint=util.SQ, export_settings={})
    assert isinstance(projects.convert_for_yaml(a_json), list)
