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


""" sonar-projects tests """

from collections.abc import Generator
from unittest.mock import patch

import utilities as util
from sonar import errcodes
from cli import projects_cli
import cli.options as opt

CMD = "projects_cli.py"
OPTS = f"{CMD} {util.SQS_OPTS} --{opt.NBR_THREADS} 8"


def test_export_all_proj(json_file: Generator[str]) -> None:
    """test_export_all_proj"""
    cmd = f"{OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {json_file} --{opt.NBR_THREADS} 16"
    util.run_success_cmd(projects_cli.main, cmd)


def test_export_single_proj(json_file: Generator[str]) -> None:
    """test_export_single_proj"""
    cmd = f"{OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {json_file} -{opt.KEY_REGEXP_SHORT} {util.LIVE_PROJECT}"
    util.run_success_cmd(projects_cli.main, cmd)


def test_export_timeout(json_file: Generator[str]) -> None:
    """test_export_timeout"""
    cmd = f"{OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {json_file} --{opt.KEY_REGEXP} {util.LIVE_PROJECT} --exportTimeout 10"
    util.run_success_cmd(projects_cli.main, cmd, True)


def test_export_no_file() -> None:
    """test_export_timeout"""
    cmd = f"{OPTS} -{opt.EXPORT_SHORT} -{opt.KEY_REGEXP_SHORT} {util.LIVE_PROJECT}"
    util.run_success_cmd(projects_cli.main, cmd, True)


def test_export_non_existing_project(json_file: Generator[str]) -> None:
    """test_config_non_existing_project"""
    cmd = f"{OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {json_file} -{opt.KEY_REGEXP_SHORT} bad_project"
    util.run_failed_cmd(projects_cli.main, cmd, errcodes.NO_SUCH_KEY)


def test_export_sq_cloud(json_file: Generator[str]) -> None:
    """test_export_sq_cloud"""
    cmd = f"{OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {json_file} {util.SC_OPTS}"
    util.run_failed_cmd(projects_cli.main, cmd, errcodes.UNSUPPORTED_OPERATION)


def test_import_no_file() -> None:
    """test_import_no_file"""
    cmd = f"{OPTS} --{opt.IMPORT}"
    util.run_failed_cmd(projects_cli.main, cmd, errcodes.ARGS_ERROR)


def test_no_export_or_import(json_file: Generator[str]) -> None:
    """test_no_export_or_import"""
    cmd = f"{OPTS} --{opt.REPORT_FILE} {json_file}"
    util.run_failed_cmd(projects_cli.main, cmd, errcodes.ARGS_ERROR)


def test_no_import_file() -> None:
    """test_no_import_file"""
    cmd = f"{OPTS} --{opt.REPORT_FILE} non-existing.json"
    util.run_failed_cmd(projects_cli.main, cmd, errcodes.ARGS_ERROR)
