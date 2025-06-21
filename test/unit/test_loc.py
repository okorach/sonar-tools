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
    sonar-loc tests
"""

import csv, json
from collections.abc import Generator
from unittest.mock import patch
import utilities as util
from sonar import errcodes
import sonar.util.constants as c

from cli import loc
import cli.options as opt

CLI = "sonar-loc.py"
CMD = f"{CLI} {util.SQS_OPTS} --skipVersionCheck"
ALL_OPTIONS = f"-{opt.BRANCH_REGEXP_SHORT} .+ --{opt.WITH_LAST_ANALYSIS} --{opt.WITH_NAME} --{opt.WITH_URL}"


def test_loc(csv_file: Generator[str]) -> None:
    """test_loc"""
    util.run_success_cmd(loc.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file}")
    assert util.csv_nbr_lines(csv_file) > 0
    assert util.csv_col_int(csv_file, "ncloc", False)
    assert util.csv_col_sorted(csv_file, "project key")


def test_loc_json(json_file: Generator[str]) -> None:
    """test_loc_json"""
    util.run_success_cmd(loc.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {json_file}")
    assert util.json_field_sorted(json_file, "project")
    assert util.json_field_int(json_file, "ncloc", False)


def test_loc_json_fmt(txt_file: Generator[str]) -> None:
    """test_loc_json_fmt"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {txt_file} --{opt.FORMAT} json"
    util.run_success_cmd(loc.main, cmd)
    assert util.json_field_sorted(txt_file, "project")


def test_loc_csv_fmt(txt_file: Generator[str]) -> None:
    """test_loc_csv_fmt"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {txt_file} --{opt.FORMAT} csv"
    util.run_success_cmd(loc.main, cmd)
    # Verify that the file is a valid CSV file
    assert util.csv_col_exist(txt_file, "project key", "ncloc")


def test_loc_project(csv_file: Generator[str]) -> None:
    """test_loc_project"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.KEY_REGEXP_SHORT} {util.LIVE_PROJECT}"
    util.run_success_cmd(loc.main, cmd)
    assert util.csv_nbr_lines(csv_file) == 1
    assert util.csv_col_is_value(csv_file, "project key", util.LIVE_PROJECT)


def test_loc_project_with_all_options(csv_file: Generator[str]) -> None:
    """test_loc_project_with_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.KEY_REGEXP} {util.LIVE_PROJECT} --{opt.WITH_URL} -{opt.WITH_NAME_SHORT} -{opt.WITH_LAST_ANALYSIS_SHORT}"
    util.run_success_cmd(loc.main, cmd)
    assert util.csv_col_url(csv_file, "URL")


def test_loc_portfolios(csv_file: Generator[str]) -> None:
    """test_loc_portfolios"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.PORTFOLIOS} --topLevelOnly --{opt.WITH_URL}"
    if util.SQ.edition() in (c.CE, c.DE):
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return
    util.run_success_cmd(loc.main, cmd)
    assert util.csv_col_sorted(csv_file, "portfolio key")
    assert util.csv_col_int(csv_file, "ncloc", False)


def test_loc_separator(csv_file: Generator[str]) -> None:
    """test_loc_separator"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.CSV_SEPARATOR} +"
    util.run_success_cmd(loc.main, cmd)


def test_loc_branches(csv_file: Generator[str]) -> None:
    """test_loc_branches"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} {ALL_OPTIONS} --{opt.WITH_TAGS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return
    util.run_success_cmd(loc.main, cmd)
    assert util.csv_col_match(csv_file, "branch", r"^[^\s]+$")


def test_loc_branches_json(json_file: Generator[str]) -> None:
    """test_loc"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS} --{opt.WITH_TAGS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return
    util.run_success_cmd(loc.main, cmd)
    assert util.json_field_match(json_file, "branch", r"^[^\s]+$")


def test_loc_proj_all_options(csv_file: Generator[str]) -> None:
    """test_loc_proj_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} {ALL_OPTIONS} --{opt.WITH_TAGS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(loc.main, cmd)
    # Check file contents
    assert util.csv_col_exist(csv_file, "project key", "branch", "project name", "tags")
    assert util.csv_col_datetime(csv_file, "last analysis")
    assert util.csv_col_int(csv_file, "ncloc", False)
    assert util.csv_col_url(csv_file, "URL")
    assert util.csv_col_datetime(csv_file, "last analysis")
    assert util.csv_col_not_all_empty(csv_file, "tags")


def test_loc_apps_all_options(csv_file: Generator[str]) -> None:
    """test_loc_apps_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --apps {ALL_OPTIONS} --{opt.WITH_TAGS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(loc.main, cmd)
    # Check file contents
    assert util.csv_col_exist(csv_file, "app key", "app name", "branch", "tags")
    assert util.csv_col_int(csv_file, "ncloc", False)
    assert util.csv_col_url(csv_file, "URL")
    assert util.csv_col_datetime(csv_file, "last analysis")
    assert util.csv_col_not_all_empty(csv_file, "tags")


def test_loc_portfolios_all_options(csv_file: Generator[str]) -> None:
    """test_loc_portfolios_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --portfolios {ALL_OPTIONS}"
    if util.SQ.edition() in (c.CE, c.DE):
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return
    util.run_success_cmd(loc.main, cmd)
    assert util.csv_col_exist(csv_file, "portfolio key", "portfolio name")
    assert util.csv_col_int(csv_file, "ncloc", False)
    assert util.csv_col_datetime(csv_file, "last analysis")
    assert util.csv_col_url(csv_file, "URL")


def test_loc_proj_all_options_json(json_file: Generator[str]) -> None:
    """test_loc_proj_all_options_json"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS} --{opt.WITH_TAGS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(loc.main, cmd)
    # Check file contents
    assert util.json_fields_exist(json_file, "project", "projectName")
    assert util.json_field_int(json_file, "ncloc", False)
    assert util.json_field_url(json_file, "url")
    assert util.json_field_datetime(json_file, "lastAnalysis")
    assert util.json_field_not_all_empty(json_file, "tags")


def test_loc_apps_all_options_json(json_file: Generator[str]) -> None:
    """test_loc_apps_all_options_json"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS} --apps --{opt.WITH_TAGS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(loc.main, cmd)
    # Check file contents
    assert util.json_fields_exist(json_file, "app", "appName")
    assert util.json_field_int(json_file, "ncloc", False)
    assert util.json_field_url(json_file, "url")
    assert util.json_field_datetime(json_file, "lastAnalysis")
    assert util.json_field_not_all_empty(json_file, "tags")


def test_loc_portfolios_all_options_json(json_file: Generator[str]) -> None:
    """test_loc_portfolios_all_options_json"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS} --portfolios"
    if util.SQ.edition() in (c.CE, c.DE):
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(loc.main, cmd, post_cleanup=False)
    assert util.json_fields_exist(json_file, "portfolio", "portfolioName")
    assert util.json_field_int(json_file, "ncloc", False)
    assert util.json_field_url(json_file, "url")
    assert util.json_field_datetime(json_file, "lastAnalysis")
    # Check file contents
