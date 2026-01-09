#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2026 Olivier Korach
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

"""Common tests, independent of SonarQube version"""

from cli import sonar_tools
from sonar import errcodes
from sonar.util import misc as util
from sonar.util import sonar_cache
import utilities as tutil


def test_deduct_fmt() -> None:
    """test_deduct_fmt"""
    assert util.deduct_format("csv", None) == "csv"
    assert util.deduct_format("foo", "file.csv") == "csv"
    assert util.deduct_format("foo", "file.json") == "csv"
    assert util.deduct_format(None, "file.json") == "json"
    assert util.deduct_format(None, "file.csv") == "csv"
    assert util.deduct_format(None, "file.txt") == "csv"


def test_clear_cache() -> None:
    """Clears the SonarQube caches before running tests on SC"""
    sonar_cache.clear()


def test_sonar_tools_help() -> None:
    """test_sonar_tools_help"""
    assert tutil.run_cmd(sonar_tools.main, "sonar-tools") == errcodes.OK
