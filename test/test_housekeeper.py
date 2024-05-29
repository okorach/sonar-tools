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


"""
    sonar-housekeeper tests
"""

import sys
from unittest.mock import patch
import utilities as testutil
from tools import housekeeper

CMD = "sonar-housekeeper.py"


def test_housekeeper() -> None:
    """test_housekeeper"""
    with patch.object(sys, "argv", [CMD] + testutil.STD_OPTS):
        try:
            housekeeper.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert True


def test_housekeeper_2() -> None:
    """test_housekeeper_2"""
    with patch.object(sys, "argv", [CMD] + testutil.STD_OPTS + ["--threads", "1"]):
        try:
            housekeeper.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert True


def test_housekeeper_3() -> None:
    """test_housekeeper_3"""
    with patch.object(sys, "argv", [CMD] + testutil.STD_OPTS + ["-P", "30"]):
        try:
            housekeeper.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert True
