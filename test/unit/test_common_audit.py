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

""" Common tests, independent of SonarQube version """

import os
import csv
import re
from collections.abc import Generator
import pytest

import utilities as tutil
from sonar import errcodes as e
import cli.options as opt
from cli import audit

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
    assert tutil.run_cmd(audit.main, f"{CMD_ONLY} --{opt.URL} {tutil.SQS_AUDIT} --{opt.REPORT_FILE} {csv_file}") == e.OK
    # Ensure no duplicate alarms #1478
    problems = []
    regexp = re.compile(r"\d+\\ days")
    with open(f"{tutil.FILES_ROOT}/audit.csv", mode="r", encoding="utf-8") as fd:
        reader = csv.reader(fd)
        for row in reader:
            problems.append((row[1], re.sub(regexp, "[0-9]+ days", re.escape(row[4]))))
    assert problems_present(csv_file, problems)


def test_configure() -> None:
    DEFAULT_CONFIG = f"{os.path.expanduser('~')}{os.sep}.sonar-audit.properties"
    config_exists = os.path.exists(DEFAULT_CONFIG)
    if config_exists:
        os.rename(DEFAULT_CONFIG, f"{DEFAULT_CONFIG}.bak")
    assert tutil.run_cmd(audit.main, f"{CMD_ONLY} --config") == e.OK
    assert os.path.exists(DEFAULT_CONFIG)
    if config_exists:
        os.rename(f"{DEFAULT_CONFIG}.bak", DEFAULT_CONFIG)


def test_configure_stdout() -> None:
    DEFAULT_CONFIG = f"{os.path.expanduser('~')}{os.sep}.sonar-audit.properties"
    if not os.path.exists(DEFAULT_CONFIG):
        pytest.skip("No $HOME config file")
    last_change = os.stat(DEFAULT_CONFIG).st_ctime_ns
    assert tutil.run_cmd(audit.main, f"{CMD} --config") == e.OK
    assert last_change == os.stat(DEFAULT_CONFIG).st_ctime_ns
