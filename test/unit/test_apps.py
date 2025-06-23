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

""" applications tests """

import datetime
from collections.abc import Generator
import pytest

import utilities as util
from sonar import applications as apps, exceptions
from sonar.applications import Application as App
import sonar.util.constants as c

EXISTING_KEY = "APP_TEST"
EXISTING_KEY_2 = "APP_TEST_2"
NON_EXISTING_KEY = "NON_EXISTING"
TEST_KEY = "MY_APPPP"

SUPPORTED_EDITIONS = (c.DE, c.EE, c.DCE)


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    if not util.verify_support(SUPPORTED_EDITIONS, App.get_object, endpoint=util.SQ, key=EXISTING_KEY):
        return
    obj = App.get_object(endpoint=util.SQ, key=EXISTING_KEY)
    assert obj.key == EXISTING_KEY
    obj2 = App.get_object(endpoint=util.SQ, key=EXISTING_KEY)
    assert obj2.key == EXISTING_KEY
    assert obj == obj2


def test_count() -> None:
    """Verify count works"""
    if not util.verify_support(SUPPORTED_EDITIONS, apps.count, endpoint=util.SQ):
        return
    assert apps.count(util.SQ) > 0


def test_search() -> None:
    """Verify that search with criterias work"""
    if not util.verify_support(SUPPORTED_EDITIONS, apps.search, endpoint=util.SQ, params={"s": "analysisDate"}):
        return
    res_list = apps.search(endpoint=util.SQ, params={"s": "analysisDate"})
    oldest = datetime.datetime(1970, 1, 1).replace(tzinfo=datetime.timezone.utc)
    for obj in res_list.values():
        app_date = obj.last_analysis()
        if app_date and app_date != "":
            assert oldest <= app_date
            oldest = app_date


def test_get_object_non_existing() -> None:
    """Test exception raised when providing non existing portfolio key"""
    if not util.verify_support(SUPPORTED_EDITIONS, App.get_object, endpoint=util.SQ, key=NON_EXISTING_KEY):
        return
    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = App.get_object(endpoint=util.SQ, key=NON_EXISTING_KEY)
    assert str(e.value).endswith(f"Application key '{NON_EXISTING_KEY}' not found")


def test_exists(get_test_app: Generator[App]) -> None:
    """Test exist"""
    if not util.verify_support(SUPPORTED_EDITIONS, apps.exists, endpoint=util.SQ, key=EXISTING_KEY) and not util.verify_support(
        SUPPORTED_EDITIONS, apps.exists, endpoint=util.SQ, key=NON_EXISTING_KEY
    ):
        return
    obj = get_test_app
    assert apps.exists(endpoint=util.SQ, key=obj.key)
    assert not apps.exists(endpoint=util.SQ, key=NON_EXISTING_KEY)


def test_get_list() -> None:
    """Test portfolio get_list"""
    k_list = [EXISTING_KEY, EXISTING_KEY_2]
    if not util.verify_support(SUPPORTED_EDITIONS, apps.get_list, endpoint=util.SQ, key_list=k_list):
        return
    p_dict = apps.get_list(endpoint=util.SQ, key_list=k_list)
    assert sorted(k_list) == sorted(list(p_dict.keys()))


def test_create_delete(get_test_app: Generator[App]) -> None:
    """Test portfolio create delete"""
    if not util.verify_support(SUPPORTED_EDITIONS, App.create, endpoint=util.SQ, name=util.TEMP_NAME, key=util.TEMP_KEY):
        return
    obj = get_test_app
    assert obj is not None
    assert obj.key == util.TEMP_KEY
    assert obj.name == util.TEMP_KEY
    obj.delete()
    assert not apps.exists(endpoint=util.SQ, key=util.TEMP_KEY)

    # Test delete with 1 project in the app
    obj = App.create(endpoint=util.SQ, name=util.TEMP_NAME, key=util.TEMP_KEY)
    obj.add_projects(["okorach_sonar-tools"])
    obj.delete()
    assert not apps.exists(endpoint=util.SQ, key=util.TEMP_KEY)


def test_permissions_1(get_test_app: Generator[App]) -> None:
    """Test permissions"""
    if not util.verify_support(SUPPORTED_EDITIONS, App.create, endpoint=util.SQ, name="An app", key=TEST_KEY):
        return
    obj = get_test_app
    obj.set_permissions({"groups": {"sonar-users": ["user", "admin"], "sonar-administrators": ["user", "admin"]}})
    # assert apps.permissions().to_json()["groups"] == {"sonar-users": ["user", "admin"], "sonar-administrators": ["user", "admin"]}


def test_permissions_2(get_test_app: Generator[App]) -> None:
    """Test permissions"""
    if not util.verify_support(SUPPORTED_EDITIONS, App.create, endpoint=util.SQ, name=util.TEMP_NAME, key=util.TEMP_KEY):
        return
    obj = get_test_app
    obj.set_permissions({"groups": {"sonar-users": ["user"], "sonar-administrators": ["user", "admin"]}})
    # assert apps.permissions().to_json()["groups"] == {"sonar-users": ["user"], "sonar-administrators": ["user", "admin"]}


def test_get_projects() -> None:
    """test_get_projects"""
    if not util.verify_support(SUPPORTED_EDITIONS, App.get_object, endpoint=util.SQ, key=EXISTING_KEY):
        return
    obj = App.get_object(endpoint=util.SQ, key=EXISTING_KEY)
    count = len(obj.projects())
    assert count > 0
    assert len(obj.projects()) == count


