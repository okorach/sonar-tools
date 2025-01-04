#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2025 Olivier Korach
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

""" projects_cli tests """

from collections.abc import Generator
import json
import logging
import pytest
from sonar import exceptions, projects, utilities as sutil
from cli import options as opt
import utilities as util
import cli.projects_cli as proj_cli

CMD = "projects_cli.py"
OPTS = f"{CMD} {util.SQS_OPTS}"


def test_import_compatibility() -> None:
    util.start_logging()
    jsondata = util.SQ.basics()
    logging.debug("JSON = %s", sutil.json_dump(jsondata))
    assert proj_cli.__check_sq_environments(util.SQ, jsondata) is None

    incompatible_data = jsondata.copy()
    incompatible_data["version"] = "8.7.0"
    with pytest.raises(exceptions.UnsupportedOperation):
        proj_cli.__check_sq_environments(util.SQ, incompatible_data)

    incompatible_data = jsondata.copy()
    incompatible_data["plugins"] = {}
    with pytest.raises(exceptions.UnsupportedOperation):
        proj_cli.__check_sq_environments(util.SQ, incompatible_data)

    incompatible_data["plugins"] = jsondata["plugins"].copy()
    incompatible_data["plugins"]["lua"] = "1.0 [Lua Analyzer]"
    with pytest.raises(exceptions.UnsupportedOperation):
        proj_cli.__check_sq_environments(util.SQ, incompatible_data)

    incompatible_data["plugins"] = jsondata["plugins"].copy()
    for p, v in incompatible_data["plugins"].items():
        incompatible_data["plugins"][p] = "1." + v
    with pytest.raises(exceptions.UnsupportedOperation):
        proj_cli.__check_sq_environments(util.SQ, incompatible_data)


def test_import(get_json_file: Generator[str]) -> None:
    """test_import"""
    export_file = get_json_file
    cmd = f"{OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {export_file} --{opt.KEYS} project1"
    util.run_success_cmd(proj_cli.main, cmd)

    proj_cli.__import_projects(util.TEST_SQ, file=export_file)

    with open(export_file, "r", encoding="utf-8") as fd:
        data = json.load(fd)
    data["project_exports"][0]["key"] = "TEMP-IMPORT_PROJECT-KEY"
    with open(export_file, "w", encoding="utf-8") as fd:
        print(json.dumps(data), file=fd)
    assert proj_cli.__import_projects(util.TEST_SQ, file=export_file) is None
    proj = projects.Project.get_object(util.TEST_SQ, "TEMP-IMPORT_PROJECT-KEY")
    proj.delete()

    # Mess up the JSON file and retry import
    with open(export_file, "r", encoding="utf-8") as fd:
        data = fd.read()
    data += "]"
    with open(export_file, "w", encoding="utf-8") as fd:
        print(data, file=fd)
    with pytest.raises(opt.ArgumentsError):
        proj_cli.__import_projects(util.TEST_SQ, file=export_file)
