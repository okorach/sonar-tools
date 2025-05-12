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
from unittest.mock import patch

import utilities as util
from sonar import errcodes
from cli import findings_sync
import cli.options as opt


CMD = "sonar-findings-sync.py"

PLAT_OPTS = f"{util.SQS_OPTS} -U {os.getenv('SONAR_HOST_URL_TEST')} -T {os.getenv('SONAR_TOKEN_SYNC_USER')}"
SC_PLAT_OPTS = f"{util.SQS_OPTS} {os.getenv('SONAR_TOKEN_ADMIN_USER')} -U https://sonarcloud.io -T {os.getenv('SONAR_TOKEN_SONARCLOUD')}"
SYNC_OPTS = f"-{opt.KEYS_SHORT} {util.LIVE_PROJECT} -K TESTSYNC -b master -B main"


def test_sync_help() -> None:
    """test_sync"""
    util.run_failed_cmd(findings_sync.main, f"{CMD} -h", errcodes.ARGS_ERROR)


def test_sync(get_json_file: callable) -> None:
    """test_sync"""
    util.run_success_cmd(findings_sync.main, f"{CMD} {PLAT_OPTS} {SYNC_OPTS} -{opt.REPORT_FILE_SHORT} {get_json_file}", True)

def test_sync_scloud(get_json_file: callable) -> None:
    """test_sync"""
    util.run_success_cmd(findings_sync.main, f"{CMD} {SC_PLAT_OPTS} {SYNC_OPTS} --threads 16 -{opt.REPORT_FILE_SHORT} {get_json_file}", True)
