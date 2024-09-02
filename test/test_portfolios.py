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

""" portfolio tests """

import pytest

import utilities as util
from sonar import portfolios, projects, exceptions, settings

EXISTING_PROJECT = "okorach_sonar-tools"
EXISTING_PORTFOLIO = "PORT_FAV_PROJECTS"
TEST_KEY = "MY_PPPPORTFOLIO_KEY"


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    if util.SQ.edition() in ("community", "developer"):
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = portfolios.Portfolio.get_object(endpoint=util.SQ, key=EXISTING_PORTFOLIO)
    else:
        portf = portfolios.Portfolio.get_object(endpoint=util.SQ, key=EXISTING_PORTFOLIO)
        assert portf.key == EXISTING_PORTFOLIO
        portf2 = portfolios.Portfolio.get_object(endpoint=util.SQ, key=EXISTING_PORTFOLIO)
        assert portf2.key == EXISTING_PORTFOLIO
        assert portf == portf2


def test_get_object_non_existing() -> None:
    """Test exception raised when providing non existing portfolio key"""
    if util.SQ.edition() in ("community", "developer"):
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = portfolios.Portfolio.get_object(endpoint=util.SQ, key="NON_EXISTING")
    else:
        with pytest.raises(exceptions.ObjectNotFound) as e:
            _ = portfolios.Portfolio.get_object(endpoint=util.SQ, key="NON_EXISTING")
        assert str(e.value).endswith("Portfolio key 'NON_EXISTING' not found")


def test_exists() -> None:
    """Test exist"""
    if util.SQ.edition() in ("community", "developer"):
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = portfolios.exists(endpoint=util.SQ, key="PORT_FAV_PROJECTS")
    else:
        assert portfolios.exists(endpoint=util.SQ, key="PORT_FAV_PROJECTS")
        assert not portfolios.exists(endpoint=util.SQ, key="NON_EXISTING")


def test_get_list() -> None:
    """Test portfolio get_list"""
    if util.SQ.edition() in ("community", "developer"):
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = portfolios.get_list(endpoint=util.SQ, key_list="PORT_FAV_PROJECTS,PORTFOLIO_ALL")
    else:
        p_dict = portfolios.get_list(endpoint=util.SQ, key_list="PORT_FAV_PROJECTS,PORTFOLIO_ALL")
        assert "PORT_FAV_PROJECTS" in p_dict
        assert "PORTFOLIO_ALL" in p_dict
        assert len(p_dict) == 2


def test_create_delete() -> None:
    """Test portfolio create delete"""
    if util.SQ.edition() in ("community", "developer"):
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = portfolios.Portfolio.create(endpoint=util.SQ, name="MY PPPPPORFOLIO", key=TEST_KEY, description="Creationtest")
    else:
        portfolios.delete(endpoint=util.SQ, key=TEST_KEY)
        portfolio = portfolios.Portfolio.create(endpoint=util.SQ, name="MY PPPPPORFOLIO", key=TEST_KEY, description="Creationtest")
        assert portfolio is not None
        assert portfolio.key == TEST_KEY
        assert "NONE" in portfolio.selection_mode()
        assert portfolio.name == "MY PPPPPORFOLIO"
        portfolio.delete()
        assert not portfolios.exists(endpoint=util.SQ, key=TEST_KEY)


def test_add_project() -> None:
    """Test addition of a project in manual mode"""
    if util.SQ.edition() in ("community", "developer"):
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = portfolios.Portfolio.create(endpoint=util.SQ, name="A portfolio", key=TEST_KEY, description="Add_project_test")
    else:
        portfolios.delete(endpoint=util.SQ, key=TEST_KEY)
        p = portfolios.Portfolio.create(endpoint=util.SQ, name="A portfolio", key=TEST_KEY, description="Add_project_test")
        assert "NONE" in p.selection_mode()

        project = projects.Project.get_object(endpoint=util.SQ, key="okorach_sonar-tools")
        p.add_projects(None)
        assert "NONE" in p.selection_mode()
        p.add_projects([])
        assert "NONE" in p.selection_mode()
        p.add_projects([project])
        mode = p.selection_mode()
        assert "MANUAL" in mode
        assert mode["MANUAL"] == {"okorach_sonar-tools": settings.DEFAULT_BRANCH}
        assert p.projects() == {"okorach_sonar-tools": settings.DEFAULT_BRANCH}
        p.delete()
        assert not portfolios.exists(endpoint=util.SQ, key=TEST_KEY)


