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
from unittest.mock import patch
from sonar import options
from tools import findings_export

LATEST = "http://localhost:9999"
LTA = "http://localhost:9000"

CMD = "sonar-findings-export.py"
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


def test_findings_export():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    __clean(CSV_FILE)


def test_findings_export_json():
    __clean(JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--format", "json"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(JSON_FILE)
    __clean(JSON_FILE)


# def test_findings_export_sarif():
#     __clean(JSON_FILE)
#     with patch.object(sys, 'argv', JSON_OPTS + ["--format", "sarif"]):
#         try:
#             findings_export.main()
#         except SystemExit as e:
#             assert int(str(e)) == 0
#     assert __file_not_empty(JSON_FILE)
#     __clean(JSON_FILE)


def test_findings_export_with_url():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--withURL"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    __clean(CSV_FILE)


def test_findings_export_statuses():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--statuses", "OPEN,CLOSED"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)


def test_findings_export_date():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--createdBefore", "2024-05-01"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)


def test_findings_export_resolutions():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--resolutions", "FALSE-POSITIVE,REMOVED"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)


def test_findings_export_mixed():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--statuses", "OPEN,CLOSED", "--severities", "MINOR,MAJOR,CRITICAL"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    os.remove(CSV_FILE)


def test_findings_export_key():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["-k", "okorach_sonar-tools"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    __clean(CSV_FILE)


def test_findings_export_alt_api():
    __clean(CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--useFindings"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert __file_not_empty(CSV_FILE)
    __clean(CSV_FILE)
