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

""" users tests """

from collections.abc import Generator
from datetime import datetime
import pytest

import utilities as util
from sonar import exceptions, logging
from sonar import users

USER = "admin"


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    users.User.CACHE.clear()
    for _ in range(2):
        user = users.User.get_object(endpoint=util.SQ, login=USER)
        assert str(user) == f"user '{USER}'"
        assert "sonar-administrators" in user.groups()
        assert "sonar-users" in user.groups()

    with pytest.raises(exceptions.ObjectNotFound):
        users.User.get_object(endpoint=util.SQ, login="non-exitsing-user")


def test_create_delete(get_test_user: Generator[users.User]) -> None:
    """test_create_delete"""
    user = get_test_user
    assert user.login == util.TEMP_KEY
    assert "sonar-users" in user.groups()

    u = users.User.get_object(util.SQ, login=util.TEMP_KEY)
    assert u is user

    user.name = "TEMP_USER"
    user.refresh()
    assert user.name == f"User name {util.TEMP_KEY}"
    assert user.url() == f"{util.SQ.url}/admin/users"


def test_add_to_group(get_test_user: Generator[users.User]) -> None:
    """test_add_to_group"""
    user = get_test_user

    with pytest.raises(exceptions.ObjectNotFound):
        user.add_to_group("non-existing-group")

    with pytest.raises(exceptions.UnsupportedOperation):
        user.add_to_group("sonar-users")

    assert user.add_to_group("sonar-administrators")
    user.refresh()
    assert "sonar-administrators" in user.groups()
    assert user.remove_from_group("sonar-administrators")
    user.refresh()
    assert "sonar-administrators" not in user.groups()


def test_remove_from_group(get_test_user: Generator[users.User]) -> None:
    """test_add_to_group"""
    user = get_test_user

    with pytest.raises(exceptions.UnsupportedOperation):
        user.remove_from_group("sonar-users")

    with pytest.raises(exceptions.ObjectNotFound):
        user.remove_from_group("non-existing-group")


def test_set_groups_2(get_test_user: Generator[users.User]) -> None:
    """test_set_groups_2"""
    user = get_test_user
    # TODO(@okorach): Pick groups that exist in SonarQube
    groups = ["quality-managers", "tech-leads"]
    for g in groups:
        if g in user.groups():
            assert user.remove_from_group(g)
    user.refresh()
    for g in groups:
        assert g not in user.groups()
    assert user.set_groups(groups)


def test_scm_accounts(get_test_user: Generator[users.User]) -> None:
    """test_scm_accounts"""
    user = get_test_user
    assert not user.add_scm_accounts([])
    user.set_scm_accounts([])
    scm_1 = ["john.doe@acme.com", "jdoe@gmail.com"]
    user.add_scm_accounts(scm_1)
    assert sorted(user.scm_accounts) == sorted(scm_1)
    scm_2 = ["jdoe@acme.com", "jdoe@live.com"]
    user.set_scm_accounts(scm_2)
    assert sorted(user.scm_accounts) == sorted(scm_2)
    user.add_scm_accounts(scm_1)
    assert sorted(user.scm_accounts) == sorted(list(set(scm_1) | set(scm_2)))


def test_audit_user() -> None:
    """audit_user"""
    logging.set_logger(util.TEST_LOGFILE)
    logging.set_debug_level("DEBUG")
    user = users.User.get_object(util.SQ, "admin")
    assert user.audit({"audit.tokens.neverExpire": "admin"}) == []
    assert len(user.audit({})) > 0


def test_audit_disabled() -> None:
    """test_audit_disabled"""
    assert len(users.audit(util.SQ, {"audit.users": False})) == 0


