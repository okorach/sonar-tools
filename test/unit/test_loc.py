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
ALL_OPTIONS = f"-{opt.BRANCH_REGEXP_SHORT} .+ --{opt.WITH_LAST_ANALYSIS} --{opt.WITH_NAME} --{opt.WITH_TAGS} --{opt.WITH_URL}"


def test_loc(csv_file: Generator[str]) -> None:
    """test_loc"""
    util.run_success_cmd(loc.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file}")
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        (key_col, loc_col) = util.get_cols(next(reader := csv.reader(fh)), "project key", "ncloc")
        last_key = ""
        for line in reader:
            assert last_key < line[key_col]
            last_key = line[key_col]
            assert isinstance(int(line[loc_col]), int)


def test_loc_json(json_file: Generator[str]) -> None:
    """test_loc_json"""
    util.run_success_cmd(loc.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {json_file}")
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        data = json.loads(fh.read())
    last_key = ""
    for p in data:
        assert isinstance(int(p["ncloc"]), int)
        assert last_key < p["projectKey"]
        last_key = p["projectKey"]


def test_loc_json_fmt(txt_file: Generator[str]) -> None:
    """test_loc_json_fmt"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {txt_file} --{opt.FORMAT} json"
    util.run_success_cmd(loc.main, cmd, post_cleanup=False)
    # Verify that the file is a valid JSON file
    with open(file=txt_file, mode="r", encoding="utf-8") as fh:
        _ = json.loads(fh.read())


def test_loc_csv_fmt(txt_file: Generator[str]) -> None:
    """test_loc_csv_fmt"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {txt_file} --{opt.FORMAT} csv"
    util.run_success_cmd(loc.main, cmd, post_cleanup=False)
    # Verify that the file is a valid CSV file
    with open(file=txt_file, mode="r", encoding="utf-8") as fh:
        row = next(csv.reader(fh))
        row[0] = row[0][2:]
    for k in "project key", "ncloc":
        assert k in row


def test_loc_project(csv_file: Generator[str]) -> None:
    """test_loc_project"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.KEY_REGEXP_SHORT} {util.LIVE_PROJECT}"
    util.run_success_cmd(loc.main, cmd, post_cleanup=False)
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        next(reader := csv.reader(fh))  # Skip header
        lines = 0
        for line in reader:
            assert line[0] == util.LIVE_PROJECT
            lines += 1
        assert lines == 1


def test_loc_project_with_all_options(csv_file: Generator[str]) -> None:
    """test_loc_project_with_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.KEY_REGEXP} {util.LIVE_PROJECT} --{opt.WITH_URL} -{opt.WITH_NAME_SHORT} -{opt.WITH_LAST_ANALYSIS_SHORT}"
    util.run_success_cmd(loc.main, cmd)


def test_loc_portfolios(csv_file: Generator[str]) -> None:
    """test_loc_portfolios"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.PORTFOLIOS} --topLevelOnly --{opt.WITH_URL}"
    if util.SQ.edition() in (c.CE, c.DE):
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return
    util.run_success_cmd(loc.main, cmd)


def test_loc_separator(csv_file: Generator[str]) -> None:
    """test_loc_separator"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.CSV_SEPARATOR} +"
    util.run_success_cmd(loc.main, cmd)


def test_loc_branches(csv_file: Generator[str]) -> None:
    """test_loc_branches"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} {ALL_OPTIONS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
    else:
        util.run_success_cmd(loc.main, cmd)


def test_loc_branches_json(json_file: Generator[str]) -> None:
    """test_loc"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
    else:
        util.run_success_cmd(loc.main, cmd)


