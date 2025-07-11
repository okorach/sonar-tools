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

from collections.abc import Generator

import json
from unittest.mock import patch

import utilities as util
from sonar import errcodes as e
from sonar import portfolios
from sonar import logging
import sonar.util.constants as c

import cli.options as opt
from cli import config

CMD = "config.py"
OPTS = f"{CMD} {util.SQS_OPTS} -{opt.EXPORT_SHORT}"


def test_config_export_full(json_file: Generator[str]) -> None:
    """test_config_export_full"""
    assert util.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file} --fullExport") == e.OK


def test_config_export_partial_2(json_file: Generator[str]) -> None:
    """test_config_export_partial_2"""
    assert util.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file} -w settings,portfolios,users") == e.OK


def test_config_export_partial_3(json_file: Generator[str]) -> None:
    """test_config_export_partial_3"""
    assert util.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file} -w projects -{opt.KEY_REGEXP_SHORT} {util.LIVE_PROJECT}") == e.OK


def test_config_export_yaml(yaml_file: Generator[str]) -> None:
    """test_config_export_yaml"""
    assert util.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {yaml_file}") == e.OK


def test_config_export_wrong() -> None:
    """test_config_export_wrong"""
    assert util.run_cmd(config.main, f"{OPTS} -w settings,wrong,users") == e.ARGS_ERROR


def test_config_non_existing_project() -> None:
    """test_config_non_existing_project"""
    assert util.run_cmd(config.main, f"{OPTS} -{opt.KEY_REGEXP_SHORT} bad_project") == e.NO_SUCH_KEY


def test_config_inline_lists(json_file: Generator[str]) -> None:
    """test_config_inline_lists"""
    assert util.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file}") == e.OK
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())
    assert isinstance(json_config["globalSettings"]["languages"]["javascript"]["sonar.javascript.file.suffixes"], str)
    assert isinstance(json_config["globalSettings"]["permissionTemplates"]["Default template"]["permissions"]["groups"]["sonar-users"], str)
    assert isinstance(json_config["projects"]["okorach_sonar-tools"]["permissions"]["groups"]["sonar-users"], str)

    if util.SQ.edition() not in (c.CE, c.DE):
        assert isinstance(json_config["portfolios"]["PORTFOLIO_ALL"]["permissions"]["groups"]["sonar-administrators"], str)
        assert isinstance(json_config["portfolios"]["PORTFOLIO_TAGS"]["projects"]["tags"], str)
        # This is a list because there is a comma in one of the branches
        if util.SQ.version() >= (10, 0, 0):
            assert isinstance(json_config["portfolios"]["PORTFOLIO_MULTI_BRANCHES"]["projects"]["manual"]["BANKING-PORTAL"], list)
        assert json_config["portfolios"]["All"]["portfolios"]["Banking"]["byReference"]


def test_config_dont_inline_lists(json_file: Generator[str]) -> None:
    """test_config_dont_inline_lists"""
    assert util.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file} --dontInlineLists") == e.OK
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())
    assert isinstance(json_config["globalSettings"]["languages"]["javascript"]["sonar.javascript.file.suffixes"], list)
    assert isinstance(json_config["globalSettings"]["permissionTemplates"]["Default template"]["permissions"]["groups"]["sonar-users"], list)
    assert isinstance(json_config["projects"]["okorach_sonar-tools"]["permissions"]["groups"]["sonar-users"], list)
    if util.SQ.edition() not in (c.CE, c.DE):
        assert isinstance(json_config["portfolios"]["PORTFOLIO_ALL"]["permissions"]["groups"]["sonar-administrators"], list)
        assert isinstance(json_config["portfolios"]["PORTFOLIO_TAGS"]["projects"]["tags"], list)
        if util.SQ.version() >= (10, 0, 0):
            assert isinstance(json_config["portfolios"]["PORTFOLIO_MULTI_BRANCHES"]["projects"]["manual"]["BANKING-PORTAL"], list)
    if util.SQ.edition() != c.CE and util.SQ.version() > (10, 0, 0):
        assert "sonar.cfamily.ignoreHeaderComments" not in json_config["globalSettings"]["languages"]["cfamily"]
        assert "sonar.cfamily.ignoreHeaderComments" in json_config["projects"]["okorach_sonar-tools"]


def test_config_import_portfolios() -> None:
    """test_config_import_portfolios"""
    with open("test/files/config.json", "r", encoding="utf-8") as f:
        json_config = json.loads(f.read())["portfolios"]

    # delete all portfolios in test
    p_list = portfolios.get_list(util.TEST_SQ, use_cache=False)
    logging.info("PORTFOLIOS = %s", str(list(p_list.keys())))
    logging.info("Deleting all portfolios")
    _ = [p.delete() for p in portfolios.get_list(util.TEST_SQ, use_cache=False).values() if p.is_toplevel()]
    # Import config
    cmd = f"{CMD} {util.SQS_TEST_OPTS} --{opt.IMPORT} --{opt.REPORT_FILE} test/files/config.json --{opt.WHAT} {opt.WHAT_PORTFOLIOS}"
    assert util.run_cmd(config.main, cmd) == e.OK

    # Compare portfolios
    portfolio_list = portfolios.get_list(util.TEST_SQ)
    assert len(portfolio_list) == len(json_config)
    assert sorted(list(portfolio_list.keys())) == sorted(list(json_config.keys()))
