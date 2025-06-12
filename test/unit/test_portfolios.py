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

""" portfolio tests """

from collections.abc import Generator
import time
import json
import pytest

import utilities as util
from sonar import portfolios, projects, exceptions, settings, logging
import sonar.util.constants as c

EXISTING_PROJECT = "okorach_sonar-tools"
EXISTING_PORTFOLIO = "PORT_FAV_PROJECTS"


def test_get_object(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    if util.SQ.edition() in (c.CE, c.DE):
        with pytest.raises(exceptions.UnsupportedOperation):
            portfolios.Portfolio.create(endpoint=util.SQ, key=util.TEMP_KEY, name=util.TEMP_KEY)
        return
    portf = portfolios.Portfolio.get_object(endpoint=util.SQ, key=EXISTING_PORTFOLIO)
    assert portf.key == EXISTING_PORTFOLIO
    portf2 = portfolios.Portfolio.get_object(endpoint=util.SQ, key=EXISTING_PORTFOLIO)
    assert portf2.key == EXISTING_PORTFOLIO
    assert portf is portf2


def test_get_object_non_existing() -> None:
    """Test exception raised when providing non existing portfolio key"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = portfolios.Portfolio.get_object(endpoint=util.SQ, key="NON_EXISTING")
    assert str(e.value).endswith("Portfolio key 'NON_EXISTING' not found")


def test_exists() -> None:
    """Test exist"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    assert portfolios.exists(endpoint=util.SQ, key="PORT_FAV_PROJECTS")
    assert not portfolios.exists(endpoint=util.SQ, key="NON_EXISTING")


def test_get_list() -> None:
    """Test portfolio get_list"""
    k_list = ["PORT_FAV_PROJECTS", "PORTFOLIO_ALL"]
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")

    p_dict = portfolios.get_list(endpoint=util.SQ, key_list=k_list)
    assert sorted(k_list) == sorted(list(p_dict.keys()))


def test_create_delete(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """Test portfolio create delete"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    portfolio = get_test_portfolio
    assert portfolio is not None
    assert portfolio.key == util.TEMP_KEY
    assert "none" in portfolio.selection_mode()
    assert portfolio.name == util.TEMP_KEY
    assert portfolio.is_toplevel()
    with pytest.raises(exceptions.ObjectAlreadyExists):
        portfolios.Portfolio.create(endpoint=util.SQ, key=util.TEMP_KEY)
    portfolio.delete()
    assert not portfolios.exists(endpoint=util.SQ, key=util.TEMP_KEY)


def test_add_project(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """Test addition of a project in manual mode"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    p = get_test_portfolio
    assert "none" in p.selection_mode()

    project = projects.Project.get_object(endpoint=util.SQ, key=util.LIVE_PROJECT)
    assert "none" in p.selection_mode()
    p._selection_mode = None
    p.selection_mode()
    assert not p.has_project(project.key)
    p.add_projects({project.key})
    mode = p.selection_mode()
    assert "manual" in mode
    assert mode["manual"] == {util.LIVE_PROJECT: {settings.DEFAULT_BRANCH}}
    assert p.projects() == {util.LIVE_PROJECT: {settings.DEFAULT_BRANCH}}
    components = p.get_components()
    # assert len(components) == 1
    # assert list(components.keys()) == [util.LIVE_PROJECT]
    assert p.has_project(project.key)

    p.add_project_branches(project.key, [settings.DEFAULT_BRANCH, "develop"])
    p.add_project_branches(project.key, ["comma,branch", "develop"])
    assert p.recompute()


def test_tags_mode(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """Test tag mode"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    p = get_test_portfolio
    in_tags = ["foss", "favorites"]
    p.set_tags_mode(in_tags)
    mode = p.selection_mode()
    assert "tags" in mode and mode["tags"].sort() == in_tags.sort()
    assert mode["branch"] == settings.DEFAULT_BRANCH

    p.set_tags_mode(tags=in_tags, branch="some_branch")
    mode = p.selection_mode()
    assert "tags" in mode and mode["tags"].sort() == in_tags.sort()
    assert mode["branch"] == "some_branch"
    assert p.recompute()


def test_regexp_mode(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """Test regexp mode"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    p = get_test_portfolio
    in_regexp = "^FAVORITES.*$"
    p.set_regexp_mode(in_regexp)
    mode = p.selection_mode()
    assert "regexp" in mode and mode["regexp"] == in_regexp
    assert "branch" in mode and mode["branch"] == settings.DEFAULT_BRANCH
    assert p.recompute()

    in_regexp = "^BRANCH_FAVORITES.*$"
    p.set_regexp_mode(regexp=in_regexp, branch="develop")
    mode = p.selection_mode()
    assert "regexp" in mode and mode["regexp"] == in_regexp
    assert "branch" in mode and mode["branch"] == "develop"
    assert p.recompute()


def test_remaining_projects_mode(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """Test regexp mode"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    p = get_test_portfolio
    p.set_remaining_projects_mode()
    assert p._selection_mode == {"rest": True, "branch": settings.DEFAULT_BRANCH}
    p.set_remaining_projects_mode("develop")
    assert p._selection_mode == {"rest": True, "branch": "develop"}


def test_none_mode(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """Test regexp mode"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    p = get_test_portfolio
    p.set_remaining_projects_mode()
    assert p._selection_mode == {"rest": True, "branch": settings.DEFAULT_BRANCH}
    p.set_none_mode()
    assert p._selection_mode == {}


def test_attributes(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """Test regexp mode"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    p = get_test_portfolio
    new_name = "foobar"
    p.set_name(new_name)
    p.refresh()
    assert p.name == new_name
    p.recompute()  # New name is not update in search if portfolio is not recomputed
    time.sleep(3)
    data = portfolios.search_by_name(util.SQ, new_name)
    assert data["key"] == p.key
    p.set_description("some description of a portfolio")
    p.refresh()
    assert p._description == "some description of a portfolio"


def test_permissions_1(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """Test permissions"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    p = get_test_portfolio
    p.set_permissions({"groups": {"sonar-users": ["user", "admin"], "sonar-administrators": ["user", "admin"]}})
    # assert p.permissions().to_json()["groups"] == {"sonar-users": ["user", "admin"], "sonar-administrators": ["user", "admin"]}


def test_permissions_2(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """Test permissions"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    p = get_test_portfolio
    p.set_permissions({"groups": {"sonar-users": ["user"], "sonar-administrators": ["user", "admin"]}})
    # assert p.permissions().to_json()["groups"] == {"sonar-users": ["user"], "sonar-administrators": ["user", "admin"]}


def test_audit(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """test_audit"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    p = get_test_portfolio
    audit_settings = {}
    assert len(p.audit(audit_settings)) > 0
    audit_settings["audit.portfolios.empty"] = False
    audit_settings["audit.portfolios.singleton"] = False
    p.audit(audit_settings)
    audit_settings["audit.portfolios"] = False
    assert len(portfolios.audit(util.SQ, audit_settings)) == 0


def test_add_standard_subp(get_test_subportfolio: Generator[portfolios.Portfolio]) -> None:
    """test_standard_subp"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    subp = get_test_subportfolio
    assert subp.parent_portfolio.key == util.TEMP_KEY
    parent = portfolios.Portfolio.get_object(util.SQ, key=util.TEMP_KEY)
    subp_d = parent.sub_portfolios()
    assert len(subp_d) == 1
    assert list(subp_d.keys()) == [util.TEMP_KEY_3]
    assert list(subp_d.values())[0] == subp


def test_add_standard_subp_2(get_test_portfolio: Generator[portfolios.Portfolio]) -> None:
    """test_add_standard_subp_2"""
    util.start_logging()
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    parent = get_test_portfolio
    subp = parent.add_subportfolio(key=util.TEMP_KEY_3)
    subp_d = parent.sub_portfolios()
    assert len(subp_d) == 1
    assert list(subp_d.keys()) == [util.TEMP_KEY_3]
    assert list(subp_d.values())[0] == subp
    # subp.refresh()
    logging.debug("%s is toplevel = %s", str(subp), str(subp.is_toplevel()))
    assert not subp.is_toplevel()
    assert parent.is_parent_of(subp.key)
    assert subp.is_subporfolio_of(parent.key)


def test_add_ref_subp(get_test_portfolio: Generator[portfolios.Portfolio], get_test_portfolio_2: Generator[portfolios.Portfolio]) -> None:
    """test_add_standard_subp_2"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    parent = get_test_portfolio
    ref = get_test_portfolio_2
    subp = parent.add_subportfolio(key=ref.key, by_ref=True)
    subp_d = parent.sub_portfolios()
    assert len(subp_d) == 1
    assert list(subp_d.keys()) == [ref.key]
    assert list(subp_d.values())[0] == subp


def test_export() -> None:
    """test_export"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    json_exp = portfolios.export(util.SQ, {})
    yaml_exp = portfolios.convert_for_yaml(json_exp)
    assert len(json_exp) > 0
    assert isinstance(json_exp, dict)
    assert isinstance(yaml_exp, list)
    assert len(yaml_exp) == len(json_exp)


def test_import(json_file: Generator[str]) -> None:
    """test_import"""

    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    with open("test/files/config.json", "r", encoding="utf-8") as f:
        json_exp = json.loads(f.read())["portfolios"]
    # delete all portfolios in test
    logging.info("Deleting all portfolios")
    portfolios.Portfolio.clear_cache()
    _ = [o.delete() for o in portfolios.get_list(util.TEST_SQ, use_cache=False).values() if o.is_toplevel()]
    assert portfolios.import_config(util.TEST_SQ, {"portfolios": json_exp})

    # Compare portfolios
    o_list = portfolios.get_list(util.TEST_SQ)
    assert len(o_list) == len(json_exp)
    assert sorted(list(o_list.keys())) == sorted(list(json_exp.keys()))


def test_audit_disabled() -> None:
    """test_audit_disabled"""
    if util.SQ.edition() in (c.CE, c.DE):
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    assert len(portfolios.audit(util.SQ, {"audit.portfolios": False})) == 0
