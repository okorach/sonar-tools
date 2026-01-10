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

"""applications tests"""

import datetime
from collections.abc import Generator
import pytest
import os

import utilities as tutil
from sonar import applications as apps, exceptions
from sonar.applications import Application as App
import sonar.util.constants as c

EXISTING_KEY = "APP_TEST"
EXISTING_KEY_2 = "FE-BE"
NON_EXISTING_KEY = "NON_EXISTING"
TEST_KEY = "MY_APPPP"

__UNSUPPORTED_MESSAGE = "Apps unsupported in SonarQube Community Build and SonarQube Cloud"
__SUPPORTED_EDITIONS = (c.DE, c.EE, c.DCE)


def __verify_support() -> bool:
    return tutil.verify_support(__SUPPORTED_EDITIONS, App.get_object, endpoint=tutil.SQ, key=NON_EXISTING_KEY)


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj = App.get_object(endpoint=tutil.SQ, key=EXISTING_KEY)
    assert obj.key == EXISTING_KEY
    obj2 = App.get_object(endpoint=tutil.SQ, key=EXISTING_KEY)
    assert obj2.key == EXISTING_KEY
    assert obj == obj2
    assert obj.recompute()


def test_count() -> None:
    """Verify count works"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    assert apps.count(tutil.SQ) > 0


def test_search() -> None:
    """Verify that search with criterias work"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    res_list = apps.Application.search(endpoint=tutil.SQ, s="analysisDate")
    oldest = datetime.datetime(1970, 1, 1).replace(tzinfo=datetime.timezone.utc)
    for obj in res_list.values():
        app_date = obj.last_analysis()
        if app_date and app_date != "":
            assert oldest <= app_date
            oldest = app_date


def test_get_object_non_existing() -> None:
    """Test exception raised when providing non existing portfolio key"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = App.get_object(endpoint=tutil.SQ, key=NON_EXISTING_KEY)
    assert str(e.value).endswith(f"Application '{NON_EXISTING_KEY}' not found")


def test_exists(get_test_app: Generator[App]) -> None:
    """Test exist"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj = get_test_app
    assert apps.Application.exists(endpoint=tutil.SQ, key=obj.key)
    assert not apps.Application.exists(endpoint=tutil.SQ, key=NON_EXISTING_KEY)


def test_create_delete(get_test_app: Generator[App]) -> None:
    """Test portfolio create delete"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj: App = get_test_app
    assert obj is not None
    assert obj.key.startswith(f"{tutil.TEMP_KEY}-application")
    assert obj.name.startswith(f"{tutil.TEMP_KEY}-application")
    obj.delete()
    assert not apps.Application.exists(endpoint=tutil.SQ, key=tutil.TEMP_KEY)

    # Test delete with 1 project in the app
    obj = App.create(endpoint=tutil.SQ, name=tutil.TEMP_NAME, key=f"{tutil.TEMP_KEY}-application-{os.getpid()}")
    obj.add_projects([tutil.LIVE_PROJECT])
    key = obj.key
    obj.delete()
    assert not apps.Application.exists(endpoint=tutil.SQ, key=key)


def test_permissions_1(get_test_app: Generator[App]) -> None:
    """Test permissions"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj: App = get_test_app
    obj.set_permissions(
        [
            {"group": tutil.SQ.default_user_group(), "permissions": ["user", "admin"]},
            {"group": "sonar-administrators", "permissions": ["user", "admin"]},
        ]
    )


def test_get_projects() -> None:
    """test_get_projects"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj = App.get_object(endpoint=tutil.SQ, key=EXISTING_KEY)
    count = len(obj.projects())
    assert count > 0
    assert len(obj.projects()) == count


def test_get_branches() -> None:
    """test_get_projects"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj = App.get_object(endpoint=tutil.SQ, key=EXISTING_KEY)
    count = len(obj.branches())
    assert count > 0
    assert len(obj.branches()) == count


def test_no_audit(get_test_app: Generator[App]) -> None:
    """Check stop fast when audit params are disabled"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj: App = get_test_app
    assert len(obj.audit({"audit.applications": False})) == 0
    assert len(obj._audit_empty({"audit.applications.empty": True})) == 1
    assert len(obj._audit_empty({"audit.applications.empty": False})) == 0
    obj.add_projects([tutil.LIVE_PROJECT])
    assert len(obj._audit_singleton({"audit.applications.singleton": True})) == 1
    assert len(obj._audit_singleton({"audit.applications.singleton": False})) == 0


def test_search_by_name() -> None:
    """test_search_by_name"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj = App.get_object(endpoint=tutil.SQ, key=EXISTING_KEY)
    other_apps = apps.search_by_name(endpoint=tutil.SQ, name=obj.name)

    assert len(other_apps) == 1
    first_app = list(other_apps.values())[0]
    assert obj == first_app