def test_loc_proj_all_options(csv_file: Generator[str]) -> None:
    """test_loc_proj_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} {ALL_OPTIONS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(loc.main, cmd)
    # Check file contents
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        row = next(reader := csv.reader(fh))
        (loc_col, last_ana_col, tags_col, url_col) = util.get_cols(row, "ncloc", "last analysis", "tags", "URL")
        for k in "# project key", "branch", "ncloc", "project name", "last analysis", "tags", "URL":
            assert k in row
        found = False
        for line in reader:
            assert util.is_integer(line[loc_col])
            assert line[last_ana_col] == "" or util.is_datetime(line[last_ana_col])
            found = found or line[tags_col] != ""
            assert util.is_url(line[url_col])
        assert found  # At least one project with tags


def test_loc_apps_all_options(csv_file: Generator[str]) -> None:
    """test_loc_apps_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --apps {ALL_OPTIONS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(loc.main, cmd)
    # Check file contents
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        row = next(reader := csv.reader(fh))
        (loc_col, last_ana_col, tags_col, url_col) = util.get_cols(row, "ncloc", "last analysis", "tags", "URL")
        for k in "# app key", "branch", "ncloc", "app name", "last analysis", "tags", "URL":
            assert k in row
        found = False
        for line in reader:
            assert util.is_integer(line[loc_col])
            assert line[last_ana_col] == "" or util.is_datetime(line[last_ana_col])
            found = found or line[tags_col] != ""
            assert util.is_url(line[url_col])
        assert found  # At least one app with tags


def test_loc_portfolios_all_options(csv_file: Generator[str]) -> None:
    """test_loc_portfolios_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --portfolios {ALL_OPTIONS}"
    if util.SQ.edition() in (c.CE, c.DE):
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return
    util.run_success_cmd(loc.main, cmd)
    # Check file contents
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        row = next(reader := csv.reader(fh))
        (loc_col, last_ana_col, tags_col, url_col) = util.get_cols(row, "ncloc", "last analysis", "tags", "URL")
        for k in "# portfolio key", "ncloc", "portfolio name", "last analysis", "tags", "URL":
            assert k in row
        for line in reader:
            assert util.is_integer(line[loc_col])
            assert line[last_ana_col] == "" or util.is_datetime(line[last_ana_col])
            assert line[tags_col] == ""  # No tags for portfolios
            assert util.is_url(line[url_col])


def test_loc_proj_all_options_json(json_file: Generator[str]) -> None:
    """test_loc_proj_all_options_json"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(loc.main, cmd)
    # Check file contents
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        jsondata = json.loads(fh.read())
    found = False
    for component in jsondata:
        for key in "branch", "lastAnalysis", "ncloc", "project", "projectName", "url":
            assert key in component
        assert component["ncloc"] == "" or util.is_integer(component["ncloc"])
        assert "tags" in component
        found = found or len(component["tags"]) > 0
        assert util.is_url(component["url"])
        assert component["lastAnalysis"] == "" or util.is_datetime(component["lastAnalysis"])
    assert found


def test_loc_apps_all_options_json(json_file: Generator[str]) -> None:
    """test_loc_apps_all_options_json"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS} --apps"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(loc.main, cmd)
    # Check file contents
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        jsondata = json.loads(fh.read())
    found = False
    for component in jsondata:
        for key in "branch", "lastAnalysis", "ncloc", "app", "appName", "url":
            assert key in component
        assert component["ncloc"] == "" or util.is_integer(component["ncloc"])
        assert "tags" in component
        found = found or len(component["tags"]) > 0
        assert util.is_url(component["url"])
        assert component["lastAnalysis"] == "" or util.is_datetime(component["lastAnalysis"])
    assert found


def test_loc_portfolios_all_options_json(json_file: Generator[str]) -> None:
    """test_loc_portfolios_all_options_json"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS} --portfolios"
    if util.SQ.edition() in (c.CE, c.DE):
        util.run_failed_cmd(loc.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(loc.main, cmd, post_cleanup=False)
    # Check file contents
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        jsondata = json.loads(fh.read())
    found = False
    for component in jsondata:
        for key in "lastAnalysis", "ncloc", "portfolio", "portfolioName", "url":
            assert key in component
        assert component["ncloc"] == "" or util.is_integer(component["ncloc"])
        assert util.is_url(component["url"])
        found = found or len(component["tags"]) > 0
        assert component["lastAnalysis"] == "" or util.is_datetime(component["lastAnalysis"])
    assert not found  # No tags for portfolios
