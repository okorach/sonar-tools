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
from sonar import portfolios, projects, exceptions

EXISTING_PROJECT = "okorach_sonar-tools"
EXISTING_PORTFOLIO = "PORT_FAV_PROJECTS"
TEST_KEY = "MY_PPPPORTFOLIO_KEY"

def get_object() -> None:
    """ Test get_object and verify that if requested twice the same object is returned """
    portf = portfolios.Portfolio.get_object(endpoint=util.SQ, key=EXISTING_PORTFOLIO)
    assert portf.key == EXISTING_PORTFOLIO
    portf2 = portfolios.Portfolio.get_object(endpoint=util.SQ, key=EXISTING_PORTFOLIO)
    assert portf2.key == EXISTING_PORTFOLIO
    assert portf == portf2

def get_object_non_existing() -> None:
    """ Test exception raised when providing non existing portfolio key """
    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = portfolios.Portfolio.get_object(endpoint=util.SQ, key="NON_EXISTING")
    assert str(e.value) == "Portfolio key 'NON_EXISTING' not found"

def exists() -> None:
    """ Test exist """
    assert portfolios.exists(endpoint=util.SQ, key="PORT_FAV_PROJECTS")
    assert not portfolios.exists(endpoint=util.SQ, key="NON_EXISTING")

def get_list() -> None:
    """ Test portfolio get_list """
    p_dict = portfolios.get_list(endpoint=util.SQ, key_list="PORT_FAV_PROJECTS,PORTFOLIO_ALL")
    assert "PORT_FAV_PROJECTS" in p_dict
    assert "PORTFOLIO_ALL" in p_dict
    assert len(p_dict) == 2

def create_delete() -> None:
    """ Test portfolio create delete """
    portfolio = portfolios.Portfolio.create(endpoint=util.SQ, name="MY PPPPPORFOLIO", key=TEST_KEY, description="Creationtest")
    assert portfolio is not None
    assert portfolio.key == TEST_KEY
    assert portfolio.name == "MY PPPPPORFOLIO"

    portfolio.delete()
    assert not portfolios.exists(endpoint=util.SQ, key=TEST_KEY)

def add_project() -> None:
    """ Test addition of a project in manual mode """
    portfolio = portfolios.Portfolio.create(endpoint=util.SQ, name="A portfolio", key=TEST_KEY, description="Add_project_test")
    project = projects.Project.get_object(endpoint=util.SQ, key="okorach_sonar-tools")
    portfolio.set_projects({"okorach_sonar-tools": project})
    portfolio.delete()