def test_set_tags(get_test_app: Generator[App]) -> None:
    """test_set_tags"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj: App = get_test_app

    assert obj.set_tags(tutil.TAGS)
    assert obj.get_tags() == sorted(tutil.TAGS)
    assert obj.set_tags(["foo"])
    assert obj.get_tags() == ["foo"]
    assert obj.set_tags([])
    assert obj.get_tags() == []
    assert not obj.set_tags(None)


def test_not_found(get_test_app: Generator[App]) -> None:
    """test_not_found"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj: App = get_test_app
    obj.key = "mess-me-up"
    with pytest.raises(exceptions.ObjectNotFound):
        obj.refresh()


def test_already_exists(get_test_app: Generator[App]) -> None:
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj = get_test_app
    with pytest.raises(exceptions.ObjectAlreadyExists):
        _ = App.create(endpoint=tutil.SQ, key=obj.key, name="Foo Bar")


def test_branch_exists(get_test_app: Generator[App]) -> None:
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj: App = get_test_app
    assert obj.branch_exists("main")
    assert not obj.branch_exists("non-existing")


def test_branch_is_main(get_test_app: Generator[App]) -> None:
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj: App = get_test_app
    assert obj.branch_is_main("main")
    with pytest.raises(exceptions.ObjectNotFound):
        obj.branch_is_main("non-existing")


def test_get_issues(get_test_app: Generator[App]) -> None:
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    app: App = get_test_app
    assert len(app.get_issues()) == 0
    app = App.get_object(endpoint=tutil.SQ, key=EXISTING_KEY)
    main_br_count = len(app.get_issues())
    assert main_br_count > 0
    assert len(app.get_issues(branch="main")) == main_br_count
    with pytest.raises(exceptions.ObjectNotFound):
        app.get_issues(branch="non-existing")

    main_br_count = len(app.get_hotspots())
    assert main_br_count > 0
    assert len(app.get_hotspots(branch="main")) == main_br_count
    with pytest.raises(exceptions.ObjectNotFound):
        app.get_hotspots(branch="non-existing")


def test_audit_disabled() -> None:
    """test_audit_disabled"""
    assert len(apps.audit(tutil.SQ, {"audit.applications": False})) == 0


def test_app_branches(get_test_app: Generator[App]) -> None:
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    obj: App = get_test_app
    APP_BRANCH_MAIN, APP_BRANCH_2 = "BRANCH foo", "Other Branch"
    definition = {
        "branches": [
            {
                "name": APP_BRANCH_2,
                "projects": [
                    {"key": tutil.PROJ_WITH_BRANCHES, "branch": tutil.BRANCH_MAIN},
                    {"key": tutil.PROJECT_1, "branch": "main"},
                    {"key": "demo:java-security", "branch": "main"},
                ],
            },
            {
                "name": APP_BRANCH_MAIN,
                "projects": [
                    {"key": tutil.PROJ_WITH_BRANCHES, "branch": tutil.BRANCH_3},
                    {"key": tutil.PROJECT_1, "branch": "main"},
                    {"key": "demo:java-security", "branch": "main"},
                ],
                "isMain": True,
            },
        ]
    }
    obj.update(definition)
    br = obj.branches()
    assert set(br.keys()) == {APP_BRANCH_MAIN, APP_BRANCH_2}
    assert obj.main_branch().name == APP_BRANCH_MAIN
    APP_BRANCH_MAIN, APP_BRANCH_2, APP_BRANCH_3 = "Main Branch", "Master", "MiBranch"
    definition = {
        "branches": [
            {
                "name": APP_BRANCH_2,
                "projects": [
                    {"key": tutil.PROJ_WITH_BRANCHES, "branch": tutil.BRANCH_MAIN},
                    {"key": tutil.PROJECT_1, "branch": "main"},
                    {"key": "demo:java-security", "branch": "main"},
                ],
            },
            {
                "name": APP_BRANCH_3,
                "projects": [
                    {"key": tutil.PROJ_WITH_BRANCHES, "branch": tutil.BRANCH_3},
                    {"key": tutil.PROJECT_1, "branch": "main"},
                    {"key": "demo:java-security", "branch": "main"},
                ],
            },
            {
                "name": APP_BRANCH_MAIN,
                "projects": [
                    {"key": tutil.PROJ_WITH_BRANCHES, "branch": tutil.BRANCH_3},
                    {"key": tutil.PROJECT_1, "branch": "main"},
                    {"key": "demo:java-security", "branch": "main"},
                ],
                "isMain": True,
            },
        ]
    }
    obj.update(definition)
    br = obj.branches()
    assert set(br.keys()) >= {APP_BRANCH_MAIN, APP_BRANCH_2, APP_BRANCH_3}
    assert obj.main_branch().name == APP_BRANCH_MAIN


def test_sorted_search() -> None:
    """test_sorted_search"""
    if not __verify_support():
        pytest.skip(__UNSUPPORTED_MESSAGE)
    apps_list = apps.Application.search(tutil.SQ)
    assert sorted(apps_list.keys()) == list(apps_list.keys())

    apps_list = apps.Application.search(tutil.SQ, use_cache=True)
    assert sorted(apps_list.keys()) == list(apps_list.keys())
