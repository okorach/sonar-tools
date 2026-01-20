#!/usr/bin/env python3
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

"""portfolio tests"""

from collections.abc import Generator
import time
import json
import pytest
import os

import utilities as tutil
from sonar import portfolios as pf, projects, exceptions, logging
import sonar.util.constants as c
from sonar.util import portfolio_helper as phelp
import credentials

EXISTING_PORTFOLIO = "PORT_FAV_PROJECTS"


__SUPPORTED_EDITIONS = (c.EE, c.DCE)
__UNSUPPORTED_MESSAGE = "Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions"


def __verify_support() -> bool:
    return tutil.verify_support(__SUPPORTED_EDITIONS, pf.Portfolio.get_object, endpoint=tutil.SQ, key=tutil.TEMP_KEY)


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    portf = pf.Portfolio.get_object(endpoint=tutil.SQ, key=EXISTING_PORTFOLIO)
    assert portf.key == EXISTING_PORTFOLIO
    portf2 = pf.Portfolio.get_object(endpoint=tutil.SQ, key=EXISTING_PORTFOLIO)
    assert portf2.key == EXISTING_PORTFOLIO
    assert portf is portf2


def test_get_object_non_existing() -> None:
    """Test exception raised when providing non existing portfolio key"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = pf.Portfolio.get_object(endpoint=tutil.SQ, key="NON_EXISTING")
    assert str(e.value).endswith("Portfolio key 'NON_EXISTING' not found")


def test_exists() -> None:
    """Test exist"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    assert pf.Portfolio.exists(endpoint=tutil.SQ, key="PORT_FAV_PROJECTS")
    assert not pf.Portfolio.exists(endpoint=tutil.SQ, key="NON_EXISTING")


def test_get_list() -> None:
    """Test portfolio get_list"""
    k_list = ["PORT_FAV_PROJECTS", "PORTFOLIO_ALL"]
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)

    p_dict = pf.Portfolio.search(endpoint=tutil.SQ)
    for k in k_list:
        assert k in p_dict


def test_create_delete(get_test_portfolio: Generator[pf.Portfolio]) -> None:
    """Test portfolio create delete"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    portfolio: pf.Portfolio = get_test_portfolio
    assert portfolio is not None
    assert portfolio.key.startswith(f"{tutil.TEMP_KEY}-portfolio")
    assert "none" in portfolio.selection_mode()
    assert portfolio.name.startswith(f"{tutil.TEMP_KEY}-portfolio")
    key = portfolio.key
    assert portfolio.is_toplevel()
    with pytest.raises(exceptions.ObjectAlreadyExists):
        pf.Portfolio.create(endpoint=tutil.SQ, key=key)
    portfolio.delete()
    assert not pf.Portfolio.exists(endpoint=tutil.SQ, key=key)


def test_add_project(get_test_portfolio: Generator[pf.Portfolio]) -> None:
    """Test addition of a project in manual mode"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    p = get_test_portfolio
    assert "none" in p.selection_mode()

    project = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.LIVE_PROJECT)
    assert "none" in p.selection_mode()
    p._selection_mode = None
    p.selection_mode()
    assert not p.has_project(project.key)
    p.add_projects({project.key})
    mode = p.selection_mode()
    assert "manual" in mode
    assert mode["manual"] == {tutil.LIVE_PROJECT: {c.DEFAULT_BRANCH}}
    assert p.projects() == {tutil.LIVE_PROJECT: {c.DEFAULT_BRANCH}}
    # components = p.get_components()
    # assert len(components) == 1
    # assert list(components.keys()) == [util.LIVE_PROJECT]
    assert p.has_project(project.key)

    p.add_project_branches(project.key, [c.DEFAULT_BRANCH, "develop"])
    p.add_project_branches(project.key, ["release-3.x", "develop"])
    assert p.recompute()


def test_tags_mode(get_test_portfolio: Generator[pf.Portfolio]) -> None:
    """Test tag mode"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    p = get_test_portfolio
    in_tags = ["foss", "favorites"]
    p.set_tags_mode(in_tags)
    mode = p.selection_mode()
    assert "tags" in mode and mode["tags"].sort() == in_tags.sort()
    assert mode["branch"] == c.DEFAULT_BRANCH

    p.set_tags_mode(tags=in_tags, branch="some_branch")
    mode = p.selection_mode()
    assert "tags" in mode and mode["tags"].sort() == in_tags.sort()
    assert mode["branch"] == "some_branch"
    assert p.recompute()


def test_regexp_mode(get_test_portfolio: Generator[pf.Portfolio]) -> None:
    """Test regexp mode"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    p = get_test_portfolio
    in_regexp = "^FAVORITES.*$"
    p.set_regexp_mode(in_regexp)
    mode = p.selection_mode()
    assert "regexp" in mode and mode["regexp"] == in_regexp
    assert "branch" in mode and mode["branch"] == c.DEFAULT_BRANCH
    assert p.recompute()

    in_regexp = "^BRANCH_FAVORITES.*$"
    p.set_regexp_mode(regexp=in_regexp, branch="develop")
    mode = p.selection_mode()
    assert "regexp" in mode and mode["regexp"] == in_regexp
    assert "branch" in mode and mode["branch"] == "develop"
    assert p.recompute()