def test_get_branches() -> None:
    """test_get_projects"""
    if not util.verify_support(SUPPORTED_EDITIONS, App.get_object, endpoint=util.SQ, key=EXISTING_KEY):
        return
    obj = App.get_object(endpoint=util.SQ, key=EXISTING_KEY)
    count = len(obj.branches())
    assert count > 0
    assert len(obj.branches()) == count


def test_no_audit(get_test_app: Generator[App]) -> None:
    """Check stop fast when audit params are disabled"""
    if not util.verify_support(SUPPORTED_EDITIONS, App.get_object, endpoint=util.SQ, key=EXISTING_KEY):
        return
    obj = get_test_app
    assert len(obj.audit({"audit.applications": False})) == 0
    assert len(obj._audit_empty({"audit.applications.empty": True})) == 1
    assert len(obj._audit_empty({"audit.applications.empty": False})) == 0
    obj.add_projects([util.LIVE_PROJECT])
    assert len(obj._audit_singleton({"audit.applications.singleton": True})) == 1
    assert len(obj._audit_singleton({"audit.applications.singleton": False})) == 0


def test_search_by_name() -> None:
    """test_search_by_name"""
    if not util.verify_support(SUPPORTED_EDITIONS, apps.search_by_name, endpoint=util.SQ, name="TEST_APP"):
        return
    obj = App.get_object(endpoint=util.SQ, key=EXISTING_KEY)
    other_apps = apps.search_by_name(endpoint=util.SQ, name=obj.name)

    assert len(other_apps) == 1
    first_app = list(other_apps.values())[0]
    assert obj == first_app


def test_set_tags(get_test_app: Generator[App]) -> None:
    """test_set_tags"""
    if util.SQ.edition() not in (c.DE, c.EE, c.DCE):
        pytest.skip("Apps unsupported in SonarQube Community Build and SonarQube Cloud")
    obj = get_test_app

    assert obj.set_tags(util.TAGS)
    assert obj.get_tags() == sorted(util.TAGS)
    assert obj.set_tags(["foo"])
    assert obj.get_tags() == ["foo"]
    assert obj.set_tags([])
    assert obj.get_tags() == []
    assert not obj.set_tags(None)


def test_not_found(get_test_app: Generator[App]) -> None:
    """test_not_found"""
    if util.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Apps unsupported in SonarQube Community Build and SonarQube Cloud")
    obj = get_test_app
    obj.key = "mess-me-up"
    with pytest.raises(exceptions.ObjectNotFound):
        obj.refresh()


def test_already_exists(get_test_app: Generator[App]) -> None:
    if util.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Apps unsupported in SonarQube Community Build and SonarQube Cloud")
    obj = get_test_app
    with pytest.raises(exceptions.ObjectAlreadyExists):
        _ = App.create(endpoint=util.SQ, key=obj.key, name="Foo Bar")


def test_branch_exists(get_test_app: Generator[App]) -> None:
    if util.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Apps unsupported in SonarQube Community Build and SonarQube Cloud")
    obj = get_test_app
    assert obj.branch_exists("main")
    assert not obj.branch_exists("non-existing")


def test_branch_is_main(get_test_app: Generator[App]) -> None:
    if util.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Apps unsupported in SonarQube Community Build and SonarQube Cloud")
    obj = get_test_app
    assert obj.branch_is_main("main")
    with pytest.raises(exceptions.ObjectNotFound):
        obj.branch_is_main("non-existing")


def test_get_issues(get_test_app: Generator[App]) -> None:
    if util.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Apps unsupported in SonarQube Community Build and SonarQube Cloud")
    obj = get_test_app
    assert len(obj.get_issues()) == 0


def test_audit_disabled() -> None:
    """test_audit_disabled"""
    assert len(apps.audit(util.SQ, {"audit.applications": False})) == 0


def test_app_branches(get_test_app: Generator[App]) -> None:
    if util.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Apps unsupported in SonarQube Community Build and SonarQube Cloud")
    obj = get_test_app
    definition = {
        "branches": {
            "Other Branch": {"projects": {"TESTSYNC": "some-branch", "demo:jcl": "main", "demo:java-security": "main"}},
            "BRANCH foo": {"projects": {"TESTSYNC": "some-branch", "demo:jcl": "main", "demo:java-security": "main"}, "isMain": True},
        }
    }
    obj.update(definition)
    br = obj.branches()
    assert set(br.keys()) == {"BRANCH foo", "Other Branch"}
    assert obj.main_branch().name == "BRANCH foo"
    definition = {
        "branches": {
            "MiBranch": {"projects": {"TESTSYNC": "main", "demo:jcl": "main", "demo:java-security": "main"}},
            "Master": {"projects": {"TESTSYNC": "some-branch", "demo:jcl": "main", "demo:java-security": "main"}},
            "Main Branch": {"projects": {"TESTSYNC": "some-branch", "demo:jcl": "main", "demo:java-security": "main"}, "isMain": True},
        }
    }
    obj.update(definition)
    br = obj.branches()
    assert set(br.keys()) >= {"Main Branch", "Master", "MiBranch"}
    assert obj.main_branch().name == "Main Branch"


def test_convert_for_yaml() -> None:
    if util.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Apps unsupported in SonarQube Community Build and SonarQube Cloud")
    data = apps.export(util.SQ, {})
    yaml_list = apps.convert_for_yaml(data)
    assert len(yaml_list) == len(data)
