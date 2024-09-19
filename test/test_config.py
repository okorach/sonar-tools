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

""" sonar-config tests """

import os
import sys
import json
from unittest.mock import patch
import pytest

import utilities as util
from sonar import errcodes, portfolios
from sonar import logging
import cli.options as opt
from cli import config

CMD = "config.py"
OPTS = [CMD] + util.STD_OPTS + ["-e", f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]
OPTS_IMPORT = [CMD] + util.TEST_OPTS + ["-i", f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]


def __test_config_cmd(arguments: list[str]) -> None:
    """Runs a test command"""
    outputfile = arguments[arguments.index(f"-{opt.REPORT_FILE_SHORT}") + 1]
    util.clean(outputfile)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", arguments):
            config.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(outputfile)
    util.clean(outputfile)


def test_config_export() -> None:
    """test_config_export"""
    __test_config_cmd(OPTS)


def test_config_export_full() -> None:
    """test_config_export_full"""
    __test_config_cmd(OPTS + ["--fullExport"])


def test_config_export_partial_1() -> None:
    """test_config_export_partial_1"""
    __test_config_cmd(OPTS + ["-w", "projects"])


def test_config_export_partial_2() -> None:
    """test_config_export_partial_2"""
    __test_config_cmd(OPTS + ["-w", "settings,portfolios,users"])


def test_config_export_partial_3() -> None:
    """test_config_export_partial_3"""
    __test_config_cmd(OPTS + ["-w", "projects", f"-{opt.KEYS_SHORT}", "okorach_sonar-tools"])


def test_config_export_yaml() -> None:
    """test_config_export_partial_3"""
    __test_config_cmd([CMD] + util.STD_OPTS + ["-e", f"-{opt.REPORT_FILE_SHORT}", util.YAML_FILE])


def test_config_export_wrong() -> None:
    """test_config_export_wrong"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS + ["-w", "settings,wrong,users"]):
            config.main()
    assert int(str(e.value)) == errcodes.ARGS_ERROR
    assert not os.path.isfile(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_config_non_existing_project() -> None:
    """test_config_non_existing_project"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS + [f"-{opt.KEYS_SHORT}", "okorach_sonar-tools,bad_project"]):
            config.main()
    assert int(str(e.value)) == errcodes.NO_SUCH_KEY
    assert not os.path.isfile(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_config_inline_commas() -> None:
    """test_config_inline_commas"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", OPTS):
            config.main()
    with open(file=util.JSON_FILE, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())
    assert isinstance(json_config["globalSettings"]["languages"]["javascript"]["sonar.javascript.file.suffixes"], str)
    assert isinstance(json_config["globalSettings"]["permissionTemplates"]["Default template"]["permissions"]["groups"]["sonar-users"], str)
    assert isinstance(json_config["projects"]["okorach_sonar-tools"]["permissions"]["groups"]["sonar-users"], str)

    if util.SQ.edition() not in ("community", "developer"):
        assert isinstance(json_config["portfolios"]["PORTFOLIO_ALL"]["permissions"]["groups"]["sonar-administrators"], str)
        assert isinstance(json_config["portfolios"]["PORTFOLIO_TAGS"]["projects"]["tags"], str)
        # This is a list because there is a comma in one of the branches
        if util.SQ.version() >= (10, 0, 0):
            assert isinstance(json_config["portfolios"]["PORTFOLIO_MULTI_BRANCHES"]["projects"]["manual"]["BANKING-PORTAL"], list)
    util.clean(util.JSON_FILE)


def test_config_no_inline_commas() -> None:
    """test_config_no_inline_commas"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", OPTS + ["--dontInlineLists"]):
            config.main()
    with open(file=util.JSON_FILE, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())
    assert isinstance(json_config["globalSettings"]["languages"]["javascript"]["sonar.javascript.file.suffixes"], list)
    assert isinstance(json_config["globalSettings"]["permissionTemplates"]["Default template"]["permissions"]["groups"]["sonar-users"], list)
    assert isinstance(json_config["projects"]["okorach_sonar-tools"]["permissions"]["groups"]["sonar-users"], list)
    if util.SQ.edition() not in ("community", "developer"):
        assert isinstance(json_config["portfolios"]["PORTFOLIO_ALL"]["permissions"]["groups"]["sonar-administrators"], list)
        assert isinstance(json_config["portfolios"]["PORTFOLIO_TAGS"]["projects"]["tags"], list)
        if util.SQ.version() >= (10, 0, 0):
            assert isinstance(json_config["portfolios"]["PORTFOLIO_MULTI_BRANCHES"]["projects"]["manual"]["BANKING-PORTAL"], list)
    util.clean(util.JSON_FILE)


def test_config_import_portfolios() -> None:
    """test_config_non_existing_project"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", [CMD] + util.STD_OPTS + ["-e", f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE, f"--{opt.WHAT}", "portfolios"]):
            config.main()
    with open(file=util.JSON_FILE, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())

    # delete all portfolios in test
    logging.set_debug_level("DEBUG")
    logging.info("Deleting all portfolios")
    portfolios.Portfolio.empty_cache()
    for p in portfolios.get_list(util.TEST_SQ).values():
        if p.is_toplevel():
            p.delete()
    # Import config
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", [CMD] + util.TEST_OPTS + ["-i", f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE, "-l", "test.log"]):
            config.main()

    # Compare portfolios
    portfolio_list = portfolios.get_list(util.TEST_SQ)
    assert len(portfolio_list) == len(json_config["portfolios"])
    assert sorted(list(portfolio_list.keys())) == sorted(list(json_config["portfolios"].keys()))
