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

import json, yaml

import utilities as tutil
from sonar import errcodes as e
from sonar import portfolios
from sonar import logging
import sonar.util.constants as c

import cli.options as opt
from cli import config

CMD = "config.py"
OPTS = f"{CMD} {tutil.SQS_OPTS} -{opt.EXPORT_SHORT}"

_DEFAULT_TEMPLATE = "0. Default template"

def __is_ordered_as_expected(data: list[str], expected_order: list[str]) -> bool:
    for k in config._SECTIONS_ORDER:
        if len(data) == 0:
            break
        if k == data[0]:
            data.pop(0)
    return len(data) == 0

def test_config_export_full(json_file: Generator[str]) -> None:
    """test_config_export_full"""
    assert tutil.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file} --fullExport") == e.OK


def test_config_export_partial_2(json_file: Generator[str]) -> None:
    """test_config_export_partial_2"""
    assert tutil.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file} -w settings,portfolios,users") == e.OK


def test_config_export_partial_3(json_file: Generator[str]) -> None:
    """test_config_export_partial_3"""
    assert tutil.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file} -w projects -{opt.KEY_REGEXP_SHORT} {tutil.LIVE_PROJECT}") == e.OK


def test_config_export_yaml(yaml_file: Generator[str]) -> None:
    """test_config_export_yaml"""
    assert tutil.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {yaml_file}") == e.OK
    with open(file=yaml_file, mode="r", encoding="utf-8") as fh:
        json_config = yaml.safe_load(fh.read())
    # Verify YAML export is in the expected key order
    assert __is_ordered_as_expected(list(json_config.keys()), config._SECTIONS_ORDER)
    for section in config._SECTIONS_TO_SORT:
        assert sorted(json_config.get(section, [])) == list(json_config.get(section, []))


def test_config_export_wrong() -> None:
    """test_config_export_wrong"""
    assert tutil.run_cmd(config.main, f"{OPTS} -w settings,wrong,users") == e.ARGS_ERROR


def test_config_non_existing_project() -> None:
    """test_config_non_existing_project"""
    assert tutil.run_cmd(config.main, f"{OPTS} -{opt.KEY_REGEXP_SHORT} bad_project") == e.WRONG_SEARCH_CRITERIA


def test_config_inline_lists(json_file: Generator[str]) -> None:
    """test_config_inline_lists"""

    assert tutil.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file}") == e.OK
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())
    assert isinstance(json_config["globalSettings"]["languages"]["javascript"]["sonar.javascript.file.suffixes"], str)
    assert isinstance(
        json_config["globalSettings"]["permissionTemplates"][_DEFAULT_TEMPLATE]["permissions"]["groups"][tutil.SQ.default_user_group()], str
    )
    assert isinstance(json_config["projects"][tutil.LIVE_PROJECT]["permissions"]["groups"][tutil.SQ.default_user_group()], str)

    if tutil.SQ.edition() not in (c.CE, c.DE):
        assert isinstance(json_config["portfolios"]["PORTFOLIO_ALL"]["permissions"]["groups"]["sonar-administrators"], str)
        assert isinstance(json_config["portfolios"]["PORTFOLIO-PYTHON"]["projects"]["tags"], str)
        # This is a list because there is a comma in one of the branches
        if tutil.SQ.version() >= (10, 0, 0):
            assert isinstance(json_config["portfolios"]["PORTFOLIO_MULTI_BRANCHES"]["projects"]["manual"]["BANKING-PORTAL"], list)
        assert json_config["portfolios"]["All"]["portfolios"]["Banking"]["byReference"]

    # Verify JSON export is in the expected key order
    assert __is_ordered_as_expected(list(json_config.keys()), config._SECTIONS_ORDER)
    for section in config._SECTIONS_TO_SORT:
        assert sorted(json_config.get(section, [])) == list(json_config.get(section, []))

def test_config_dont_inline_lists(json_file: Generator[str]) -> None:
    """test_config_dont_inline_lists"""
    assert tutil.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file} --{opt.WHAT} settings,projects,portfolios --dontInlineLists") == e.OK
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())
    assert isinstance(json_config["globalSettings"]["languages"]["javascript"]["sonar.javascript.file.suffixes"], list)
    assert isinstance(
        json_config["globalSettings"]["permissionTemplates"][_DEFAULT_TEMPLATE]["permissions"]["groups"][tutil.SQ.default_user_group()], list
    )
    assert isinstance(json_config["projects"][tutil.LIVE_PROJECT]["permissions"]["groups"][tutil.SQ.default_user_group()], list)
    if tutil.SQ.edition() not in (c.CE, c.DE):
        assert isinstance(json_config["portfolios"]["PORTFOLIO_ALL"]["permissions"]["groups"]["sonar-administrators"], list)
        assert isinstance(json_config["portfolios"]["PORTFOLIO-PYTHON"]["projects"]["tags"], list)
        if tutil.SQ.version() >= (10, 0, 0):
            assert isinstance(json_config["portfolios"]["PORTFOLIO_MULTI_BRANCHES"]["projects"]["manual"]["BANKING-PORTAL"], list)
    if tutil.SQ.edition() != c.CE and tutil.SQ.version() > (10, 0, 0):
        assert "sonar.cfamily.ignoreHeaderComments" not in json_config["globalSettings"]["languages"]["cfamily"]
        assert "sonar.cfamily.ignoreHeaderComments" in json_config["projects"][tutil.LIVE_PROJECT]


def test_config_import_portfolios() -> None:
    """test_config_import_portfolios"""
    with open(f"{tutil.FILES_ROOT}/config.json", "r", encoding="utf-8") as f:
        json_config = json.loads(f.read())["portfolios"]

    # delete all portfolios in test
    p_list = portfolios.get_list(tutil.TEST_SQ, use_cache=False)
    logging.info("PORTFOLIOS = %s", str(list(p_list.keys())))
    logging.info("Deleting all portfolios")
    _ = [p.delete() for p in portfolios.get_list(tutil.TEST_SQ, use_cache=False).values() if p.is_toplevel()]
    # Import config
    cmd = f"{CMD} {tutil.SQS_TEST_OPTS} --{opt.IMPORT} --{opt.REPORT_FILE} ${tutil.FILES_ROOT}/config.json --{opt.WHAT} {opt.WHAT_PORTFOLIOS}"
    assert tutil.run_cmd(config.main, cmd) == e.OK

    # Compare portfolios
    portfolio_list = portfolios.get_list(tutil.TEST_SQ)
    assert len(portfolio_list) == len(json_config)
    assert sorted(portfolio_list.keys()) == sorted(json_config.keys())
