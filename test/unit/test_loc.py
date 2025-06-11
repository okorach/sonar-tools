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

import sys
import csv, json
from unittest.mock import patch
import pytest
import utilities as util
from sonar import errcodes
import sonar.util.constants as c

from cli import loc
import cli.options as opt

CMD = "sonar-loc.py"
CSV_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE]
JSON_OPTS = [CMD] + util.STD_OPTS + [f"--{opt.REPORT_FILE}", util.JSON_FILE]

ALL_OPTIONS = [f"-{opt.BRANCH_REGEXP_SHORT}", ".+", f"--{opt.WITH_LAST_ANALYSIS}", f"--{opt.WITH_NAME}", f"--{opt.WITH_URL}"]


def test_loc() -> None:
    """test_loc"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS):
            loc.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_loc_json() -> None:
    """test_loc_json"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS):
            loc.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_loc_json_fmt() -> None:
    """test_loc_json_fmt"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(
            sys, "argv", JSON_OPTS + [f"--{opt.FORMAT}", "json", f"--{opt.WITH_NAME}", f"-{opt.WITH_LAST_ANALYSIS_SHORT}", f"--{opt.WITH_URL}"]
        ):
            loc.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_loc_project() -> None:
    """test_loc_project"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"-{opt.KEYS_SHORT}", "okorach_sonar-tools"]):
            loc.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_loc_project_with_all_options() -> None:
    """test_loc_project_with_all_options"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(
            sys,
            "argv",
            CSV_OPTS + [f"--{opt.KEYS}", "okorach_sonar-tools", f"--{opt.WITH_URL}", f"-{opt.WITH_NAME_SHORT}", f"-{opt.WITH_LAST_ANALYSIS_SHORT}"],
        ):
            loc.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_loc_portfolios() -> None:
    """test_loc_portfolios"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.PORTFOLIOS}", "--topLevelOnly", f"--{opt.WITH_URL}"]):
            loc.main()
    if util.SQ.edition() in (c.CE, c.DE):
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
    else:
        assert int(str(e.value)) == errcodes.OK
        assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_loc_separator() -> None:
    """test_loc_separator"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.CSV_SEPARATOR}", "+"]):
            loc.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_loc_branches() -> None:
    """test_loc"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ALL_OPTIONS):
            loc.main()
    if util.SQ.edition() == c.CE:
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
    else:
        assert int(str(e.value)) == errcodes.OK
    util.clean(util.CSV_FILE)


def test_loc_branches_json() -> None:
    """test_loc"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", [CMD] + util.STD_OPTS + [f"--{opt.REPORT_FILE}", util.JSON_FILE] + ALL_OPTIONS):
            loc.main()
    if util.SQ.edition() == c.CE:
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
    else:
        assert int(str(e.value)) == errcodes.OK
    util.clean(util.JSON_FILE)


def test_loc_proj_all_options() -> None:
    """test_loc"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ALL_OPTIONS):
            loc.main()
    if util.SQ.edition() == c.CE:
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
    else:
        assert int(str(e.value)) == errcodes.OK
        # Check file contents
        with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            row = next(reader)
            for k in "# project key", "ncloc", "project name", "last analysis", "URL":
                assert k in row
            if util.SQ.edition() != c.CE:
                assert "branch" in row
                offset = 0
            else:
                offset = -1
            for line in reader:
                assert util.is_url(line[5 + offset])
                assert line[4 + offset] == "" or util.is_datetime(line[4 + offset])
                assert util.is_integer(line[2])
    util.clean(util.CSV_FILE)


def test_loc_apps_all_options() -> None:
    """test_loc"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--apps"] + ALL_OPTIONS):
            loc.main()
    if util.SQ.edition() == c.CE:
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
    else:
        assert int(str(e.value)) == errcodes.OK
        # Check file contents
        with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            row = next(reader)
            for k in "# app key", "branch", "ncloc", "app name", "last analysis", "URL":
                assert k in row
            for line in reader:
                assert util.is_url(line[5])
                assert line[4] == "" or util.is_datetime(line[4])
                assert util.is_integer(line[2])
    util.clean(util.CSV_FILE)


def test_loc_portfolios_all_options() -> None:
    """test_loc"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--portfolios"] + ALL_OPTIONS):
            loc.main()
    if util.SQ.edition() in (c.CE, c.DE):
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
    else:
        assert int(str(e.value)) == errcodes.OK
        # Check file contents
        with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            row = next(reader)
            for k in "# portfolio key", "ncloc", "portfolio name", "last analysis", "URL":
                assert k in row
            for line in reader:
                assert util.is_url(line[4])
                assert line[3] == "" or util.is_datetime(line[3])
                assert util.is_integer(line[1])
    util.clean(util.CSV_FILE)


def test_loc_proj_all_options_json() -> None:
    """test_loc_proj_all_options_json"""
    file = util.JSON_FILE
    util.clean(file)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ALL_OPTIONS):
            loc.main()
    if util.SQ.edition() == c.CE:
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
    else:
        assert int(str(e.value)) == errcodes.OK
        # Check file contents
        with open(file=file, mode="r", encoding="utf-8") as fh:
            jsondata = json.loads(fh.read())
        for component in jsondata:
            for key in "branch", "lastAnalysis", "ncloc", "project", "projectName", "url":
                assert key in component
            assert component["ncloc"] == "" or util.is_integer(component["ncloc"])
            assert util.is_url(component["url"])
            assert component["lastAnalysis"] == "" or util.is_datetime(component["lastAnalysis"])
    util.clean(file)


def test_loc_apps_all_options_json() -> None:
    """test_loc_apps_all_options_json"""
    file = util.JSON_FILE
    util.clean(file)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ALL_OPTIONS + ["--apps"]):
            loc.main()
    if util.SQ.edition() == c.CE:
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
    else:
        assert int(str(e.value)) == errcodes.OK
        # Check file contents
        with open(file=file, mode="r", encoding="utf-8") as fh:
            jsondata = json.loads(fh.read())
        for component in jsondata:
            for key in "branch", "lastAnalysis", "ncloc", "app", "appName", "url":
                assert key in component
            assert component["ncloc"] == "" or util.is_integer(component["ncloc"])
            assert util.is_url(component["url"])
            assert component["lastAnalysis"] == "" or util.is_datetime(component["lastAnalysis"])
    util.clean(file)


def test_loc_portfolios_all_options_json() -> None:
    """test_loc_portfolios_all_options_json"""
    file = util.JSON_FILE
    util.clean(file)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ALL_OPTIONS + ["--portfolios"]):
            loc.main()
    if util.SQ.edition() in (c.CE, c.DE):
        assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
    else:
        assert int(str(e.value)) == errcodes.OK
        # Check file contents
        with open(file=file, mode="r", encoding="utf-8") as fh:
            jsondata = json.loads(fh.read())
        for component in jsondata:
            for key in "lastAnalysis", "ncloc", "portfolio", "portfolioName", "url":
                assert key in component
            assert component["ncloc"] == "" or util.is_integer(component["ncloc"])
            assert util.is_url(component["url"])
            assert component["lastAnalysis"] == "" or util.is_datetime(component["lastAnalysis"])
    util.clean(file)
