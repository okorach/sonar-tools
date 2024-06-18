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
    sonar-measures-export tests
"""

import sys
import os
from unittest.mock import patch
import pytest
import utilities as testutil
from sonar import errcodes
from cli import measures_export

CMD = "sonar-measures-export.py"
CSV_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.CSV_FILE]
JSON_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.JSON_FILE]


def test_measures_export() -> None:
    """test_measures_export"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_measures_conversion() -> None:
    """test_measures_conversion"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-r", "-p", "--withTags"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_measures_export_with_url() -> None:
    """test_measures_export_with_url"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-b", "-m", "_main", "--withURL"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_measures_export_json() -> None:
    """test_measures_export_json"""
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ["-b", "-m", "_main"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_measures_export_all() -> None:
    """test_measures_export_all"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-b", "-m", "_all"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_measures_export_json_all() -> None:
    """test_measures_export_json_all"""
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ["-b", "-m", "_all"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_measures_export_history() -> None:
    """test_measures_export_history"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--history", "-m", "_all"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_measures_export_history_as_table() -> None:
    """test_measures_export_history_as_table"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--history", "--asTable"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_measures_export_history_as_table_no_time() -> None:
    """test_measures_export_history_as_table_no_time"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--history", "--asTable", "-d"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_measures_export_history_as_table_with_url() -> None:
    """test_measures_export_history_as_table_with_url"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--history", "--asTable", "--withURL"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_measures_export_history_as_table_with_branch() -> None:
    """test_measures_export_history_as_table_with_url"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--history", "--asTable", "-b"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_measures_export_dateonly() -> None:
    """test_measures_export_dateonly"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-d"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_specific_measure() -> None:
    """test_specific_measure"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-m", "ncloc,sqale_index,coverage"]):
            measures_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_non_existing_measure() -> None:
    """test_non_existing_measure"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-m", "ncloc,sqale_index,bad_measure"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.ERR_NO_SUCH_KEY
    assert not os.path.isfile(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_non_existing_project() -> None:
    """test_non_existing_project"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-k", "okorach_sonar-tools,bad_project"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.ERR_NO_SUCH_KEY
    assert not os.path.isfile(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)
