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
import test.utilities as testutil
from tools import findings_export

CMD = "sonar-findings-export.py"
CSV_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.CSV_FILE]
JSON_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.JSON_FILE]

def test_findings_export():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_findings_export_json():
    testutil.clean(testutil.JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--format", "json"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


# def test_findings_export_sarif():
#     testutil.clean(testutil.JSON_FILE)
#     with patch.object(sys, 'argv', JSON_OPTS + ["--format", "sarif"]):
#         try:
#             findings_export.main()
#         except SystemExit as e:
#             assert int(str(e)) == 0
#     assert testutil.file_not_empty(testutil.JSON_FILE)
#     testutil.clean(testutil.JSON_FILE)


def test_findings_export_with_url():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--withURL"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_findings_export_statuses():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--statuses", "OPEN,CLOSED"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    os.remove(testutil.CSV_FILE)


def test_findings_export_date():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--createdBefore", "2024-05-01"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    os.remove(testutil.CSV_FILE)


def test_findings_export_resolutions():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--resolutions", "FALSE-POSITIVE,REMOVED"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    os.remove(testutil.CSV_FILE)


def test_findings_export_mixed():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--statuses", "OPEN,CLOSED", "--severities", "MINOR,MAJOR,CRITICAL"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    os.remove(testutil.CSV_FILE)


def test_findings_export_key():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["-k", "okorach_sonar-tools"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_findings_export_alt_api():
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--useFindings"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)
