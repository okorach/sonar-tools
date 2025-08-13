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
import pytest
from sonar import projects
from sonar import errcodes
import utilities as tutil
import credentials as creds
from cli import options as opt
from cli import findings_export, projects_cli as proj_cli, measures_export, audit, config, findings_sync, housekeeper, loc, rules_cli

CLIS_DATA = [
    ["findings_export.py", findings_export.main, ""],
    ["measures_export.py", measures_export.main, ""],
    ["config.py", config.main, f"--{opt.EXPORT}"],
    ["audit.py", audit.main, ""],
    ["housekeeper.py", housekeeper.main, ""],
    ["loc.py", loc.main, ""],
    ["rules_cli.py", rules_cli.main, ""],
    ["findings_sync.py", findings_sync.main, f"{tutil.SQS_OPTS} --{opt.KEY_REGEXP} TESTSYNC -U {tutil.SC_URL} -T {tutil.SC_TOKEN} -K TESTSYNC"],
    [
        "findings_sync.py",
        findings_sync.main,
        f"{tutil.SC_OPTS_NO_ORG} --{opt.KEY_REGEXP} {tutil.LIVE_PROJECT} -U {creds.TARGET_PLATFORM} -T {creds.TARGET_TOKEN} -K TESTSYNC",
    ],
]


def test_import(json_file: Generator[str]) -> None:
    """test_import"""
    cmd = f"projects_cli.py {tutil.SQS_OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {json_file} --{opt.KEY_REGEXP} {tutil.PROJECT_1}"
    assert tutil.run_cmd(proj_cli.main, cmd) == errcodes.OK

    if tutil.SQ.version() == tutil.TEST_SQ.version():
        assert proj_cli.__import_projects(tutil.TEST_SQ, file=json_file) is None

        with open(json_file, "r", encoding="utf-8") as fd:
            data = json.load(fd)
        data["projects"][0]["key"] = "TEMP-IMPORT_PROJECT-KEY"
        with open(json_file, "w", encoding="utf-8") as fd:
            print(json.dumps(data), file=fd)
        assert proj_cli.__import_projects(tutil.TEST_SQ, file=json_file) is None
        proj = projects.Project.get_object(tutil.TEST_SQ, "TEMP-IMPORT_PROJECT-KEY")
        proj.delete()

    # Mess up the JSON file and retry import
    with open(json_file, "r", encoding="utf-8") as fd:
        data = fd.read()
    data += "]"
    with open(json_file, "w", encoding="utf-8") as fd:
        print(data, file=fd)
    with pytest.raises(opt.ArgumentsError):
        proj_cli.__import_projects(tutil.TEST_SQ, file=json_file)


def test_bad_org(json_file: Generator[str]):
    """Test that passing a wrong org to any CLI tool fails fast"""
    __NON_EXISTING_ORG = "letsfindsomethngimpossible"
    org_opts = f"--{opt.ORG} {__NON_EXISTING_ORG} --{opt.REPORT_FILE} {json_file}"
    for cli_data in CLIS_DATA:
        pyfile, func, extra_args = cli_data
        cmd = f"{pyfile} {tutil.SC_OPTS_NO_ORG} {org_opts} {extra_args}"
        if pyfile == "findings_sync.py":
            cmd += f" -O {__NON_EXISTING_ORG}"
        assert tutil.run_cmd(func, cmd) == errcodes.NO_SUCH_KEY


def test_bad_arg():
    """Test that passing a wrong argument to any CLI tool fails fast"""
    for cli_data in CLIS_DATA:
        pyfile, func, extra_args = cli_data
        cmd = f"{pyfile} {tutil.SQS_OPTS} {extra_args} -Q something"
        assert tutil.run_cmd(func, cmd) == errcodes.ARGS_ERROR
        cmd = f"{pyfile} {tutil.SC_OPTS} {extra_args} -Q something"
        assert tutil.run_cmd(func, cmd) == errcodes.ARGS_ERROR


def test_bad_project_key(json_file: Generator[str]):
    """Test that passing a wrong argument to any CLI tool fails fast"""
    for cli_data in CLIS_DATA:
        pyfile, func, extra_args = cli_data
        cmd = f"{pyfile} {tutil.SQS_OPTS} {extra_args} --{opt.REPORT_FILE} {json_file} --{opt.KEY_REGEXP} non-existing-project"
        if pyfile in ("audit.py", "housekeeper.py", "rules_cli.py"):
            continue  # Audit does not only audit projects, housekeeper has no project selection
        if pyfile != "findings_sync.py":
            assert tutil.run_cmd(func, cmd) == errcodes.WRONG_SEARCH_CRITERIA
            continue
        cmd = f"{pyfile} {tutil.SC_OPTS} {extra_args} --{opt.KEY_REGEXP} non-existing-project"
        assert tutil.run_cmd(func, cmd) == errcodes.NO_SUCH_KEY
        cmd = f"{pyfile} {tutil.SC_OPTS} {extra_args} -K non-existing-project"
        assert tutil.run_cmd(func, cmd) == errcodes.NO_SUCH_KEY
