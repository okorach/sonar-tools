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
from copy import deepcopy
import pytest
from sonar import projects
from sonar import errcodes
from cli import options as opt
import utilities as util
import cli.projects_cli as proj_cli


def test_import(json_file: Generator[str]) -> None:
    """test_import"""
    cmd = f"projects_cli.py {util.SQS_OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {json_file} --{opt.KEY_REGEXP} project1"
    assert util.run_cmd(proj_cli.main, cmd) == errcodes.OK

    if util.SQ.version() == util.TEST_SQ.version():
        assert proj_cli.__import_projects(util.TEST_SQ, file=json_file) is None

        with open(json_file, "r", encoding="utf-8") as fd:
            data = json.load(fd)
        data["projects"][0]["key"] = "TEMP-IMPORT_PROJECT-KEY"
        with open(json_file, "w", encoding="utf-8") as fd:
            print(json.dumps(data), file=fd)
        assert proj_cli.__import_projects(util.TEST_SQ, file=json_file) is None
        proj = projects.Project.get_object(util.TEST_SQ, "TEMP-IMPORT_PROJECT-KEY")
        proj.delete()

    # Mess up the JSON file and retry import
    with open(json_file, "r", encoding="utf-8") as fd:
        data = fd.read()
    data += "]"
    with open(json_file, "w", encoding="utf-8") as fd:
        print(data, file=fd)
    with pytest.raises(opt.ArgumentsError):
        proj_cli.__import_projects(util.TEST_SQ, file=json_file)
