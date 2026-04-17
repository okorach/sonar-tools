#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2026 Olivier Korach
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

"""Common tests, independent of SonarQube version"""

import os
import csv
import re
from collections.abc import Generator
import pytest

import utilities as tutil
from sonar import errcodes as e
import cli.options as opt
from sonar.cli import audit, maturity

CMD_ONLY = "sonar-audit.py"
CMD = f"{CMD_ONLY} {tutil.SQS_OPTS}"


def problems_present(csv_file: str, problems: list[tuple[str, str]]) -> bool:
    """Check if the problems are present in the audit output"""
    unfound_problems = problems.copy()
    with open(csv_file, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        for row in reader:
            for pb in problems:
                string = row[4]
                if row[1] == pb[0] and re.match(pb[1], string):
                    unfound_problems.remove(pb)
                    break
            if len(unfound_problems) == 0:
                break
    return len(unfound_problems) == 0


def test_audit(csv_file: Generator[str]) -> None:
    """test_audit"""
    transient_errors = ("ERROR_IN_LOGS", "WARNING_IN_LOGS", "DEPRECATION_WARNINGS", "LATEST_PATCH_MISSING")
    csv_file = "z.csv"
    assert tutil.run_cmd(audit.main, f"{CMD_ONLY} {tutil.SQS_OPTS} --{opt.REPORT_FILE} {csv_file}") == e.OK
    # Ensure no duplicate alarms #1478
    problems = []
    regexp = re.compile(r"\d+\\ days")
    platform = os.environ.get("SONAR_TEST_PLATFORM")
    audit_file = f"{tutil.FILES_ROOT}/audit.{platform}.csv"
    if platform is None or not os.path.exists(audit_file):
        audit_file = f"{tutil.FILES_ROOT}/audit.csv"
    with open(csv_file, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        next(reader)
        problems = [tuple((row[1], re.sub(regexp, "[0-9]+ days", re.escape(row[4])))) for row in reader if row[1] not in transient_errors]
    with open(audit_file, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        next(reader)
        old_problems = [tuple((row[1], re.sub(regexp, "[0-9]+ days", re.escape(row[4])))) for row in reader if row[1] not in transient_errors]
    for row in old_problems:
        assert row in problems, f"Problem {row[0]}/{row[1]} not found in new audit comparing {audit_file} and {csv_file}"
    assert problems_present(csv_file, problems)


def test_configure() -> None:
    """test_configure"""
    cmd_map = {
        audit.CONFIG_FILE: audit.main,
        maturity.CONFIG_FILE: maturity.main,
    }
    for file, cmd in cmd_map.items():
        config_file = f"{os.path.expanduser('~')}{os.sep}.{file}"
        config_exists = os.path.exists(config_file)
        if config_exists:
            os.rename(config_file, f"{config_file}.bak")
        assert tutil.run_cmd(cmd, f"{CMD_ONLY} --config") == e.OK
    assert os.path.exists(config_file)
    if config_exists:
        os.rename(f"{config_file}.bak", config_file)


def test_configure_stdout() -> None:
    """test_configure_stdout"""
    cmd_map = {
        audit.CONFIG_FILE: audit.main,
        maturity.CONFIG_FILE: maturity.main,
    }
    for file, cmd in cmd_map.items():
        config_file = f"{os.path.expanduser('~')}{os.sep}.{file}"
        if not os.path.exists(config_file):
            pytest.skip("No $HOME config file")
        last_change = os.stat(config_file).st_ctime_ns
        assert tutil.run_cmd(cmd, f"{CMD} --config") == e.OK
        assert last_change == os.stat(config_file).st_ctime_ns
