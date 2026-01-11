#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2024-2026 Olivier Korach
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

"""sonar-audit CLI tests"""

import os
from collections.abc import Generator

import utilities as tutil
from sonar import errcodes as e
import cli.options as opt
from sonar.cli import audit

CMD = f"sonar-audit.py {tutil.SQS_OPTS}"

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
    """Tests that nothing is output when all audits are disabled"""
    with open(f".{audit.CONFIG_FILE}", mode="w", encoding="utf-8") as fd:
        print(AUDIT_DISABLED, file=fd)
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file}") == e.OK
    os.remove(f".{audit.CONFIG_FILE}")
    assert tutil.csv_nbr_lines(csv_file) == 0


def test_audit_stdout() -> None:
    """Tests audit to stdout"""
    assert tutil.run_cmd(audit.main, CMD) == e.OK


def test_audit_json(json_file: Generator[str]) -> None:
    """Test audit to json file"""
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {json_file}") == e.OK


def test_audit_proj_key(csv_file: Generator[str]) -> None:
    """Tests that audit can select only specific project keys"""
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.WHAT} projects --{opt.KEY_REGEXP} {tutil.LIVE_PROJECT}") == e.OK


def test_audit_proj_non_existing_key() -> None:
    """Tests that error is raised when the project key regexp does not select any project"""
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.WHAT} projects --{opt.KEY_REGEXP} {tutil.LIVE_PROJECT},bad_key") == e.ARGS_ERROR


def run_cli_settings(file: str, toggle: bool) -> int:
    """Helper to run audit with all audits toggled on or off"""
    what_to_audit = ["globalSettings", "logs", "projects", "portfolios", "applications", "qualityProfiles", "qualityGates", "users", "groups"]
    cli_opt = " ".join([f"-Daudit.{what}={str(toggle).lower()}" for what in what_to_audit])
    return tutil.run_cmd(audit.main, f"{CMD} {cli_opt} --{opt.REPORT_FILE} {file}")


def test_audit_cmd_line_settings_on(csv_file: Generator[str]) -> None:
    """Verifies that passing audit settings from command line with -D<key>=<value> works, turning on everything"""
    assert run_cli_settings(csv_file, True) == e.OK
    assert tutil.csv_nbr_lines(csv_file) > 0


def test_audit_cmd_line_settings_off(csv_file: Generator[str]) -> None:
    """Verifies that passing audit settings from command line with -D<key>=<value> works, turning off everything"""
    assert run_cli_settings(csv_file, False) == e.OK
    assert tutil.csv_nbr_lines(csv_file) == 0


def test_filter_severity(csv_file: Generator[str]) -> None:
    """Verify that filtering by severities works"""
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.SEVERITIES} MEDIUM,HIGH") == e.OK
    assert tutil.csv_nbr_lines(csv_file) > 0
    assert tutil.csv_col_is_value(csv_file, "Severity", "MEDIUM", "HIGH")


def test_filter_type(json_file: Generator[str]) -> None:
    """Verify that filtering by severities works"""
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {json_file} --{opt.TYPES} HOUSEKEEPING,SECURITY") == e.OK
    assert tutil.json_field_in_values(json_file, "type", "HOUSEKEEPING", "SECURITY")


def test_filter_problem(csv_file: Generator[str]) -> None:
    """Verify that filtering by problem id works"""
    regexp = "(OBJECT.+|QG.+)"
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file} --problems {regexp}") == e.OK
    assert tutil.csv_col_match(csv_file, "Problem", regexp)


def test_filter_multiple(csv_file: Generator[str]) -> None:
    """Verify that filtering by problem id works"""
    regexp = "(OBJECT.+|QG.+)"
    assert (
        tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.TYPES} HOUSEKEEPING --{opt.SEVERITIES} MEDIUM --problems {regexp}")
        == e.OK
    )
    assert tutil.csv_col_is_value(csv_file, "Severity", "MEDIUM")
    assert tutil.csv_col_is_value(csv_file, "Type", "HOUSEKEEPING")
    assert tutil.csv_col_match(csv_file, "Problem", regexp)
