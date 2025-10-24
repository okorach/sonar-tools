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

"""sonar-config tests"""

from collections.abc import Generator

import json, yaml

import utilities as tutil
from sonar import errcodes as e
from sonar import portfolios, applications, projects
from sonar import logging
import sonar.util.constants as c
from sonar import utilities as util

import cli.options as opt
from cli import config

CMD = "config.py"
OPTS = f"{CMD} {tutil.SQS_OPTS} -{opt.EXPORT_SHORT}"

_DEFAULT_TEMPLATE = "0. Default template"


def __is_ordered_as_expected(data: list[str], expected_order: list[str]) -> bool:
    for k in expected_order:
        if len(data) == 0:
            break
        if k == data[0]:
            data.pop(0)
    return len(data) == 0


def __sections_present(data: list[str], present_sections: list[str], all_sections: list[str]) -> bool:
    what = ["platform"] + ["globalSettings" if w == "settings" else w for w in present_sections]
    whatnot = [w for w in all_sections if w not in what]
    print(json.dumps(data, indent=3))
    return all(s in data for s in what) and all(s not in data for s in whatnot)


def test_config_export_full(json_file: Generator[str]) -> None:
    """test_config_export_full"""
    assert tutil.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file} --fullExport") == e.OK


def test_config_export_partial_2(json_file: Generator[str]) -> None:
    """test_config_export_partial_2"""
    what = ["settings", "portfolios", "users"]
    assert tutil.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file} --{opt.WHAT} {','.join(what)}") == e.OK
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())
    assert __sections_present(json_config, what, config._SECTIONS_ORDER)


def test_config_export_partial_3(json_file: Generator[str]) -> None:
    """test_config_export_partial_3"""
    what = ["projects"]
    assert (
        tutil.run_cmd(
            config.main, f"{OPTS} --{opt.REPORT_FILE} {json_file} --{opt.WHAT} {','.join(what)} -{opt.KEY_REGEXP_SHORT} {tutil.LIVE_PROJECT}"
        )
        == e.OK
    )
    with open(file=json_file, mode="r", encoding="utf-8") as fh:
        json_config = json.loads(fh.read())
    assert __sections_present(json_config, what, config._SECTIONS_ORDER)


def test_config_export_yaml(yaml_file: Generator[str]) -> None:
    """test_config_export_yaml"""
    assert tutil.run_cmd(config.main, f"{OPTS} --{opt.REPORT_FILE} {yaml_file}") == e.OK
    with open(file=yaml_file, mode="r", encoding="utf-8") as fh:
        json_config = yaml.safe_load(fh.read())
    # Verify YAML export is in the expected key order
    assert __is_ordered_as_expected(list(json_config.keys()), config._SECTIONS_ORDER)
    __MAP = {
        "projects": "key",
        "applications": "key",
        "portfolios": "key",
        "users": "login",
        "groups": "name",
        "qualityGates": "name",
        "qualityProfiles": "language",
    }
    for section in config._SECTIONS_TO_SORT:
        elems = json_config.get(section, {})
        if isinstance(elems, dict):
            assert sorted(elems.keys()) == list(elems.keys())
        elif isinstance(elems, list):
            elems = [elem[__MAP[section]] for elem in elems]
            assert sorted(elems) == list(elems)


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
        assert sorted(json_config.get(section, {}).keys()) == list(json_config.get(section, {}).keys())


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
    config_file = f"{tutil.FILES_ROOT}/config.json"
    with open(config_file, "r", encoding="utf-8") as f:
        json_config = json.loads(f.read())["portfolios"]

    # delete all portfolios in test
    p_list = portfolios.get_list(tutil.TEST_SQ, use_cache=False)
    logging.info("PORTFOLIOS = %s", str(list(p_list.keys())))
    logging.info("Deleting all portfolios")
    for p in portfolios.get_list(tutil.TEST_SQ, use_cache=False).values():
        if p.is_toplevel():
            p.delete()
    # Import config
    cmd = f"{CMD} {tutil.SQS_TEST_OPTS} --{opt.IMPORT} --{opt.REPORT_FILE} {config_file} --{opt.WHAT} {opt.WHAT_PORTFOLIOS}"
    assert tutil.run_cmd(config.main, cmd) == e.OK

    # Compare portfolios
    portfolio_list = portfolios.get_list(tutil.TEST_SQ)
    assert len(portfolio_list) == len(json_config)
    assert sorted(portfolio_list.keys()) == sorted(json_config.keys())


def test_config_import_apps() -> None:
    """test_config_import_apps"""
    config_file = f"{tutil.FILES_ROOT}/config.json"
    with open(config_file, "r", encoding="utf-8") as f:
        json_config = json.loads(f.read())["applications"]

    # delete all apps in test
    for p in applications.get_list(tutil.TEST_SQ, use_cache=False).values():
        p.delete()
    # Import config
    cmd = f"{CMD} {tutil.SQS_TEST_OPTS} --{opt.IMPORT} --{opt.REPORT_FILE} {config_file} --{opt.WHAT} {opt.WHAT_APPS}"
    assert tutil.run_cmd(config.main, cmd) == e.OK

    # Compare apps
    app_list = applications.get_list(tutil.TEST_SQ)
    assert len(app_list) == len(json_config)
    assert sorted(app_list.keys()) == sorted(json_config.keys())


def test_config_import_projects() -> None:
    """TEsts that the import of projects config works"""
    config_file = f"{tutil.FILES_ROOT}/config.json"
    json_config = tutil.read_json(config_file)["projects"]

    # delete all projects in test except the testsync one
    for p in projects.get_list(tutil.TEST_SQ).values():
        if p.key != "TESTSYNC":
            p.delete()
    # Import config
    cmd = f"{CMD} {tutil.SQS_TEST_OPTS} --{opt.IMPORT} --{opt.REPORT_FILE} {config_file} --{opt.WHAT} {opt.WHAT_PROJECTS}"
    assert tutil.run_cmd(config.main, cmd) == e.OK

    # Compare projects
    project_list = projects.get_list(tutil.TEST_SQ)
    assert len(project_list) == len(json_config)
    assert sorted(project_list.keys()) == sorted(json_config.keys())
