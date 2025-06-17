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
from collections.abc import Generator
from unittest.mock import patch

import utilities as util
from sonar import errcodes, logging, utilities
import sonar.util.constants as c

from cli import measures_export
import cli.options as opt

CMD = "sonar-measures-export.py"
CMD = f"{CMD} {util.SQS_OPTS}"

TYPE_COL = 1
KEY_COL = 0


def test_measures_export(csv_file: Generator[str]) -> None:
    """test_measures_export"""
    util.run_success_cmd(measures_export.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --withTags")
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
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


def test_measures_conversion(csv_file: Generator[str]) -> None:
    """test_measures_conversion"""
    util.run_success_cmd(measures_export.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -r -p --withTags")
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
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


def test_measures_export_with_url(csv_file: Generator[str]) -> None:
    """test_measures_export_with_url"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.BRANCH_REGEXP_SHORT} .+ -{opt.METRIC_KEYS_SHORT} _main --{opt.WITH_URL}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
    else:
        util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_json(json_file: Generator[str]) -> None:
    """test_measures_export_json"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {json_file} -{opt.BRANCH_REGEXP_SHORT} .+ -{opt.METRIC_KEYS_SHORT} _main"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
    else:
        util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_all(csv_file: Generator[str]) -> None:
    """test_measures_export_all"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.METRIC_KEYS_SHORT} _all"
    if util.SQ.edition() != c.CE:
        cmd += f" -{opt.BRANCH_REGEXP_SHORT} .+"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_json_all(json_file: Generator[str]) -> None:
    """test_measures_export_json_all"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {json_file} --{opt.METRIC_KEYS} _all"
    if util.SQ.edition() != c.CE:
        cmd += f" -{opt.BRANCH_REGEXP_SHORT} .+"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_history(csv_file: Generator[str]) -> None:
    """test_measures_export_history"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --{opt.METRIC_KEYS} _all"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_history_as_table(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_history_as_table_no_time(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table_no_time"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable -d"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_history_as_table_with_url(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table_with_url"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable --{opt.WITH_URL}"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_history_as_table_with_branch(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table_with_branch"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable"
    if util.SQ.edition() != c.CE:
        cmd += f" -{opt.BRANCH_REGEXP_SHORT} .+"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_dateonly(csv_file: Generator[str]) -> None:
    """test_measures_export_dateonly"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -d"
    util.run_success_cmd(measures_export.main, cmd)


def test_specific_measure(csv_file: Generator[str]) -> None:
    """test_specific_measure"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.METRIC_KEYS_SHORT} ncloc,sqale_index,coverage"
    util.run_success_cmd(measures_export.main, cmd)


def test_non_existing_measure(csv_file: Generator[str]) -> None:
    """test_non_existing_measure"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.METRIC_KEYS_SHORT} ncloc,sqale_index,bad_measure"
    util.run_failed_cmd(measures_export.main, cmd, errcodes.NO_SUCH_KEY)


def test_non_existing_project(csv_file: Generator[str]) -> None:
    """test_non_existing_project"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.KEY_REGEXP_SHORT} bad_project"
    util.run_success_cmd(measures_export.main, cmd)
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        lines = len(fh.readlines())
    assert lines == 1  # Only the header


def test_specific_project_keys(csv_file: Generator[str]) -> None:
    """test_non_existing_project"""
    projects = ["okorach_sonar-tools", "project1", "project4"]
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.KEY_REGEXP_SHORT} {utilities.list_to_regexp(projects)}"
    util.run_success_cmd(measures_export.main, cmd)
    lines = 0
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)
        for line in reader:
            assert line[0] in projects
            assert line[TYPE_COL] == "PROJECT"
            lines += 1
    assert lines == len(projects)


def test_apps_measures(csv_file: Generator[str]) -> None:
    """test_apps_measures"""
    EXISTING_KEY = "APP_TEST"
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --{opt.APPS} -m ncloc"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return
    util.run_success_cmd(measures_export.main, cmd)
    found = False
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)
        for line in reader:
            found = found or line[KEY_COL] == EXISTING_KEY
            assert line[TYPE_COL] == "APPLICATION"
            assert len(line) == 5
    assert found


def test_portfolios_measures(csv_file: Generator[str]) -> None:
    """test_portfolios_measures"""
    EXISTING_KEY = "PORTFOLIO_ALL"
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --portfolios -m ncloc"
    if util.SQ.edition() in (c.CE, c.DE):
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(measures_export.main, cmd)
    found = False
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)
        for line in reader:
            found = found or line[KEY_COL] == EXISTING_KEY
            assert line[TYPE_COL] == "PORTFOLIO"
            assert len(line) == 5
    assert found


def test_basic(csv_file: Generator[str]) -> None:
    """Tests that basic invocation against a CE and DE works"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file}"
    util.run_success_cmd(measures_export.main, cmd)
    with open(csv_file, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        next(reader)
        for line in reader:
            assert line[TYPE_COL] == "PROJECT"


def test_option_apps(csv_file: Generator[str]) -> None:
    """Tests that using the --apps option works in the correct editions (DE and higher)"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.APPS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(measures_export.main, cmd)
    with open(csv_file, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        next(reader)
        for line in reader:
            assert line[TYPE_COL] == "APPLICATION"


def test_option_portfolios(csv_file: Generator[str]) -> None:
    """Tests that using the --portfolios option works in the correct editions (EE and higher)"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.PORTFOLIOS}"
    if util.SQ.edition() in (c.CE, c.DE):
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(measures_export.main, cmd)
    with open(csv_file, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        next(reader)
        for line in reader:
            assert line[TYPE_COL] == "PORTFOLIO"
