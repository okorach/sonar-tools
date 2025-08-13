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

""" sonar-audit tests """

import os
from collections.abc import Generator

import utilities as util
from sonar import errcodes as e
import cli.options as opt
from cli import audit

CMD = f"sonar-audit.py {util.SQS_OPTS}"

AUDIT_DISABLED = """
audit.globalSettings = no
audit.projects = false
audit.qualityGates = no
audit.qualityProfiles = no
audit.users = no
audit.groups = no
audit.portfolios = no
audit.applications = no
audit.logs = no
audit.plugins = no"""


def test_audit_disabled(csv_file: Generator[str]) -> None:
    """test_audit_disabled"""
    with open(".sonar-audit.properties", mode="w", encoding="utf-8") as fd:
        print(AUDIT_DISABLED, file=fd)
    assert util.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file}") == e.OK
    assert util.file_empty(csv_file)
    os.remove(".sonar-audit.properties")


def test_audit_stdout() -> None:
    """test_audit_stdout"""
    assert util.run_cmd(audit.main, CMD) == e.OK


def test_audit_json(json_file: Generator[str]) -> None:
    """test_audit_json"""
    assert util.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {json_file}") == e.OK


def test_audit_proj_key(csv_file: Generator[str]) -> None:
    """test_audit_proj_key"""
    assert util.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.WHAT} projects --{opt.KEY_REGEXP} {util.LIVE_PROJECT}") == e.OK


def test_audit_proj_non_existing_key() -> None:
    """test_audit_proj_non_existing_key"""
    assert util.run_cmd(audit.main, f"{CMD} --{opt.WHAT} projects --{opt.KEY_REGEXP} {util.LIVE_PROJECT},bad_key") == e.ARGS_ERROR