def test_tags_mode() -> None:
    """Test tag mode"""
    if util.SQ.edition() in ("community", "developer"):
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = portfolios.Portfolio.create(endpoint=util.SQ, name="A portfolio", key=TEST_KEY, description="Add_project_test")
    else:
        portfolios.delete(endpoint=util.SQ, key=TEST_KEY)
        p = portfolios.Portfolio.create(endpoint=util.SQ, name="A portfolio", key=TEST_KEY, description="Add_project_test")
        in_tags = ["foss", "favorites"]
        p.set_tags_mode(in_tags)
        mode = p.selection_mode()
        assert "TAGS" in mode and mode["TAGS"].sort() == in_tags.sort()
        assert mode["branch"] == settings.DEFAULT_BRANCH

        p.set_tags_mode(tags=in_tags, branch="some_branch")
        mode = p.selection_mode()
        assert "TAGS" in mode and mode["TAGS"].sort() == in_tags.sort()
        assert mode["branch"] == "some_branch"
        p.delete()
        assert not portfolios.exists(endpoint=util.SQ, key=TEST_KEY)


def test_regexp_mode() -> None:
    """Test regexp mode"""
    if util.SQ.edition() in ("community", "developer"):
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = portfolios.Portfolio.create(endpoint=util.SQ, name="A portfolio", key=TEST_KEY, description="Add_project_test")
    else:
        portfolios.delete(endpoint=util.SQ, key=TEST_KEY)
        p = portfolios.Portfolio.create(endpoint=util.SQ, name="A portfolio", key=TEST_KEY, description="Add_project_test")
        in_regexp = "^FAVORITES.*$"
        p.set_regexp_mode(in_regexp)
        mode = p.selection_mode()
        assert "REGEXP" in mode and mode["REGEXP"] == in_regexp
        assert "branch" in mode and mode["branch"] == settings.DEFAULT_BRANCH

        in_regexp = "^BRANCH_FAVORITES.*$"
        p.set_regexp_mode(regexp=in_regexp, branch="develop")
        mode = p.selection_mode()
        assert "REGEXP" in mode and mode["REGEXP"] == in_regexp
        assert "branch" in mode and mode["branch"] == "develop"
        p.delete()
        assert not portfolios.exists(endpoint=util.SQ, key=TEST_KEY)


def test_permissions_1() -> None:
    """Test permissions"""
    if util.SQ.edition() in ("community", "developer"):
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = portfolios.Portfolio.create(endpoint=util.SQ, name="A portfolio", key=TEST_KEY, description="Add_project_test")
    else:
        portfolios.delete(endpoint=util.SQ, key=TEST_KEY)
        p = portfolios.Portfolio.create(endpoint=util.SQ, name="A portfolio", key=TEST_KEY, description="Add_project_test")
        p.set_permissions({"groups": {"sonar-users": ["user", "admin"], "sonar-administrators": ["user", "admin"]}})
        # assert p.permissions().to_json()["groups"] == {"sonar-users": ["user", "admin"], "sonar-administrators": ["user", "admin"]}
        p.delete()
        assert not portfolios.exists(endpoint=util.SQ, key=TEST_KEY)


def test_permissions_2() -> None:
    """Test permissions"""
    if util.SQ.edition() in ("community", "developer"):
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = portfolios.Portfolio.create(endpoint=util.SQ, name="A portfolio", key=TEST_KEY, description="Add_project_test", visibility="private")
    else:
        portfolios.delete(endpoint=util.SQ, key=TEST_KEY)
        p = portfolios.Portfolio.create(endpoint=util.SQ, name="A portfolio", key=TEST_KEY, description="Add_project_test", visibility="private")
        p.set_permissions({"groups": {"sonar-users": ["user"], "sonar-administrators": ["user", "admin"]}})
        # assert p.permissions().to_json()["groups"] == {"sonar-users": ["user"], "sonar-administrators": ["user", "admin"]}
        p.delete()
        assert not portfolios.exists(endpoint=util.SQ, key=TEST_KEY)
