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

""" Test fixtures """

from collections.abc import Generator
import pytest

import utilities as util
from sonar import projects, applications, portfolios, exceptions, logging, issues


TEST_ISSUE = "a1fddba4-9e70-46c6-ac95-e815104ead59"


@pytest.fixture
def get_test_project() -> Generator[projects.Project]:
    """setup of tests"""
    logging.set_logger("test-sqobject.log")
    logging.set_debug_level("DEBUG")
    o = projects.Project.create(endpoint=util.SQ, key=util.TEMP_KEY, name=util.TEMP_KEY)
    yield o
    # Teardown: Clean up resources (if any) after the test
    o.delete()


@pytest.fixture
def get_test_app() -> Generator[applications.Application]:
    """setup of tests"""
    logging.set_logger("test-sqobject.log")
    logging.set_debug_level("DEBUG")
    try:
        o = applications.Application.get_object(endpoint=util.SQ, key=util.TEMP_KEY)
    except exceptions.ObjectNotFound:
        o = applications.Application.create(endpoint=util.SQ, key=util.TEMP_KEY, name=util.TEMP_NAME)
    yield o
    # Teardown: Clean up resources (if any) after the test
    o.delete()


@pytest.fixture
def get_test_portfolio() -> Generator[portfolios.Portfolio]:
    """setup of tests"""
    o = portfolios.Portfolio.create(endpoint=util.SQ, key=util.TEMP_KEY, name=util.TEMP_KEY)
    yield o
    # Teardown: Clean up resources (if any) after the test
    o.delete()


@pytest.fixture
def get_test_issue() -> issues.Issue:
    """setup of tests"""
    issues_d = issues.search_by_project(endpoint=util.SQ, project_key=util.LIVE_PROJECT)
    yield issues_d[TEST_ISSUE]
    # Teardown: Clean up resources (if any) after the test
