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


"""
sonar-housekeeper tests
"""

from collections.abc import Generator
import pytest

import utilities as tutil
from sonar import errcodes
from cli import housekeeper, options

CMD = "sonar-housekeeper.py"
__GOOD_OPTS = ["", f"--{options.NBR_THREADS} 1", "-P 30", f"--{options.HTTP_TIMEOUT} 100"]


def test_housekeeper() -> None:
    """test_housekeeper"""
    for opts in __GOOD_OPTS:
        assert tutil.run_cmd(housekeeper.main, f"{CMD} {tutil.SQS_OPTS} {opts}") == errcodes.OK


def test_keep_branches_override(csv_file: Generator[str]) -> None:
    """test_keep_branches_override"""
    if tutil.SQ.version() == "community":
        pytest.skip("No branches in Community")
    opts = f"{CMD} {tutil.SQS_OPTS} -P 730 -T 730 -R 730 -B 90 -f {csv_file}"
    assert tutil.run_cmd(housekeeper.main, opts) == errcodes.OK
    nbr_br = tutil.csv_col_count_values(csv_file, "Audit Check", "BRANCH_LAST_ANALYSIS")
    assert tutil.run_cmd(housekeeper.main, f"{opts} --keepWhenInactive 'dontkeepanything'") == errcodes.OK
    # With 'dontkeepanything' as branch regexp, more branches to delete should be found
    assert tutil.csv_col_count_values(csv_file, "Audit Check", "BRANCH_LAST_ANALYSIS") > nbr_br
