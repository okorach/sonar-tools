#!/usr/bin/env python3
#
# sonar-migration tests
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

""" sonar-migration tests """

import os
import sys
import json
from unittest.mock import patch
import pytest

import utilities as util
from sonar import errcodes
import cli.options as opt
from cli import migration

CMD = "migration.py"
OPTS = [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]


def __test_config_cmd(arguments: list[str]) -> None:
    """Runs a test command"""
    outputfile = arguments[arguments.index(f"-{opt.REPORT_FILE_SHORT}") + 1]
    util.clean(outputfile)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", arguments):
            migration.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(outputfile)
    util.clean(outputfile)


def test_migration_help() -> None:
    """test_migration_help"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS + ["-h"]):
            migration.main()
    assert int(str(e.value)) == 10
    assert not os.path.isfile(util.JSON_FILE)


def test_migration_basic() -> None:
    """test_config_export"""
    __test_config_cmd(OPTS)
