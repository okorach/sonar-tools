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

""" sonar-measures-export tests """

import sys
import os
import csv
from unittest.mock import patch
import pytest

import utilities as util
from sonar import errcodes
from cli import measures_export
import cli.options as opt

CMD = "sonar-measures-export.py"
CSV_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.OUTPUTFILE_SHORT}", util.CSV_FILE]
JSON_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.OUTPUTFILE_SHORT}", util.JSON_FILE]

TYPE_COL = 1
KEY_COL = 0


def test_measures_export() -> None:
    """test_measures_export"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_measures_conversion() -> None:
    """test_measures_conversion"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-r", "-p", "--withTags"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_measures_export_with_url() -> None:
    """test_measures_export_with_url"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"-{opt.WITH_BRANCHES_SHORT}", f"-{opt.METRIC_KEYS_SHORT}", "_main", f"--{opt.WITH_URL}"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_measures_export_json() -> None:
    """test_measures_export_json"""
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + [f"-{opt.WITH_BRANCHES_SHORT}", f"--{opt.METRIC_KEYS}", "_main"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_measures_export_all() -> None:
    """test_measures_export_all"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"-{opt.WITH_BRANCHES_SHORT}", f"-{opt.METRIC_KEYS_SHORT}", "_all"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_measures_export_json_all() -> None:
    """test_measures_export_json_all"""
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + [f"-{opt.WITH_BRANCHES_SHORT}", f"-{opt.METRIC_KEYS_SHORT}", "_all"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_measures_export_history() -> None:
    """test_measures_export_history"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--history", f"--{opt.METRIC_KEYS}", "_all"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_measures_export_history_as_table() -> None:
    """test_measures_export_history_as_table"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--history", "--asTable"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_measures_export_history_as_table_no_time() -> None:
    """test_measures_export_history_as_table_no_time"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--history", "--asTable", "-d"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_measures_export_history_as_table_with_url() -> None:
    """test_measures_export_history_as_table_with_url"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--history", "--asTable", f"--{opt.WITH_URL}"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_measures_export_history_as_table_with_branch() -> None:
    """test_measures_export_history_as_table_with_url"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--history", "--asTable", f"-{opt.WITH_BRANCHES_SHORT}"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_measures_export_dateonly() -> None:
    """test_measures_export_dateonly"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-d"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_specific_measure() -> None:
    """test_specific_measure"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"-{opt.METRIC_KEYS_SHORT}", "ncloc,sqale_index,coverage"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_non_existing_measure() -> None:
    """test_non_existing_measure"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"-{opt.METRIC_KEYS_SHORT}", "ncloc,sqale_index,bad_measure"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.NO_SUCH_KEY
    assert not os.path.isfile(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_non_existing_project() -> None:
    """test_non_existing_project"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"-{opt.KEYS_SHORT}", "okorach_sonar-tools,bad_project"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.NO_SUCH_KEY
    assert not os.path.isfile(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_apps_measures() -> None:
    """test_apps_measures"""
    EXISTING_KEY = "APP_TEST"
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--apps", "-m", "ncloc"]):
            measures_export.main()
    if util.SQ.edition() == "community":
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
    else:
        assert int(str(e.value)) == errcodes.OK
        assert util.file_not_empty(util.CSV_FILE)
        first = True
        found = False
        with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
            for line in csv.reader(fh):
                if first:
                    first = False
                    continue
                found = found or line[KEY_COL] == EXISTING_KEY
                assert line[TYPE_COL] == "APPLICATION"
                assert len(line) == 5
        assert found
    util.clean(util.CSV_FILE)


def test_portfolios_measures() -> None:
    """test_portfolios_measures"""
    EXISTING_KEY = "PORTFOLIO_ALL"
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--portfolios", "-m", "ncloc"]):
            measures_export.main()
    if util.SQ.edition() in ("community", "developer"):
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
    else:
        assert util.file_not_empty(util.CSV_FILE)
        first = True
        found = False
        with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
            for line in csv.reader(fh):
                if first:
                    first = False
                    continue
                found = found or line[KEY_COL] == EXISTING_KEY
                assert len(line) == 5
                assert line[TYPE_COL] == "PORTFOLIO"
        assert found
    util.clean(util.CSV_FILE)


def test_basic() -> None:
    """Tests that basic invocation against a CE and DE works"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    with open(util.CSV_FILE, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        next(reader)
        for line in reader:
            assert line[TYPE_COL] == "PROJECT"


def test_option_apps() -> None:
    """Tests that using the --apps option works in the correct editions (DE and higher)"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--apps"]):
            measures_export.main()
    if util.SQ.edition() == "community":
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
        assert not os.path.isfile(util.CSV_FILE)
    else:
        assert int(str(e.value)) == errcodes.OK
        with open(util.CSV_FILE, encoding="utf-8") as fd:
            reader = csv.reader(fd)
            next(reader)
            for line in reader:
                assert line[TYPE_COL] == "APPLICATION"
    util.clean(util.CSV_FILE)


def test_option_portfolios() -> None:
    """Tests that using the --portfolios option works in the correct editions (EE and higher)"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--portfolios"]):
            measures_export.main()
    if util.SQ.edition() in ("developer", "community"):
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
        assert not os.path.isfile(util.CSV_FILE)
    else:
        assert int(str(e.value)) == errcodes.OK
        with open(util.CSV_FILE, encoding="utf-8") as fd:
            reader = csv.reader(fd)
            next(reader)
            for line in reader:
                assert line[TYPE_COL] == "PORTFOLIO"
    util.clean(util.CSV_FILE)
