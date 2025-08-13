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

import os, stat
import csv
import re
from collections.abc import Generator
import pytest

import test.unit.utilities as util
from sonar import errcodes as e, utilities
import cli.options as opt
from cli import audit

CMD_ONLY = "sonar-audit.py"
CMD = f"{CMD_ONLY} {util.SQS_OPTS}"


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
    assert util.run_cmd(audit.main, f"{CMD_ONLY} --{opt.URL} {util.SQS_AUDIT} --{opt.REPORT_FILE} {csv_file}") == e.OK
    # Ensure no duplicate alarms #1478
    problems = []
    regexp = re.compile(r"\d+\\ days")
    with open(f"{util.FILES_ROOT}/audit.csv", mode="r", encoding="utf-8") as fd:
        reader = csv.reader(fd)
        for row in reader:
            problems.append((row[1], re.sub(regexp, "[0-9]+ days", re.escape(row[4]))))
    assert problems_present(csv_file, problems)


def test_sif_broken(csv_file: Generator[str]) -> None:
    """test_sif_broken"""
    assert util.run_cmd(audit.main, f"{CMD} --{opt.REPORT_FILE} {csv_file} --sif {util.FILES_ROOT}/sif_broken.json") == e.SIF_AUDIT_ERROR


def test_sif_non_existing(csv_file: Generator[str]) -> None:
    """test_sif_non_existing"""
    non_existing_file = f"{util.FILES_ROOT}/sif_non_existing.json"
    assert util.run_cmd(audit.main, f"{CMD_ONLY} --{opt.REPORT_FILE} {csv_file} --sif {non_existing_file}") == e.SIF_AUDIT_ERROR


def test_sif_not_readable(json_file: Generator[str]) -> None:
    """test_sif_not_readable"""
    unreadable_file = f"{util.FILES_ROOT}/sif_not_readable.json"
    NO_PERMS = ~stat.S_IRUSR & ~stat.S_IWUSR
    current_permissions = stat.S_IMODE(os.lstat(unreadable_file).st_mode)
    os.chmod(unreadable_file, current_permissions & NO_PERMS)
    assert util.run_cmd(audit.main, f"{CMD_ONLY} --{opt.REPORT_FILE} {json_file} --sif {unreadable_file}") == e.SIF_AUDIT_ERROR
    os.chmod(unreadable_file, current_permissions)


def test_deduct_fmt() -> None:
    """test_deduct_fmt"""
    assert utilities.deduct_format("csv", None) == "csv"
    assert utilities.deduct_format("foo", "file.csv") == "csv"
    assert utilities.deduct_format("foo", "file.json") == "csv"
    assert utilities.deduct_format(None, "file.json") == "json"
    assert utilities.deduct_format(None, "file.csv") == "csv"
    assert utilities.deduct_format(None, "file.txt") == "csv"

def test_configure() -> None:
    DEFAULT_CONFIG = f"{os.path.expanduser('~')}{os.sep}.sonar-audit.properties"
    config_exists = os.path.exists(DEFAULT_CONFIG)
    if config_exists:
        os.rename(DEFAULT_CONFIG, f"{DEFAULT_CONFIG}.bak")
    assert util.run_cmd(audit.main, f"{CMD_ONLY} --config") == e.OK
    assert os.path.exists(DEFAULT_CONFIG)
    if config_exists:
        os.rename(f"{DEFAULT_CONFIG}.bak", DEFAULT_CONFIG)


def test_configure_stdout() -> None:
    DEFAULT_CONFIG = f"{os.path.expanduser('~')}{os.sep}.sonar-audit.properties"
    if not os.path.exists(DEFAULT_CONFIG):
        pytest.skip("No $HOME config file")
    last_change = os.stat(DEFAULT_CONFIG).st_ctime_ns
    assert util.run_cmd(audit.main, f"{CMD} --config") == e.OK
    assert last_change == os.stat(DEFAULT_CONFIG).st_ctime_ns
