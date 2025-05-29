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

import datetime
import sonar.util.update_center as uc


def test_get_upd_center_data():
    upd = uc.get_update_center_properties()
    assert len(upd) > 0


def test_lta():
    """Test the LTA"""
    now = datetime.datetime.now()
    year, month = now.year, now.month
    if month == 1:
        year -= 1
    lta = uc.get_lta()
    assert lta[:2] == (year, 1)


def test_latest():
    """Test the LATEST"""
    now = datetime.datetime.now()
    year, month = now.year, now.month
    if month == 1:
        month = 12
        year -= 1
    digit = month // 2
    assert uc.get_latest()[:2] == (year, digit)


def test_release_date():
    """Test the release date"""
    dates = {"10.2": "2023-09-01", "5.4": "2016-03-08", "8.0": "2019-10-16", "9.7.1": "2022-10-28", "2025.2": "2025-03-26", "25.2": "2025-02-03"}
    for version, date_str in dates.items():
        release_date = uc.get_release_date(tuple(version.split(".")))
        assert release_date == datetime.datetime.strptime(date_str, "%Y-%m-%d").date()

    assert uc.get_release_date((9, 10, 3)) is None


def tes_get_registered_plugins():
    """Test the registered plugins"""
    plugin_list = ["authaad", "clover", "ecocodephp"]
    plugins = uc.get_registered_plugins()
    assert len(plugins) > 0
    for plugin in plugin_list:
        assert plugin in plugins
