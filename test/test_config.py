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
    sonar-config tests
"""

import os
import sys
from unittest.mock import patch
import pytest
import utilities as testutil
from sonar import errcodes
from cli import config

CMD = "config.py"
OPTS = [CMD] + testutil.STD_OPTS + ["-e", "-f", testutil.JSON_FILE]


def __test_config_cmd(arguments: list[str]) -> None:
    """Runs a test command"""
    testutil.clean(testutil.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", arguments):
            config.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_config_export() -> None:
    """test_config_export"""
    __test_config_cmd(OPTS)


def test_config_export_full() -> None:
    """test_config_export_full"""
    __test_config_cmd(OPTS + ["--fullExport"])


def test_config_export_partial_1() -> None:
    """test_config_export_partial_1"""
    __test_config_cmd(OPTS + ["-w", "projects"])


def test_config_export_partial_2() -> None:
    """test_config_export_partial_2"""
    __test_config_cmd(OPTS + ["-w", "settings,portfolios,users"])


def test_config_export_partial_3() -> None:
    """test_config_export_partial_3"""
    __test_config_cmd(OPTS + ["-w", "projects", "-k", "okorach_sonar-tools"])


def test_config_export_wrong() -> None:
    """test_config_export_wrong"""
    testutil.clean(testutil.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS + ["-w", "settings,wrong,users"]):
            config.main()
    assert int(str(e.value)) == errcodes.ARGS_ERROR
    assert not os.path.isfile(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_config_non_existing_project() -> None:
    """test_config_non_existing_project"""
    testutil.clean(testutil.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS + ["-k", "okorach_sonar-tools,bad_project"]):
            config.main()
    assert int(str(e.value)) == errcodes.NO_SUCH_KEY
    assert not os.path.isfile(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)
