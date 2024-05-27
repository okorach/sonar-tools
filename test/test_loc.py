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

import sys
from unittest.mock import patch
import test.utilities as testutil
from tools import loc

CMD = "sonar-loc.py"
CSV_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.CSV_FILE]
JSON_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.JSON_FILE]


def test_loc():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS):
        try:
            loc.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_loc_json():
    testutil.clean(testutil.JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS):
        try:
            loc.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_loc_json_fmt():
    testutil.clean(testutil.JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--format", "json", "-n", "-a", "--withURL"]):
        try:
            loc.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_loc_project():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["-k", "okorach_sonar-tools"]):
        try:
            loc.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_loc_project_with_all_options():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["-k", "okorach_sonar-tools", "--withURL", "-n", "-a"]):
        try:
            loc.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_loc_portfolios():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--portfolios", "--topLevelOnly", "--withURL"]):
        try:
            loc.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_loc_separator():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--csvSeparator", "+"]):
        try:
            loc.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)
