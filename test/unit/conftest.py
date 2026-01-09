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

"""Test fixtures"""

from __future__ import annotations
import os
from typing import Union

from collections.abc import Generator
import pytest

import utilities as tutil
from sonar import projects, applications, portfolios, qualityprofiles, qualitygates, exceptions, logging, issues, users, groups
import sonar.util.constants as c

TEMP_FILE_ROOT = f"temp.{os.getpid()}"
CSV_FILE = f"{TEMP_FILE_ROOT}.csv"
JSON_FILE = f"{TEMP_FILE_ROOT}.json"
YAML_FILE = f"{TEMP_FILE_ROOT}.yaml"

TEST_ISSUE = "a1fddba4-9e70-46c6-ac95-e815104ead59"


def create_test_object(a_class: type, key: str) -> any:
    """Creates a SonarQube test object of a given class"""
    try:
        o = a_class.get_object(endpoint=tutil.SQ, key=key)
    except exceptions.ObjectNotFound:
        o = a_class.create(endpoint=tutil.SQ, key=key, name=key)
    return o


@pytest.fixture(autouse=True)
def run_around_tests():
    tutil.start_logging()
    url = tutil.TEST_SQ.local_url
    yield
    tutil.TEST_SQ.local_url = url


@pytest.fixture
def get_test_project() -> Generator[projects.Project]:
    """setup of tests"""
    o = create_test_object(projects.Project, key=tutil.TEMP_KEY)
    yield o
    # Teardown: Clean up resources (if any) after the test
    o.key = tutil.TEMP_KEY
    try:
        o.delete()
    except exceptions.ObjectNotFound:
        pass


@pytest.fixture
def get_empty_qg() -> Generator[qualitygates.QualityGate]:
    """setup of tests"""
    try:
        o = qualitygates.QualityGate.get_object(endpoint=tutil.SQ, name=tutil.TEMP_KEY)
    except exceptions.ObjectNotFound:
        o = qualitygates.QualityGate.create(endpoint=tutil.SQ, name=tutil.TEMP_KEY)
    o.clear_conditions()
    yield o
    # Teardown: Clean up resources (if any) after the test
    o.key = tutil.TEMP_KEY
    try:
        sw = qualitygates.QualityGate.get_object(endpoint=tutil.SQ, name=tutil.SONAR_WAY)
        sw.set_as_default()
        o.delete()
    except exceptions.ObjectNotFound:
        pass


@pytest.fixture
def get_loaded_qg() -> Generator[qualitygates.QualityGate]:
    """setup of tests"""
    try:
        o = qualitygates.QualityGate.get_object(endpoint=tutil.SQ, name=tutil.TEMP_KEY)
    except exceptions.ObjectNotFound:
        o = qualitygates.QualityGate.create(endpoint=tutil.SQ, name=tutil.TEMP_KEY)
    yield o
    o.key = tutil.TEMP_KEY
    try:
        sw = qualitygates.QualityGate.get_object(endpoint=tutil.SQ, name=tutil.SONAR_WAY)
        sw.set_as_default()
        o.delete()
    except exceptions.ObjectNotFound:
        pass


@pytest.fixture
def get_test_app() -> Generator[applications.Application]:
    """setup of tests"""
    o = None
    if tutil.SQ.edition() in (c.DE, c.EE, c.DCE):
        o = create_test_object(applications.Application, key=tutil.TEMP_KEY)
    yield o
    if tutil.SQ.edition() in (c.DE, c.EE, c.DCE):
        o.key = tutil.TEMP_KEY
        try:
            o.delete()
        except exceptions.ObjectNotFound:
            pass


@pytest.fixture
def get_test_portfolio() -> Generator[Union[portfolios.Portfolio, None]]:
    """setup of tests"""
    o = None
    if tutil.SQ.edition() in (c.EE, c.DCE):
        o = create_test_object(portfolios.Portfolio, key=tutil.TEMP_KEY)
    yield o
    if tutil.SQ.edition() in (c.EE, c.DCE):
        o.key = tutil.TEMP_KEY
        try:
            o.delete()
        except exceptions.ObjectNotFound:
            pass


@pytest.fixture
def get_test_portfolio_2() -> Generator[portfolios.Portfolio]:
    """setup of tests"""
    o = None
    if tutil.SQ.edition() in (c.EE, c.DCE):
        o = create_test_object(portfolios.Portfolio, key=tutil.TEMP_KEY_2)
    yield o
    if tutil.SQ.edition() in (c.EE, c.DCE):
        o.key = tutil.TEMP_KEY_2
        try:
            o.delete()
        except exceptions.ObjectNotFound:
            pass


@pytest.fixture
def get_test_subportfolio() -> Generator[portfolios.Portfolio]:
    """setup of tests"""
    subp = None
    if tutil.SQ.edition() in (c.EE, c.DCE):
        parent = create_test_object(portfolios.Portfolio, key=tutil.TEMP_KEY)
        subp = parent.add_standard_subportfolio(key=tutil.TEMP_KEY_3, name=tutil.TEMP_KEY_3)
    yield subp
    if tutil.SQ.edition() in (c.EE, c.DCE):
        subp.key = tutil.TEMP_KEY_3
        try:
            subp.delete()
        except exceptions.ObjectNotFound:
            pass
        parent.key = tutil.TEMP_KEY
        try:
            parent.delete()
        except exceptions.ObjectNotFound:
            pass


