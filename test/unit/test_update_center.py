#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2025 Olivier Korach
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

""" update_center tests """

import sonar.util.update_center as uc


def test_get_upd_center_data():
    upd = uc.get_update_center_properties()
    assert len(upd) > 0


def test_lta():
    """Test the hardcoded LTA date"""
    lta = uc.get_lta()
    assert lta[:2] == (2025, 1)


def test_latest():
    """Test the hardcoded LTA date"""
    latest = uc.get_latest()
    assert latest[0] == (2025, 3)
