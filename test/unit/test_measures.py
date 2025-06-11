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

""" sonar-measures-export tests """

import sys
import os
import csv
from unittest.mock import patch
import pytest

import utilities as util
from sonar import errcodes, logging
import sonar.util.constants as c

from cli import measures_export
import cli.options as opt

CMD = "sonar-measures-export.py"
CSV_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE]
CSV_OPTS_STR = " ".join(CSV_OPTS)
JSON_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]

TYPE_COL = 1
KEY_COL = 0


def test_measures_export(get_csv_file: callable) -> None:
    """test_measures_export"""
    file = get_csv_file
    util.run_success_cmd(measures_export.main, f"{CMD} {util.SQS_OPTS} --withTags -{opt.REPORT_FILE_SHORT} {file}")
    with open(file=file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        line = next(csvreader)
        rating_col_1 = line.index("reliability_rating")
        rating_col_2 = line.index("security_rating")
        pct_col_1 = line.index("duplicated_lines_density")
        pct_col_2 = line.index("sqale_debt_ratio")
        for line in csvreader:
            assert line[rating_col_1] == "" or "A" <= line[rating_col_1] <= "E"
            assert line[rating_col_2] == "" or "A" <= line[rating_col_2] <= "E"
            assert line[pct_col_1] == "" or 0.0 <= float(line[pct_col_1]) <= 1.0
            assert line[pct_col_2] == "" or 0.0 <= float(line[pct_col_2]) <= 1.0


def test_measures_conversion(get_csv_file: callable) -> None:
    """test_measures_conversion"""
    logging.set_logger("test.log")
    logging.set_debug_level("DEBUG")
    file = get_csv_file
    util.run_success_cmd(measures_export.main, f"{CMD} {util.SQS_OPTS} -r -p --withTags -{opt.REPORT_FILE_SHORT} {file}")
    with open(file=file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        line = next(csvreader)
        rating_col_1 = line.index("reliability_rating")
        rating_col_2 = line.index("security_rating")
        pct_col_1 = line.index("duplicated_lines_density")
        pct_col_2 = line.index("sqale_debt_ratio")
        for line in csvreader:
            assert line[rating_col_1] == "" or 1 <= int(line[rating_col_1]) <= 5
            assert line[rating_col_2] == "" or 1 <= int(line[rating_col_2]) <= 5
            assert line[pct_col_1] == "" or line[pct_col_1].endswith("%")
            assert line[pct_col_2] == "" or line[pct_col_2].endswith("%")


def test_measures_export_with_url() -> None:
    """test_measures_export_with_url"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"-{opt.BRANCH_REGEXP_SHORT}", ".+", f"-{opt.METRIC_KEYS_SHORT}", "_main", f"--{opt.WITH_URL}"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_measures_export_json() -> None:
    """test_measures_export_json"""
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + [f"-{opt.BRANCH_REGEXP_SHORT}", ".+", f"--{opt.METRIC_KEYS}", "_main"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_measures_export_all() -> None:
    """test_measures_export_all"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"-{opt.BRANCH_REGEXP_SHORT}", ".+", f"-{opt.METRIC_KEYS_SHORT}", "_all"]):
            measures_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_measures_export_json_all() -> None:
    """test_measures_export_json_all"""
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + [f"-{opt.BRANCH_REGEXP_SHORT}", ".+", f"-{opt.METRIC_KEYS_SHORT}", "_all"]):
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


def test_measures_export_history_as_table(get_csv_file: callable) -> None:
    """test_measures_export_history_as_table"""
    file = get_csv_file
    util.run_success_cmd(measures_export.main, f"{CMD} {util.SQS_OPTS} --history --asTable -{opt.REPORT_FILE_SHORT} {file}")


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
        with patch.object(sys, "argv", CSV_OPTS + ["--history", "--asTable", f"-{opt.BRANCH_REGEXP_SHORT}", ".+"]):
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
    util.run_success_cmd(measures_export.main, f"{CSV_OPTS_STR} -{opt.REPORT_FILE_SHORT} {util.CSV_FILE} -{opt.KEY_REGEXP_SHORT} 'bad_project'")
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        lines = len(fh.readlines())
    util.clean(util.CSV_FILE)
    # Only the header
    assert lines == 1


def test_specific_project_keys() -> None:
    """test_non_existing_project"""
    util.clean(util.CSV_FILE)
    projects = ["okorach_sonar-tools", "project1", "project4"]
    regexp = "(" + "|".join(projects) + ")"
    util.run_success_cmd(measures_export.main, f"{CSV_OPTS_STR} -{opt.KEY_REGEXP_SHORT} {regexp}")
    lines = 0
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)
        for line in reader:
            assert line[0] in projects
            assert line[TYPE_COL] == "PROJECT"
            lines += 1
    assert lines == len(projects)
    util.clean(util.CSV_FILE)

def test_apps_measures() -> None:
    """test_apps_measures"""
    EXISTING_KEY = "APP_TEST"
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--apps", "-m", "ncloc"]):
            measures_export.main()
    if util.SQ.edition() == c.CE:
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
    if util.SQ.edition() in (c.CE, c.DE):
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
    if util.SQ.edition() == c.CE:
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
    if util.SQ.edition() in (c.DE, c.CE):
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
