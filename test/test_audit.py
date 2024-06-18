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

""" sonar-audit tests """

import sys
from unittest.mock import patch
import pytest

import utilities as testutil
from sonar import errcodes, utilities
from cli import audit

CMD = "sonar-audit.py"
CSV_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.CSV_FILE]
JSON_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.JSON_FILE]


def test_audit() -> None:
    """test_audit"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS):
            audit.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_audit_stdout() -> None:
    """test_audit_stdout"""
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", [CMD] + testutil.STD_OPTS):
            audit.main()
    assert int(str(e.value)) == 0


def test_audit_json() -> None:
    """test_audit_json"""
    testutil.clean(testutil.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS):
            audit.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_sif_1() -> None:
    """test_sif_1"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--sif", "test/sif1.json"]):
            audit.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_sif_2() -> None:
    """test_sif_2"""
    testutil.clean(testutil.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif2.json"]):
            audit.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_audit_proj_key() -> None:
    """test_audit_proj_key"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--what", "projects", "-k", "okorach_sonar-tools"]):
            audit.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_audit_proj_non_existing_key() -> None:
    """test_audit_proj_non_existing_key"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--what", "projects", "-k", "okorach_sonar-tools,bad_key"]):
            audit.main()
    assert int(str(e.value)) == errcodes.NO_SUCH_KEY


def test_sif_broken() -> None:
    """test_sif_broken"""
    testutil.clean(testutil.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif_broken.json"]):
            audit.main()
    assert int(str(e.value)) == errcodes.SIF_AUDIT_ERROR


def test_deduct_fmt() -> None:
    """test_deduct_fmt"""
    assert utilities.deduct_format("csv", None) == "csv"
    assert utilities.deduct_format("foo", "file.csv") == "csv"
    assert utilities.deduct_format("foo", "file.json") == "csv"
    assert utilities.deduct_format(None, "file.json") == "json"
    assert utilities.deduct_format(None, "file.csv") == "csv"
    assert utilities.deduct_format(None, "file.txt") == "csv"


def test_sif_non_existing() -> None:
    """test_sif_non_existing"""
    testutil.clean(testutil.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif_non_existing.json"]):
            audit.main()
    assert int(str(e.value)) == errcodes.SIF_AUDIT_ERROR


def test_sif_not_readable() -> None:
    """test_sif_not_readable"""
    testutil.clean(testutil.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif_not_readable.json"]):
            audit.main()
    assert int(str(e.value)) == errcodes.SIF_AUDIT_ERROR
