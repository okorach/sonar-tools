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

""" Logging tests """

import sys
import os
from unittest.mock import patch
import pytest

import utilities as util
from sonar import errcodes
from cli import loc
import cli.options as opt

CMD = "sonar-loc.py"
CSV_OPTS = [CMD] + util.STD_OPTS + [f"--{opt.REPORT_FILE}", util.CSV_FILE]


def test_no_log_file() -> None:
    """Tests that when no log file is specified, no file is produced"""
    util.clean("sonar-tools.log")
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS):
            loc.main()
    assert int(str(e.value)) == errcodes.OK
    assert not os.path.isfile("sonar-tools.log")
    util.clean(util.CSV_FILE)


def test_custom_log_file() -> None:
    """Tests that when a specific log file is given, logs come in that file"""
    logfile = "sonar-loc-logging.log"
    util.clean(util.CSV_FILE, "sonar-tools.log", logfile)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"-{opt.LOGFILE_SHORT}", logfile]):
            loc.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    assert not os.path.isfile("sonar-tools.log")
    assert util.file_not_empty(logfile)
    with open(logfile, encoding="utf-8") as f:
        first_line = f.readline()
    assert "| sonar-loc |" in first_line
    util.clean(util.CSV_FILE, logfile)


def test_missing_log_filename() -> None:
    """Tests that correct error is raise when log file name is forgotten"""
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"-{opt.LOGFILE_SHORT}"]):
            loc.main()
    assert int(str(e.value)) == errcodes.ARGS_ERROR
