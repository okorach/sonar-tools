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
""" sonarcloud tests """

import os
import sys
from unittest.mock import patch
import pytest

import utilities as util
from sonar import errcodes
import cli.options as opt
from cli import config

CMD = "config.py"
SC_OPTS = [f"-{opt.URL_SHORT}", "https://sonarcloud.io", f"-{opt.TOKEN_SHORT}", os.getenv("SONAR_TOKEN_SONARCLOUD")]

OPTS = [CMD] + SC_OPTS + [f"-{opt.EXPORT_SHORT}", f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]


def test_sc_config_export() -> None:
    """test_sc_config_export"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS + [f"-{opt.ORG_SHORT}", "okorach"]):
            config.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)

def test_sc_config_export_no_org() -> None:
    """test_sc_config_export"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", OPTS):
            config.main()
    assert int(str(e.value)) == errcodes.ARGS_ERROR
    assert not os.path.isfile(util.JSON_FILE)
