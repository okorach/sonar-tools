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
import sonar.logging as log
from sonar import applications, exceptions

EXISTING_KEY = "APP_TEST"
EXISTING_KEY_2 = "APP_TEST_2"
NON_EXISTING_KEY = "NON_EXISTING"
TEST_KEY = "MY_APPPP"


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.Application.get_object(endpoint=util.SQ, key=EXISTING_KEY)
    else:
        app = applications.Application.get_object(endpoint=util.SQ, key=EXISTING_KEY)
        assert app.key == EXISTING_KEY
        app2 = applications.Application.get_object(endpoint=util.SQ, key=EXISTING_KEY)
        assert app2.key == EXISTING_KEY
        assert app == app2


def test_count() -> None:
    """Verify count works"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.count(util.SQ)
    else:
        assert applications.count(util.SQ) > 0


def test_search() -> None:
    """Verify that search with criterias work"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.search(endpoint=util.SQ, params={"s": "analysisDate"})
    else:
        res_list = applications.search(endpoint=util.SQ, params={"s": "analysisDate"})
        oldest = datetime.datetime(1970, 1, 1).replace(tzinfo=datetime.timezone.utc)
        for app in res_list.values():
            app_date = app.last_analysis()
            if app_date and app_date != "":
                assert oldest <= app_date
                oldest = app_date


def test_get_object_non_existing() -> None:
    """Test exception raised when providing non existing portfolio key"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.Application.get_object(endpoint=util.SQ, key=NON_EXISTING_KEY)
    else:
        with pytest.raises(exceptions.ObjectNotFound) as e:
            _ = applications.Application.get_object(endpoint=util.SQ, key=NON_EXISTING_KEY)
        assert str(e.value).endswith(f"Application key '{NON_EXISTING_KEY}' not found")


def test_exists(get_test_app) -> None:
    """Test exist"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.exists(endpoint=util.SQ, key=EXISTING_KEY)
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.exists(endpoint=util.SQ, key=NON_EXISTING_KEY)
    else:
        app = get_test_app
        assert applications.exists(endpoint=util.SQ, key=app.key)
        assert not applications.exists(endpoint=util.SQ, key=NON_EXISTING_KEY)


def test_get_list() -> None:
    """Test portfolio get_list"""
    k_list = [EXISTING_KEY, EXISTING_KEY_2]
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.get_list(endpoint=util.SQ, key_list=k_list)
    else:
        p_dict = applications.get_list(endpoint=util.SQ, key_list=k_list)
        assert sorted(k_list) == sorted(list(p_dict.keys()))


def test_create_delete() -> None:
    """Test portfolio create delete"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.Application.create(endpoint=util.SQ, name=util.TEMP_NAME, key=util.TEMP_KEY)
    else:
        app = applications.Application.create(endpoint=util.SQ, name=util.TEMP_NAME, key=util.TEMP_KEY)
        assert app is not None
        assert app.key == util.TEMP_KEY
        assert app.name == util.TEMP_NAME
        app.delete()
        assert not applications.exists(endpoint=util.SQ, key=util.TEMP_KEY)

        # Test delete with 1 project in the app
        app = applications.Application.create(endpoint=util.SQ, name=util.TEMP_NAME, key=util.TEMP_KEY)
        app.add_projects(["okorach_sonar-tools"])
        app.delete()
        assert not applications.exists(endpoint=util.SQ, key=util.TEMP_KEY)


def test_permissions_1(get_test_app) -> None:
    """Test permissions"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.Application.create(endpoint=util.SQ, name="An app", key=TEST_KEY)
    else:
        app = get_test_app
        app.set_permissions({"groups": {"sonar-users": ["user", "admin"], "sonar-administrators": ["user", "admin"]}})
        # assert app.permissions().to_json()["groups"] == {"sonar-users": ["user", "admin"], "sonar-administrators": ["user", "admin"]}


def test_permissions_2(get_test_app) -> None:
    """Test permissions"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.Application.create(endpoint=util.SQ, name=util.TEMP_NAME, key=util.TEMP_KEY)
    else:
        app = get_test_app
        app.set_permissions({"groups": {"sonar-users": ["user"], "sonar-administrators": ["user", "admin"]}})
        # assert app.permissions().to_json()["groups"] == {"sonar-users": ["user"], "sonar-administrators": ["user", "admin"]}


def test_get_projects() -> None:
    """test_get_projects"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.Application.get_object(endpoint=util.SQ, key=EXISTING_KEY)
    else:
        app = applications.Application.get_object(endpoint=util.SQ, key=EXISTING_KEY)
        count = len(app.projects())
        assert count > 0
        assert len(app.projects()) == count


