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
    sonar-loc tests
"""

import sys
import os
from unittest.mock import patch
import pytest
import utilities as util
from cli import loc

CMD = "sonar-loc.py"
CSV_OPTS = [CMD] + util.STD_OPTS + ["-f", util.CSV_FILE]
JSON_OPTS = [CMD] + util.STD_OPTS + ["-f", util.JSON_FILE]


def test_loc() -> None:
    """test_loc"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS):
            loc.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_loc_json() -> None:
    """test_loc_json"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS):
            loc.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_loc_json_fmt() -> None:
    """test_loc_json_fmt"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ["--format", "json", "-n", "-a", "--withURL"]):
            loc.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_loc_project() -> None:
    """test_loc_project"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-k", "okorach_sonar-tools"]):
            loc.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_loc_project_with_all_options() -> None:
    """test_loc_project_with_all_options"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-k", "okorach_sonar-tools", "--withURL", "-n", "-a"]):
            loc.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_loc_portfolios() -> None:
    """test_loc_portfolios"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--portfolios", "--topLevelOnly", "--withURL"]):
            loc.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_loc_separator() -> None:
    """test_loc_separator"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--csvSeparator", "+"]):
            loc.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_loc_branches() -> None:
    """test_loc"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-b", "--withURL", "-a", "-n"]):
            loc.main()
    assert int(str(e.value)) == 0
    util.clean(util.CSV_FILE)


def test_loc_branches_json() -> None:
    """test_loc"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", [CMD] + util.STD_OPTS + ["-b", "-f", util.JSON_FILE, "-a", "-n", "--withURL"]):
            loc.main()
    assert int(str(e.value)) == 0
    util.clean(util.JSON_FILE)


def test_loc_portfolios_all_options() -> None:
    """test_loc"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-b", "--portfolios", "--withURL", "-a", "-n"]):
            loc.main()
    assert int(str(e.value)) == 0
    util.clean(util.CSV_FILE)
