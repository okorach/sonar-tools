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

"""sonar-misra tests"""

import os
from collections.abc import Generator
import pytest

import utilities as tutil
from sonar import errcodes as e
from sonar.util import constants as c
from sonar.cli import misra
import cli.options as opt


CMD = "sonar-misra.py"

MISRA_PROJ = "test:carbon"


def test_misra_json(json_file: Generator[str]) -> None:
    """test_misra_json"""
    if tutil.SQ.edition() in (c.CE, c.DE):
        pytest.skip("MISRA export requires Enterprise Edition or above")
    if tutil.SQ.version() < (2025, 6, 0) or tutil.SQ.is_sonarcloud():
        pytest.skip("MISRA export requires SonarQube Server 2025.6 or above")
    assert tutil.run_cmd(misra.main, f"{CMD} {tutil.SQS_OPTS} --{opt.KEY_REGEXP} {MISRA_PROJ} --{opt.REPORT_FILE} {json_file}") == e.OK
    assert tutil.file_not_empty(json_file)


def test_misra_csv(csv_file: Generator[str]) -> None:
    """test_misra_csv"""
    if tutil.SQ.edition() in (c.CE, c.DE):
        pytest.skip("MISRA export requires Enterprise Edition or above")
    if tutil.SQ.version() < (2025, 6, 0) or tutil.SQ.is_sonarcloud():
        pytest.skip("MISRA export requires SonarQube Server 2025.6 or above")
    assert tutil.run_cmd(misra.main, f"{CMD} {tutil.SQS_OPTS} --{opt.KEY_REGEXP} {MISRA_PROJ} --{opt.REPORT_FILE} {csv_file}") == e.OK
    assert 7500 < tutil.csv_nbr_lines(csv_file) < 8500


def test_misra_empty(csv_file: Generator[str]) -> None:
    """test_misra_empty"""
    if tutil.SQ.edition() in (c.CE, c.DE):
        pytest.skip("MISRA export requires Enterprise Edition or above")
    if tutil.SQ.version() < (2025, 6, 0) or tutil.SQ.is_sonarcloud():
        pytest.skip("MISRA export requires SonarQube Server 2025.6 or above")
    assert tutil.run_cmd(misra.main, f"{CMD} {tutil.SQS_OPTS} --{opt.KEY_REGEXP} {tutil.LIVE_PROJECT} --{opt.REPORT_FILE} {csv_file}") == e.OK
    assert tutil.csv_nbr_lines(csv_file) == 0


def test_misra_custom_tags(csv_file: Generator[str]) -> None:
    """test_misra_custom_tags"""
    if tutil.SQ.edition() in (c.CE, c.DE):
        pytest.skip("MISRA export requires Enterprise Edition or above")
    if tutil.SQ.version() < (2025, 6, 0) or tutil.SQ.is_sonarcloud():
        pytest.skip("MISRA export requires SonarQube Server 2025.6 or above")
    assert (
        tutil.run_cmd(misra.main, f"{CMD} {tutil.SQS_OPTS} --{opt.KEY_REGEXP} {MISRA_PROJ} --{opt.REPORT_FILE} {csv_file} --{opt.TAGS} misra-c2012")
        == e.OK
    )
    assert tutil.csv_nbr_lines(csv_file) == 0


def test_misra_wrong_args(csv_file: Generator[str]) -> None:
    """test_misra_wrong_args"""
    if tutil.SQ.edition() in (c.CE, c.DE):
        pytest.skip("MISRA export requires Enterprise Edition or above")
    if tutil.SQ.version() < (2025, 6, 0) or tutil.SQ.is_sonarcloud():
        pytest.skip("MISRA export requires SonarQube Server 2025.6 or above")
    assert (
        tutil.run_cmd(misra.main, f"{CMD} {tutil.SQS_OPTS} --{opt.KEY_REGEXP} {MISRA_PROJ} --{opt.REPORT_FILE} {csv_file} --misra-std c++2023")
        == e.ARGS_ERROR
    )
