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
    sonar-audit tests
"""

import sys
from unittest.mock import patch
import utilities as testutil
from sonar import options
from tools import audit

CMD = "sonar-audit.py"
CSV_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.CSV_FILE]
JSON_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.JSON_FILE]


def test_audit() -> None:
    """test_audit"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_audit_stdout() -> None:
    """test_audit_stdout"""
    with patch.object(sys, "argv", [CMD] + testutil.STD_OPTS):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0


def test_audit_json() -> None:
    """test_audit_json"""
    testutil.clean(testutil.JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_sif_1() -> None:
    """test_sif_1"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--sif", "test/sif1.json"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_sif_2() -> None:
    """test_sif_2"""
    testutil.clean(testutil.JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif2.json"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_audit_proj_key() -> None:
    """test_audit_proj_key"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--what", "projects", "-k", "okorach_sonar-tools"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_audit_proj_non_existing_key() -> None:
    """test_audit_proj_non_existing_key"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--what", "projects", "-k", "okorach_sonar-tools,bad_key"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == options.ERR_NO_SUCH_KEY


def test_sif_broken() -> None:
    """test_sif_broken"""
    testutil.clean(testutil.JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif_broken.json"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == options.ERR_SIF_AUDIT_ERROR


def test_deduct_fmt() -> None:
    """test_deduct_fmt"""
    assert audit.__deduct_format__("csv", None) == "csv"
    assert audit.__deduct_format__("foo", "file.csv") == "foo"
    assert audit.__deduct_format__(None, "file.json") == "json"
    assert audit.__deduct_format__(None, "file.csv") == "csv"
    assert audit.__deduct_format__(None, "file.txt") == "csv"


def test_sif_non_existing() -> None:
    """test_sif_non_existing"""
    testutil.clean(testutil.JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif_non_existing.json"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == options.ERR_SIF_AUDIT_ERROR


def test_sif_not_readable() -> None:
    """test_sif_not_readable"""
    testutil.clean(testutil.JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif_not_readable.json"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == options.ERR_SIF_AUDIT_ERROR
