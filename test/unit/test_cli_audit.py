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

"""sonar-audit tests"""

import os
import csv
from collections.abc import Generator

import utilities as tutil
from sonar import errcodes as e
import cli.options as opt
from cli import audit
from sonar import projects
from sonar.audit import rules

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
    with open(".sonar-audit.properties", mode="w", encoding="utf-8") as fd:
        print(AUDIT_DISABLED, file=fd)
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file}") == e.OK
    os.remove(".sonar-audit.properties")
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


def test_audit_cmd_line_settings(csv_file: Generator[str]) -> None:
    """test_audit_cmd_line_settings"""
    what_to_audit = ["logs", "projects", "portfolios", "applications", "qualityProfiles", "qualityGates", "users", "groups"]
    cli_opt = " ".join([f"-Daudit.{what}=true" for what in what_to_audit])
    assert tutil.run_cmd(audit.main, f"{CMD} {cli_opt} --{opt.REPORT_FILE} {csv_file}") == e.OK
    assert tutil.csv_nbr_lines(csv_file) > 0

    cli_opt = " ".join([f"-Daudit.{what}=false" for what in what_to_audit + ["globalSettings"]])
    assert tutil.run_cmd(audit.main, f"{CMD} {cli_opt} --{opt.REPORT_FILE} {csv_file}") == e.OK
    assert tutil.csv_nbr_lines(csv_file) == 0


def test_audit_proj_key_pattern(csv_file: Generator[str]) -> None:
    """test_audit_cmd_line_settings"""
    settings = {"audit.projects": True, "audit.projects.keyPattern": None}
    pbs = projects.audit(tutil.SQ, settings, key_list="BANKING.*")
    assert all(pb.rule_id != rules.RuleId.PROJ_NON_COMPLIANT_KEY_PATTERN for pb in pbs)

    settings = {"audit.projects": True, "audit.projects.keyPattern": ".+"}
    pbs = projects.audit(tutil.SQ, settings, key_list="BANKING.*")
    assert all(pb.rule_id != rules.RuleId.PROJ_NON_COMPLIANT_KEY_PATTERN for pb in pbs)

    settings = {"audit.projects": True, "audit.projects.keyPattern": "BANKING.+"}
    pbs = projects.audit(tutil.SQ, settings, key_list="(BANKING|INSURANCE).+")
    assert any(pb.rule_id == rules.RuleId.PROJ_NON_COMPLIANT_KEY_PATTERN for pb in pbs)

    settings = {"audit.projects": True, "audit.projects.keyPattern": "(BANK|INSU|demo:).+"}
    pbs = projects.audit(tutil.SQ, settings, key_list="(BANKING|INSURANCE|demo:).+")
    assert all(pb.rule_id != rules.RuleId.PROJ_NON_COMPLIANT_KEY_PATTERN for pb in pbs)


def test_filter_severity(csv_file: Generator[str]) -> None:
    """test_filter_severity"""
    assert tutil.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.MIN_SEVERITY} BLOCKER") == e.OK
    with open(csv_file, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        for row in reader:
            severity = row[3]
            assert severity == "BLOCKER"
