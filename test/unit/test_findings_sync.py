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

"""
sonar-findings-sync tests
"""

import os
from collections.abc import Generator
import pytest

import utilities as tutil
from sonar import errcodes as e
from sonar.util import constants as c
from cli import findings_sync
import cli.options as opt


CMD = "sonar-findings-sync.py"

PLAT_OPTS = f"{tutil.SQS_OPTS} -U {os.getenv('SONAR_HOST_URL_TEST')} -T {os.getenv('SONAR_TOKEN_SYNC_USER')}"
SC_PLAT_OPTS = f"{tutil.SQS_OPTS} -U https://sonarcloud.io -T {os.getenv('SONAR_TOKEN_SONARCLOUD')} -O okorach"
SYNC_OPTS = f"-{opt.KEY_REGEXP_SHORT} {tutil.LIVE_PROJECT} -K TESTSYNC"


def test_sync_help() -> None:
    """test_sync_help"""
    assert tutil.run_cmd(findings_sync.main, f"{CMD} -h") == e.ARGS_ERROR


def test_sync_proj(json_file: Generator[str]) -> None:
    """test_sync_proj"""
    assert tutil.run_cmd(findings_sync.main, f"{CMD} {PLAT_OPTS} {SYNC_OPTS} -{opt.REPORT_FILE_SHORT} {json_file}") == e.OK


def test_sync_branch(json_file: Generator[str]) -> None:
    """test_sync_branch"""
    code = e.UNSUPPORTED_OPERATION if tutil.SQ.edition() == c.CE else e.OK
    assert tutil.run_cmd(findings_sync.main, f"{CMD} {PLAT_OPTS} {SYNC_OPTS} -b master -B main -{opt.REPORT_FILE_SHORT} {json_file}") == code
    if tutil.SQ.edition() == c.CE:
        assert tutil.run_cmd(findings_sync.main, f"{CMD} {PLAT_OPTS} {SYNC_OPTS} -B main -{opt.REPORT_FILE_SHORT} {json_file}") == e.OK


def test_sync_scloud(json_file: Generator[str]) -> None:
    """test_sync_scloud"""
    assert tutil.run_cmd(findings_sync.main, f"{CMD} {SC_PLAT_OPTS} {SYNC_OPTS} --threads 16 -{opt.REPORT_FILE_SHORT} {json_file}") == e.OK
