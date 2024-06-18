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
from cli import projects_export

CMD = "projects_export.py"
OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.JSON_FILE]


def __test_project_export(arguments: list[str], file: str) -> None:
    """Runs a test command"""
    testutil.clean(file)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", arguments):
            projects_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(file)
    testutil.clean(file)


def test_export_all_proj() -> None:
    """test_export_all_proj"""
    __test_project_export(OPTS, testutil.JSON_FILE)


def test_export_single_proj() -> None:
    """test_export_single_proj"""
    __test_project_export(OPTS + ["-k", "okorach_sonar-tools"], testutil.JSON_FILE)


def test_export_timeout() -> None:
    """test_export_timeout"""
    __test_project_export(OPTS + ["-k", "okorach_sonar-tools", "--exportTimeout", "10"], testutil.JSON_FILE)


def test_export_non_existing_project() -> None:
    """test_config_non_existing_project"""
    testutil.clean(testutil.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS + ["-k", "okorach_sonar-tools,bad_project"]):
            projects_export.main()
    assert int(str(e.value)) == errcodes.NO_SUCH_KEY
    assert not os.path.isfile(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_two_threads() -> None:
    """test_two_threads"""
    __test_project_export(OPTS + ["--threads", "2"], testutil.JSON_FILE)
