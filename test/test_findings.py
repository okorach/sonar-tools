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
    sonar-findings-export tests
"""

import os
import sys
from unittest.mock import patch
import pytest
import utilities as testutil
from tools import findings_export
from sonar import options

CMD = "sonar-findings-export.py"
CSV_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.CSV_FILE]
JSON_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.JSON_FILE]


def test_findings_export() -> None:
    """test_findings_export"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_findings_export_json() -> None:
    """test_findings_export_json"""
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


def test_findings_export_with_url() -> None:
    """test_findings_export_with_url"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--withURL"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_findings_export_statuses() -> None:
    """test_findings_export_statuses"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--statuses", "OPEN,CLOSED"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    os.remove(testutil.CSV_FILE)


def test_findings_export_date() -> None:
    """test_findings_export_date"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--createdBefore", "2024-05-01"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    os.remove(testutil.CSV_FILE)


def test_findings_export_resolutions() -> None:
    """test_findings_export_resolutions"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--resolutions", "FALSE-POSITIVE,REMOVED"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    os.remove(testutil.CSV_FILE)


def test_findings_export_mixed() -> None:
    """test_findings_export_mixed"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--statuses", "OPEN,CLOSED", "--severities", "MINOR,MAJOR,CRITICAL"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    os.remove(testutil.CSV_FILE)


def test_findings_export_key() -> None:
    """test_findings_export_key"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["-k", "okorach_sonar-tools"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_findings_export_all_branches() -> None:
    """test_findings_export_all_branches"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["-k", "okorach_sonar-tools", "-b", "*"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_findings_export_some_branch() -> None:
    """test_findings_export_some_branch"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-k", "training:security", "-b", "main"]):
            findings_export.main()
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_findings_export_non_existing_branch() -> None:
    """test_findings_export_non_existing_branch"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-k", "training:security", "-b", "non-existing-branch"]):
            findings_export.main()
    assert int(str(e.value)) == options.ERR_NO_SUCH_KEY
    assert not os.path.isfile(testutil.CSV_FILE)


def test_findings_export_alt_api() -> None:
    """test_findings_export_alt_api"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS + ["--useFindings"]):
        try:
            findings_export.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_wrong_filters() -> None:
    """test_wrong_filters"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--statuses", "OPEN,NOT_OPEN"]):
            findings_export.main()
    assert int(str(e.value)) == options.ERR_WRONG_SEARCH_CRITERIA
    assert not os.path.isfile(testutil.CSV_FILE)

    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--resolutions", "ACCEPTED,SAFE,DO_FIX,WONTFIX"]):
            findings_export.main()
    assert int(str(e.value)) == options.ERR_WRONG_SEARCH_CRITERIA
    assert not os.path.isfile(testutil.CSV_FILE)

    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--types", "BUG,VULN"]):
            findings_export.main()
    assert int(str(e.value)) == options.ERR_WRONG_SEARCH_CRITERIA
    assert not os.path.isfile(testutil.CSV_FILE)

    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["--types", "BUG,VULN"]):
            findings_export.main()
    assert int(str(e.value)) == options.ERR_WRONG_SEARCH_CRITERIA
    assert not os.path.isfile(testutil.CSV_FILE)
