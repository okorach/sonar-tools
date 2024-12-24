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

""" Groups tests """

from collections.abc import Generator

import pytest

import utilities as util
from sonar import exceptions
from sonar import groups

GROUP1 = "sonar-users"
GROUP2 = "sonar-administrators"


def test_get_object() -> None:
    """Test group get_obejct"""
    for name in GROUP1, GROUP2:
        gr = groups.Group.get_object(endpoint=util.SQ, name=name)
        assert gr.name == name
        assert str(gr) == f"group '{name}'"

    gr2 = groups.Group.get_object(endpoint=util.SQ, name=GROUP2)
    assert gr is gr2

    with pytest.raises(exceptions.ObjectNotFound):
        groups.Group.get_object(endpoint=util.SQ, name=util.NON_EXISTING_KEY)


def test_more_than_50_groups(get_60_groups: Generator[list[groups.Group]]) -> None:
    # Count groups first
    group_list = get_60_groups
    groups.Group.clear_cache()
    new_group_list = groups.get_list(util.SQ)
    assert len(new_group_list) > 60
    assert set(new_group_list.keys()) > set(g.name for g in group_list)
