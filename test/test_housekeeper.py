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
import pytest
import utilities as testutil
from tools import housekeeper

CMD = "sonar-housekeeper.py"
__GOOD_OPTS = [
    [],
    ["--threads", "1"],
    ["-P", "30"],
]


def test_housekeeper() -> None:
    """test_housekeeper"""
    for opts in __GOOD_OPTS:
        with pytest.raises(SystemExit) as e:
            with patch.object(sys, "argv", [CMD] + testutil.STD_OPTS + opts):
                housekeeper.main()
        assert int(str(e.value)) == 0
