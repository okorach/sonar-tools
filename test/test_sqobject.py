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
from sonar import projects, branches, exceptions


TAGS = ["foo", "bar"]


def __set_unset_tags(o: object) -> None:
    """Sets and unsets TAGS on a object, and verify that TAGS are modifed accordingly"""
    assert o.get_tags() is None
    o.set_tags(TAGS)
    assert o.get_tags() == sorted(TAGS)
    o.set_tags([])
    assert o.get_tags() is None


def test_tag_projects(get_test_project: callable) -> None:
    """test_tag_projects"""
    __set_unset_tags(get_test_project)


def test_tag_apps(get_test_app: callable) -> None:
    """test_tag_apps"""
    __set_unset_tags(get_test_app)


def test_tag_issues(get_test_issue: callable) -> None:
    """test_tag_apps"""
    __set_unset_tags(get_test_issue)


def test_tag_portfolios(get_test_portfolio: callable) -> None:
    """test_tag_portfolios"""
    o = get_test_portfolio
    with pytest.raises(exceptions.UnsupportedOperation):
        o.get_tags()
    with pytest.raises(exceptions.UnsupportedOperation):
        o.set_tags(TAGS)


def test_tag_project_branches() -> None:
    """test_tag_project_branches"""
    proj = projects.Project.get_object(util.SQ, util.LIVE_PROJECT)
    o = branches.Branch.get_object(proj, "master")
    with pytest.raises(exceptions.UnsupportedOperation):
        o.get_tags()
    with pytest.raises(exceptions.UnsupportedOperation):
        o.set_tags(TAGS)