@pytest.fixture
def get_test_qp() -> Generator[qualityprofiles.QualityProfile]:
    """setup of tests"""
    try:
        o = qualityprofiles.QualityProfile.get_object(endpoint=tutil.SQ, name=tutil.TEMP_KEY, language="py")
        if o.is_default:
            sw = qualityprofiles.QualityProfile.get_object(endpoint=tutil.SQ, name=tutil.SONAR_WAY, language="py")
            sw.set_as_default()
    except exceptions.ObjectNotFound:
        o = qualityprofiles.QualityProfile.create(endpoint=tutil.SQ, name=tutil.TEMP_KEY, language="py")
    yield o
    try:
        o.delete()
    except exceptions.ObjectNotFound:
        pass


@pytest.fixture
def get_test_issue() -> Generator[issues.Issue]:
    """setup of tests"""
    issues_d = issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.LIVE_PROJECT)
    yield issues_d[TEST_ISSUE]
    # Teardown: Clean up resources (if any) after the test - Nothing in that case


@pytest.fixture
def get_test_user() -> Generator[users.User]:
    """setup of tests"""
    try:
        o = users.User.get_object(endpoint=tutil.SQ, login=tutil.TEMP_KEY)
    except exceptions.ObjectNotFound:
        o = users.User.create(endpoint=tutil.SQ, login=tutil.TEMP_KEY, name=f"User name {tutil.TEMP_KEY}")
    (uid, uname, ulogin) = (o.name, o.id, o.login)
    for g in o.groups():
        if g != tutil.SQ.default_user_group():
            o.remove_from_group(g)
    yield o
    try:
        (o.name, o.id, o.login) = (uid, uname, ulogin)
        for g in o.groups():
            if g != tutil.SQ.default_user_group():
                o.remove_from_group(g)
        o.delete()
    except exceptions.ObjectNotFound:
        pass


def rm(file: str) -> None:
    """Removes a file if exists"""
    try:
        os.remove(file)
    except FileNotFoundError:
        pass


def get_temp_filename(ext: str) -> str:
    """Returns a temp output file for tests"""
    logging.set_logger("pytest.log")
    logging.set_debug_level("DEBUG")
    file = f"{TEMP_FILE_ROOT}.{ext}"
    rm(file)
    return file


@pytest.fixture
def csv_file() -> Generator[str]:
    """setup of tests"""
    file = get_temp_filename("csv")
    yield file
    if os.path.exists(file):
        rm(file)


@pytest.fixture
def txt_file() -> Generator[str]:
    """setup of tests"""
    file = get_temp_filename("txt")
    yield file
    if os.path.exists(file):
        rm(file)


@pytest.fixture
def json_file() -> Generator[str]:
    """setup of tests"""
    file = get_temp_filename("json")
    yield file
    if os.path.exists(file):
        rm(file)


@pytest.fixture
def yaml_file() -> Generator[str]:
    """setup of tests"""
    file = get_temp_filename("yaml")
    yield file
    if os.path.exists(file):
        rm(file)


@pytest.fixture
def sarif_file() -> Generator[str]:
    """setup of tests"""
    file = get_temp_filename("sarif")
    yield file
    if os.path.exists(file):
        rm(file)


@pytest.fixture
def get_test_quality_gate() -> Generator[qualitygates.QualityGate]:
    """setup of tests"""
    sonar_way = qualitygates.QualityGate.get_object(tutil.SQ, tutil.SONAR_WAY)
    o = sonar_way.copy(tutil.TEMP_KEY)
    yield o
    try:
        o.delete()
    except exceptions.ObjectNotFound:
        pass


@pytest.fixture
def get_test_group() -> Generator[groups.Group]:
    """setup of tests"""
    try:
        o = groups.Group.get_object(endpoint=tutil.SQ, name=tutil.TEMP_KEY)
    except exceptions.ObjectNotFound:
        o = groups.Group.create(endpoint=tutil.SQ, name=tutil.TEMP_KEY)
    yield o
    try:
        o.delete()
    except exceptions.ObjectNotFound:
        pass


@pytest.fixture
def get_60_groups() -> Generator[list[groups.Group]]:
    group_list = []
    for i in range(60):
        gr_name = f"Group-{tutil.TEMP_KEY}{i}"
        try:
            o_gr = groups.Group.get_object(endpoint=tutil.SQ, name=gr_name)
        except exceptions.ObjectNotFound:
            o_gr = groups.Group.create(endpoint=tutil.SQ, name=gr_name, description=gr_name)
        group_list.append(o_gr)
    yield group_list
    for g in group_list:
        g.delete()


@pytest.fixture
def get_60_users() -> Generator[list[users.User]]:
    user_list = []
    for i in range(60):
        u_name = f"User-{tutil.TEMP_KEY}{i}"
        try:
            o_user = users.User.get_object(endpoint=tutil.SQ, login=u_name)
        except exceptions.ObjectNotFound:
            o_user = users.User.create(endpoint=tutil.SQ, login=u_name, name=u_name)
        user_list.append(o_user)
    yield user_list
    for u in user_list:
        u.delete()
