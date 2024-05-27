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

import os
import sys
import json
from unittest.mock import patch
from sonar import options
from tools import audit

LATEST = "http://localhost:9999"
LTA = "http://localhost:9000"

CMD = "sonar-audit.py"
CSV_FILE = "temp.csv"
JSON_FILE = "temp.json"

STD_OPTS = [CMD, "-u", os.getenv("SONAR_HOST_URL"), "-t", os.getenv("SONAR_TOKEN_ADMIN_USER")]
CSV_OPTS = STD_OPTS + ["-f", CSV_FILE]
JSON_OPTS = STD_OPTS + ["-f", JSON_FILE]


def __file_not_empty(file: str) -> bool:
    """Returns whether a file exists and is not empty"""
    if not os.path.isfile(file):
        return False
    return os.stat(file).st_size > 0


def __clean(file: str) -> None:
    try:
        os.remove(file)
    except FileNotFoundError:
        pass


def test_audit():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    __clean(CSV_FILE)


def test_audit_stdout():
    with patch.object(sys, "argv", STD_OPTS):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0


def test_audit_json():
    __clean(JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(JSON_FILE)
    __clean(JSON_FILE)


def test_sif_1():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--sif", "test/sif1.json"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    __clean(CSV_FILE)


def test_sif_2():
    __clean(JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif2.json"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(JSON_FILE)
    __clean(JSON_FILE)


def test_audit_proj_key():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--what", "projects", "-k", "okorach_sonar-tools"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    __clean(CSV_FILE)


def test_audit_proj_non_existing_key():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--what", "projects", "-k", "okorach_sonar-tools,bad_key"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == options.ERR_NO_SUCH_KEY


def test_sif_broken():
    __clean(JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif_broken.json"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == options.ERR_SIF_AUDIT_ERROR


def test_deduct_fmt() -> None:
    assert audit.__deduct_format__("csv", None) == "csv"
    assert audit.__deduct_format__("foo", "file.csv") == "foo"
    assert audit.__deduct_format__(None, "file.json") == "json"
    assert audit.__deduct_format__(None, "file.csv") == "csv"
    assert audit.__deduct_format__(None, "file.txt") == "csv"


def test_sif_non_existing():
    __clean(JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif_non_existing.json"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == options.ERR_SIF_AUDIT_ERROR


def test_sif_not_readable():
    __clean(JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--sif", "test/sif_not_readable.json"]):
        try:
            audit.main()
        except SystemExit as e:
            assert int(str(e)) == options.ERR_SIF_AUDIT_ERROR
