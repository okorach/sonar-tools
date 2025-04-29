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

""" sonar-config tests """

import os
import sys
from collections.abc import Generator

import json
from unittest.mock import patch

import utilities as util
from sonar import errcodes, portfolios
from sonar import logging
import cli.options as opt
from cli import config

CMD = "config.py"
LIST_OPTS = [CMD] + util.STD_OPTS + ["-e", f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]
OPTS = " ".join(LIST_OPTS)
OPTS_IMPORT = [CMD] + util.TEST_OPTS + ["-i", f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]


def test_config_export_full() -> None:
    """test_config_export_full"""
    util.run_success_cmd(config.main, f"{OPTS} --fullExport", True)


def test_config_export_partial_2() -> None:
    """test_config_export_partial_2"""
    util.run_success_cmd(config.main, f"{OPTS} -w settings,portfolios,users", True)


def test_config_export_partial_3() -> None:
    """test_config_export_partial_3"""
    util.run_success_cmd(config.main, f"{OPTS} -w projects -{opt.KEYS_SHORT} okorach_sonar-tools", True)


def test_config_export_yaml() -> None:
    """test_config_export_yaml"""
    util.run_success_cmd(config.main, f"{CMD} {util.SQS_OPTS} --{opt.EXPORT} -{opt.REPORT_FILE_SHORT} {util.YAML_FILE}", True)


def test_config_export_wrong() -> None:
    """test_config_export_wrong"""
    util.run_failed_cmd(config.main, f"{OPTS} -w settings,wrong,users", errcodes.ARGS_ERROR)


def test_config_non_existing_project() -> None:
    """test_config_non_existing_project"""
    util.run_failed_cmd(config.main, f"{OPTS} -{opt.KEYS_SHORT} okorach_sonar-tools,bad_project", errcodes.NO_SUCH_KEY)


def test_config_inline_lists() -> None:
    """test_config_inline_commas"""
    util.run_success_cmd(config.main, OPTS)
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
        assert json_config["portfolios"]["All"]["portfolios"]["Banking"]["byReference"]
    util.clean(util.JSON_FILE)


def test_config_dont_inline_lists() -> None:
    """test_config_no_inline_commas"""
    util.run_success_cmd(config.main, f"{OPTS} --dontInlineLists")
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
    if util.SQ.edition() != "community" and util.SQ.version() > (10, 0, 0):
        assert "sonar.cfamily.ignoreHeaderComments" not in json_config["globalSettings"]["languages"]["cfamily"]
        assert "sonar.cfamily.ignoreHeaderComments" in json_config["projects"]["okorach_sonar-tools"]

    util.clean(util.JSON_FILE)


def test_config_import_portfolios(get_json_file: Generator[str]) -> None:
    """test_config_non_existing_project"""
    with open("test/files/config.json", "r", encoding="utf-8") as f:
        json_config = json.loads(f.read())["portfolios"]

    # delete all portfolios in test
    p_list = portfolios.get_list(util.TEST_SQ, use_cache=False)
    logging.info("PORTFOLIOS = %s", str(list(p_list.keys())))
    logging.info("Deleting all portfolios")
    _ = [p.delete() for p in portfolios.get_list(util.TEST_SQ, use_cache=False).values() if p.is_toplevel()]
    # Import config
    util.run_success_cmd(
        config.main, f"{CMD} {util.SQS_TEST_OPTS} --{opt.IMPORT} --{opt.REPORT_FILE} test/files/config.json --{opt.WHAT} {opt.WHAT_PORTFOLIOS}"
    )

    # Compare portfolios
    portfolio_list = portfolios.get_list(util.TEST_SQ)
    assert len(portfolio_list) == len(json_config)
    assert sorted(list(portfolio_list.keys())) == sorted(list(json_config.keys()))
