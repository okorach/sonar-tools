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

"""Groups tests"""

from collections.abc import Generator

import pytest

import utilities as tutil
from sonar import exceptions
from sonar import groups, users
from sonar.util import constants as c

GROUP1 = tutil.SQ.default_user_group()
GROUP2 = "sonar-administrators"


def test_get_object() -> None:
    """Test group get_obejct"""
    for name in GROUP1, GROUP2:
        gr = groups.Group.get_object(endpoint=tutil.SQ, name=name)
        assert gr.name == name
        assert str(gr) == f"group '{name}'"

    gr2 = groups.Group.get_object(endpoint=tutil.SQ, name=GROUP2)
    assert gr is gr2

    gr3 = groups.Group.read(endpoint=tutil.SQ, name=GROUP2)
    assert gr3 is gr

    with pytest.raises(exceptions.ObjectNotFound):
        groups.Group.get_object(endpoint=tutil.SQ, name=tutil.NON_EXISTING_KEY)


def test_more_than_50_groups(get_60_groups: Generator[list[groups.Group]]) -> None:
    # Count groups first
    group_list = get_60_groups
    groups.Group.clear_cache()
    new_group_list = groups.get_list(tutil.SQ)
    assert len(new_group_list) > 60
    assert set(new_group_list.keys()) > {g.name for g in group_list}


def test_read_non_existing() -> None:
    with pytest.raises(exceptions.ObjectNotFound):
        groups.Group.read(endpoint=tutil.SQ, name=tutil.NON_EXISTING_KEY)


def test_create_already_exists(get_test_group: Generator[groups.Group]) -> None:
    gr = get_test_group
    with pytest.raises(exceptions.ObjectAlreadyExists):
        groups.Group.create(endpoint=tutil.SQ, name=gr.name)


def test_size() -> None:
    gr = groups.Group.get_object(endpoint=tutil.SQ, name=tutil.SQ.default_user_group())
    assert gr.size() > 4


def test_url() -> None:
    gr = groups.Group.get_object(endpoint=tutil.SQ, name=tutil.SQ.default_user_group())
    assert gr.url() == f"{tutil.SQ.external_url}/admin/groups"


def test_add_non_existing_user(get_test_group: Generator[groups.Group], get_test_user: Generator[users.User]) -> None:
    gr = get_test_group
    u = get_test_user
    u.login = tutil.NON_EXISTING_KEY
    u.id = tutil.NON_EXISTING_KEY
    with pytest.raises(exceptions.ObjectNotFound):
        gr.add_user(u)


def test_remove_non_existing_user(get_test_group: Generator[groups.Group], get_test_user: Generator[users.User]) -> None:
    tutil.start_logging()
    gr = get_test_group
    u = get_test_user
    try:
        gr.remove_user(u)
    except exceptions.ObjectNotFound:
        pass
    gr.add_user(u)
    u.id = tutil.NON_EXISTING_KEY
    u.login = tutil.NON_EXISTING_KEY
    with pytest.raises(exceptions.ObjectNotFound):
        gr.remove_user(u)


def test_audit_empty(get_test_group: Generator[groups.Group]) -> None:
    gr = get_test_group
    settings = {"audit.groups.empty": True}
    assert len(gr.audit(settings)) == 1


def test_to_json(get_test_group: Generator[groups.Group]) -> None:
    gr = get_test_group
    json_data = gr.to_json()
    assert json_data["name"] == tutil.TEMP_KEY
    assert "description" not in json_data

    assert gr.set_description("A test group")
    json_data = gr.to_json()
    assert json_data["description"] == "A test group"

    assert not gr.set_description(None)
    assert json_data["description"] == "A test group"

    if tutil.SQ.version() >= c.GROUP_API_V2_INTRO_VERSION:
        assert "id" in gr.to_json(True)

    sonar_users = groups.Group.get_object(tutil.SQ, tutil.SQ.default_user_group())
    json_exp = sonar_users.to_json()
    assert "default" in json_exp


def test_import() -> None:
    data = {}
    groups.import_config(tutil.SQ, data)
    data = {
        "groups": [
            {"name": "Group1", "description": "This is Group1"},
            {"name": "Group2", "description": "This is Group2"},
            {"name": "Group3", "description": "This is Group3"},
        ]
    }
    groups.import_config(tutil.SQ, data)
    for g in "Group1", "Group2", "Group3":
        assert groups.exists(endpoint=tutil.SQ, name=g)
        o_g = groups.Group.get_object(endpoint=tutil.SQ, name=g)
        assert o_g.description == f"This is {g}"
        o_g.delete()


def test_set_name(get_test_group: Generator[groups.Group]) -> None:
    gr = get_test_group
    assert gr.name == tutil.TEMP_KEY
    assert not gr.set_name(gr.name)
    assert not gr.set_name(None)
    assert gr.name == tutil.TEMP_KEY
    gr.set_name("FOOBAR")
    assert gr.name == "FOOBAR"


def test_create_or_update(get_test_group: Generator[groups.Group]) -> None:
    gr = get_test_group
    gr2 = groups.create_or_update(tutil.SQ, gr.name, "Some new group description")
    assert gr2 is gr
    assert gr.description == "Some new group description"


def test_api_params(get_test_group: Generator[groups.Group]) -> None:
    gr = get_test_group
    if tutil.SQ.version() >= c.GROUP_API_V2_INTRO_VERSION:
        assert gr.api_params(c.GET) == {}
        assert gr.api_params(c.CREATE) == {}
    else:
        assert gr.api_params(c.GET) == {"name": tutil.TEMP_KEY}
        assert gr.api_params(c.CREATE) == {"name": tutil.TEMP_KEY}


def test_get_from_id(get_test_group: Generator[groups.Group]) -> None:
    gr = get_test_group
    if tutil.SQ.version() >= c.GROUP_API_V2_INTRO_VERSION:
        gr2 = groups.get_object_from_id(tutil.SQ, gr.id)
        assert gr2 is gr
    else:
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = groups.get_object_from_id(tutil.SQ, gr.id)
