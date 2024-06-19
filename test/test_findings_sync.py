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

"""
    sonar-findings-export tests
"""

import os
import sys
from unittest.mock import patch
import pytest

import utilities as util
import sonar.logging as log
from cli import findings_sync


CMD = "sonar-findings-sync.py"
PLAT_OPTS = ["-u", os.getenv("SONAR_HOST_URL_LATEST"), "-t", os.getenv("SONAR_TOKEN_ADMIN_USER")] + [
    "-U",
    os.getenv("SONAR_HOST_URL_TEST"),
    "-T",
    os.getenv("SONAR_TOKEN_SYNC_USER"),
]
SYNC_OPTS = ["--login", "syncer", "-k", "TESTSYNC", "-K", "TESTSYNC"]
ALL_OPTS = [CMD] + PLAT_OPTS + SYNC_OPTS + ["-f", util.JSON_FILE]


def test_sync_help() -> None:
    """test_sync"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", [CMD, "-h"]):
            findings_sync.main()
    assert not os.path.isfile(util.JSON_FILE)


def test_sync() -> None:
    """test_sync"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", ALL_OPTS):
            log.info("Running %s", " ".join(ALL_OPTS))
            findings_sync.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)