def test_remaining_projects_mode(get_test_portfolio: Generator[pf.Portfolio]) -> None:
    """Test regexp mode"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    p = get_test_portfolio
    p.set_remaining_projects_mode()
    assert p._selection_mode == {"rest": True, "branch": c.DEFAULT_BRANCH}
    p.set_remaining_projects_mode("develop")
    assert p._selection_mode == {"rest": True, "branch": "develop"}


def test_none_mode(get_test_portfolio: Generator[pf.Portfolio]) -> None:
    """Test regexp mode"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    p = get_test_portfolio
    p.set_remaining_projects_mode()
    assert p._selection_mode == {"rest": True, "branch": c.DEFAULT_BRANCH}
    p.set_none_mode()
    assert p._selection_mode == {}


def test_attributes(get_test_portfolio: Generator[pf.Portfolio]) -> None:
    """Test regexp mode"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    p = get_test_portfolio
    new_name = "foobar"
    p.set_name(new_name)
    p.refresh()
    assert p.name == new_name
    p.recompute()  # New name is not update in search if portfolio is not recomputed
    time.sleep(3)
    data = pf.search_by_name(tutil.SQ, new_name)
    assert data["key"] == p.key
    p.set_description("some description of a portfolio")
    p.refresh()
    assert p._description == "some description of a portfolio"


def test_permissions_1(get_test_portfolio: Generator[pf.Portfolio]) -> None:
    """Test permissions"""
    if not __verify_support():
        pytest.skip("Portfolios unsupported in SonarQube Community Build and SonarQube Developer editions")
    p = get_test_portfolio
    p.set_permissions(
        [
            {"group": tutil.SQ.default_user_group(), "permissions": ["user", "admin"]},
            {"group": credentials.ADMIN_GROUP, "permissions": ["user", "admin"]},
        ]
    )
    # assert p.permissions().to_json()["groups"] == {tutil.SQ.default_user_group(): ["user", "admin"], credentials.ADMIN_GROUP: ["user", "admin"]}


def test_audit(get_test_portfolio: Generator[pf.Portfolio]) -> None:
    """test_audit"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    p = get_test_portfolio
    audit_settings = {}
    assert len(p.audit(audit_settings)) > 0
    audit_settings["audit.pf.empty"] = False
    audit_settings["audit.pf.singleton"] = False
    p.audit(audit_settings)
    audit_settings["audit.portfolios"] = False
    assert len(pf.audit(tutil.SQ, audit_settings)) == 0


def test_add_standard_subp(get_test_subportfolio: Generator[pf.Portfolio]) -> None:
    """test_standard_subp"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    subp = get_test_subportfolio
    assert subp.parent_portfolio.key.startswith(f"{tutil.TEMP_KEY}-portfolio")
    parent = pf.Portfolio.get_object(tutil.SQ, key=subp.parent_portfolio.key)
    subp_d = parent.sub_portfolios()
    assert len(subp_d) == 1
    assert list(subp_d.keys()) == [subp.key]
    assert list(subp_d.values())[0] == subp


def test_add_standard_subp_2(get_test_portfolio: Generator[pf.Portfolio]) -> None:
    """test_add_standard_subp_2"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    parent = get_test_portfolio
    subp = parent.add_subportfolio(key=parent.key)
    subp_d = parent.sub_portfolios()
    assert len(subp_d) == 1
    assert list(subp_d.keys()) == [subp.key]
    assert list(subp_d.values())[0] == subp
    # subp.refresh()
    logging.debug("%s is toplevel = %s", str(subp), str(subp.is_toplevel()))
    assert not subp.is_toplevel()
    assert parent.is_parent_of(subp.key)
    assert subp.is_subporfolio_of(parent.key)


def test_add_ref_subp(get_test_portfolio: Generator[pf.Portfolio], get_test_portfolio_2: Generator[pf.Portfolio]) -> None:
    """test_add_standard_subp_2"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    parent = get_test_portfolio
    ref = get_test_portfolio_2
    subp = parent.add_subportfolio(key=ref.key, by_ref=True)
    subp_d = parent.sub_portfolios()
    assert len(subp_d) == 1
    assert list(subp_d.keys()) == [ref.key]
    assert list(subp_d.values())[0] == subp


def test_export() -> None:
    """test_export"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    json_exp = pf.export(tutil.SQ, {})
    list_exp = phelp.convert_portfolios_json(json_exp)
    assert len(json_exp) > 0
    assert isinstance(list_exp, list)
    assert len(list_exp) == len(json_exp)


def test_import() -> None:
    """test_import"""

    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    with open(f"{tutil.FILES_ROOT}/config.json", "r", encoding="utf-8") as f:
        json_exp = json.loads(f.read())["portfolios"]
    # delete all portfolios in test
    logging.info("Deleting all portfolios")
    pf.Portfolio.clear_cache()
    for o in pf.Portfolio.search(tutil.TEST_SQ).values():
        if o.is_toplevel():
            o.delete()
    assert pf.import_config(tutil.TEST_SQ, {"portfolios": json_exp})

    # Compare portfolios
    o_list = pf.Portfolio.search(tutil.TEST_SQ)
    assert len(o_list) == len(json_exp)
    assert sorted(o_list.keys()) == sorted([o["key"] for o in json_exp])


def test_audit_disabled() -> None:
    """test_audit_disabled"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    assert len(pf.audit(tutil.SQ, {"audit.portfolios": False})) == 0


def test_sorted_search() -> None:
    """test_sorted_search"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    p_dict = pf.Portfolio.search(tutil.SQ)
    assert sorted(p_dict.keys()) == list(p_dict.keys())

    p_dict = pf.Portfolio.search(tutil.SQ, use_cache=True)
    assert sorted(p_dict.keys()) == list(p_dict.keys())