def test_get_branches() -> None:
    """test_get_projects"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.Application.get_object(endpoint=util.SQ, key=EXISTING_KEY)
    else:
        app = applications.Application.get_object(endpoint=util.SQ, key=EXISTING_KEY)
        count = len(app.branches())
        assert count > 0
        assert len(app.branches()) == count


def test_no_audit() -> None:
    """Check stop fast when audit params are disabled"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.Application.get_object(endpoint=util.SQ, key=EXISTING_KEY)
    else:
        app = applications.Application.get_object(endpoint=util.SQ, key=EXISTING_KEY)
        assert len(app.audit({"audit.applications": False})) == 0
        assert len(app._audit_empty({"audit.applications.empty": False})) == 0
        assert len(app._audit_singleton({"audit.applications.singleton": False})) == 0


def test_search_by_name() -> None:
    """test_search_by_name"""
    if util.SQ.edition() == "community":
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = applications.search_by_name(endpoint=util.SQ, name="TEST_APP")
    else:
        app = applications.Application.get_object(endpoint=util.SQ, key=EXISTING_KEY)
        other_apps = applications.search_by_name(endpoint=util.SQ, name=app.name)

        assert len(other_apps) == 1
        first_app = list(other_apps.values())[0]
        assert app == first_app


def test_set_tags(get_test_app: Generator[applications.Application]) -> None:
    """test_set_tags"""
    o = get_test_app

    assert o.set_tags(util.TAGS)
    assert o.get_tags() == sorted(util.TAGS)
    assert o.set_tags(["foo"])
    assert o.get_tags() == ["foo"]
    assert o.set_tags([])
    assert o.get_tags() == []
    assert not o.set_tags(None)


def test_not_found(get_test_app: Generator[applications.Application]) -> None:
    """test_not_found"""
    if util.SQ.edition() != "community":
        o = get_test_app
        o.key = "mess-me-up"
        with pytest.raises(exceptions.ObjectNotFound):
            o.refresh()


def test_already_exists(get_test_app: Generator[applications.Application]) -> None:
    if util.SQ.edition() != "community":
        app = get_test_app
        with pytest.raises(exceptions.ObjectAlreadyExists):
            _ = applications.Application.create(endpoint=util.SQ, key=app.key, name="Foo Bar")


def test_branch_exists(get_test_app: Generator[applications.Application]) -> None:
    if util.SQ.edition() != "community":
        app = get_test_app
        assert app.branch_exists("main")
        assert not app.branch_exists("non-existing")


def test_branch_is_main(get_test_app: Generator[applications.Application]) -> None:
    if util.SQ.edition() != "community":
        app = get_test_app
        assert app.branch_is_main("main")
        with pytest.raises(exceptions.ObjectNotFound):
            app.branch_is_main("non-existing")


def test_get_issues(get_test_app: Generator[applications.Application]) -> None:
    if util.SQ.edition() != "community":
        app = get_test_app
        assert len(app.get_issues()) == 0


def test_audit_disabled() -> None:
    """test_audit_disabled"""
    assert len(applications.audit(util.SQ, {"audit.applications": False})) == 0


def test_app_branches(get_test_application: Generator[applications.Application]) -> None:
    app = get_test_application
    definition = {
        "branches": {
            "Other Branch": {"projects": {"TESTSYNC": "some-branch", "demo:jcl": "main", "training:security": "main"}},
            "BRANCH foo": {"projects": {"TESTSYNC": "some-branch", "demo:jcl": "main", "training:security": "main"}, "isMain": True},
        }
    }
    app.update(definition)
    br = app.branches()
    assert set(br.keys()) == {"BRANCH foo", "Other Branch"}
    assert app.main_branch().name == "BRANCH foo"
    definition = {
        "branches": {
            "MiBranch": {"projects": {"TESTSYNC": "main", "demo:jcl": "main", "training:security": "main"}},
            "Master": {"projects": {"TESTSYNC": "some-branch", "demo:jcl": "main", "training:security": "main"}},
            "Main Branch": {"projects": {"TESTSYNC": "some-branch", "demo:jcl": "main", "training:security": "main"}, "isMain": True},
        }
    }
    app.update(definition)
    br = app.branches()
    assert set(br.keys()) >= {"Main Branch", "Master", "MiBranch"}
    assert app.main_branch().name == "Main Branch"


def test_convert_for_yaml() -> None:
    if util.SQ.edition() != "community":
        data = applications.export(util.SQ, {})
        yaml_list = applications.convert_for_yaml(data)
        assert len(yaml_list) == len(data)