def test_login_from_name(get_test_user: Generator[users.User]) -> None:
    """test_login_from_name"""
    _ = get_test_user
    name = f"User name {util.TEMP_KEY}"
    assert users.get_login_from_name(util.SQ, name) == util.TEMP_KEY

    name = "Non existing name"
    assert users.get_login_from_name(util.SQ, name) is None

    try:
        user2 = users.User.create(endpoint=util.SQ, login=f"bb{util.TEMP_KEY}aa", name=f"User name bb{util.TEMP_KEY}aa")
    except exceptions.ObjectAlreadyExists:
        user2 = users.User.get_object(util.SQ, login=f"bb{util.TEMP_KEY}aa")
    assert users.get_login_from_name(util.SQ, f"User name bb{util.TEMP_KEY}aa") == user2.login


def test_convert_for_yaml() -> None:
    """test_convert_for_yaml"""
    json_exp = users.export(util.SQ, export_settings={"FULL_EXPORT": True})
    yaml_exp = users.convert_for_yaml(json_exp)
    assert len(json_exp) > 0
    assert isinstance(json_exp, dict)
    assert isinstance(yaml_exp, list)
    assert len(yaml_exp) == len(json_exp)


def test_more_than_50_users(get_60_users: Generator[list[users.User]]) -> None:
    # Count groups first
    user_list = get_60_users
    users.User.clear_cache()
    new_user_list = users.get_list(util.SQ)
    assert len(new_user_list) > 60
    assert set(new_user_list.keys()) > set(u.name for u in user_list)


def test_update(get_test_user: Generator[users.User]) -> None:
    # test_update
    user = get_test_user
    assert user.groups() == ["sonar-users"]
    assert user.login == util.TEMP_KEY
    assert user.name == f"User name {util.TEMP_KEY}"

    user.update(groups=["sonar-administrators"])
    assert sorted(user.groups()) == ["sonar-administrators", "sonar-users"]

    assert user.scm_accounts == []

    user.update(scmAccounts=["foo@gmail.com", "bar@gmail.com", "foo", "bar"])
    assert sorted(user.scm_accounts) == sorted(["foo@gmail.com", "bar@gmail.com", "foo", "bar"])

    if util.SQ.version() >= (10, 4, 0):
        new_login = f"johndoe{str(datetime.now()).replace(' ', '').replace(':', '')}"
        user.update(login=new_login)
        assert user.login == new_login

    user.update(name="John Doe", email="john@doe.com")
    assert user.name == "John Doe"
    assert user.email == "john@doe.com"

    if util.SQ.version() >= (10, 4, 0):
        new_login = f"johndoe{str(datetime.now()).replace(' ', '-').replace(':', '-')}"
        user.update(login=new_login, email="john@doe.com")
        assert user.login == new_login


def test_set_groups(get_test_user: Generator[users.User]) -> None:
    """test_set_groups"""
    user = get_test_user
    user.set_groups(["sonar-administrators", "language-experts"])
    assert sorted(user.groups()) == sorted(["sonar-users", "sonar-administrators", "language-experts"])

    user.set_groups(["language-experts", "security-auditors", "developers"])
    assert sorted(user.groups()) == sorted(["sonar-users", "language-experts", "security-auditors", "developers"])


def test_import() -> None:
    data = {}
    users.import_config(util.SQ, data)
    now_str = {str(datetime.now()).replace(" ", "-").replace(":", "-")}
    data = {
        "users": {
            "TEMP": {"local": True, "name": "User name TEMP", "scmAccounts": "temp@acme.com, temp@gmail.com"},
            "TEMP_ADMIN": {
                "email": "admin@acme.com",
                "groups": "sonar-administrators",
                "local": True,
                "name": "User name TEMP_ADMIN",
                "scmAccounts": f"admin-acme{now_str}, administrator-acme{now_str}",
            },
        }
    }
    users.import_config(util.SQ, data)
    for uname in "TEMP", "TEMP_ADMIN":
        assert users.exists(endpoint=util.SQ, login=uname)
        o_g = users.User.get_object(endpoint=util.SQ, login=uname)
        assert o_g.name == f"User name {uname}"
        o_g.delete()


def test_deactivate(get_test_user: Generator[users.User]) -> None:
    user = get_test_user
    assert user.deactivate()
