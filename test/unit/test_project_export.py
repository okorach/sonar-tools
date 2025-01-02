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


""" sonar-projects tests """

import os
import sys
from collections.abc import Generator

import utilities as util
from sonar import errcodes
from cli import projects_cli
import cli.options as opt

CMD = "projects_cli.py"
OPTS = f"{CMD} {util.SQS_OPTS}"


def test_export_all_proj(get_json_file: Generator[str]) -> None:
    """test_export_all_proj"""
    args = f"{OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {get_json_file} --{opt.NBR_THREADS} 16"
    util.run_success_cmd(projects_cli.main, args)


def test_export_single_proj(get_json_file: Generator[str]) -> None:
    """test_export_single_proj"""
    args = f"{OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {get_json_file} -{opt.KEYS_SHORT} okorach_sonar-tools"
    util.run_success_cmd(projects_cli.main, args)


def test_export_timeout(get_json_file: Generator[str]) -> None:
    """test_export_timeout"""
    cmd = f"{OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {get_json_file} --{opt.KEYS} okorach_sonar-tools --exportTimeout 10"
    util.run_success_cmd(projects_cli.main, cmd)


def test_export_no_file(get_json_file: Generator[str]) -> None:
    """test_export_timeout"""
    cmd = f"{OPTS} --{opt.EXPORT} -{opt.KEYS_SHORT} okorach_sonar-tools"
    util.run_success_cmd(projects_cli.main, cmd)


def test_export_non_existing_project(get_json_file: Generator[str]) -> None:
    """test_config_non_existing_project"""
    cmd = f"{OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {get_json_file} --{opt.KEYS_SHORT} okorach_sonar-tools,bad_project"
    util.run_failed_cmd(projects_cli.main, cmd, errcodes.NO_SUCH_KEY)


def test_export_sq_cloud(get_json_file: Generator[str]) -> None:
    """test_export_sq_cloud"""
    cmd = f"{OPTS} --{opt.EXPORT} --{opt.REPORT_FILE} {get_json_file} {util.SC_OPTS}"
    util.run_failed_cmd(projects_cli.main, cmd, errcodes.UNSUPPORTED_OPERATION)


def test_import_no_file() -> None:
    """test_import_no_file"""
    util.run_failed_cmd(projects_cli.main, f"{OPTS} --{opt.IMPORT}", errcodes.ARGS_ERROR)
