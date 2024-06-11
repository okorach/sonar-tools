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
from sonar import options, utilities

CMD = "sonar-findings-export.py"
CSV_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.CSV_FILE]
JSON_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.JSON_FILE]

__GOOD_OPTS = [
    ["--format", "json", "-l", "sonar-tools.log", "-v", "DEBUG"],
    ["--format", "json", "-f", testutil.JSON_FILE],
    ["--withURL", "--threads", "4", "-f", testutil.CSV_FILE],
    ["--csvSeparator", "';'", "-d", "--tags", "cwe,convention", "-f", testutil.CSV_FILE],
    ["--statuses", "OPEN,CLOSED", "-f", testutil.CSV_FILE],
    ["--createdBefore", "2024-05-01", "-f", testutil.JSON_FILE],
    ["--createdAfter", "2023-05-01", "-f", testutil.CSV_FILE],
    ["--resolutions", "FALSE-POSITIVE,REMOVED", "-f", testutil.CSV_FILE],
    ["--types", "BUG,VULNERABILITY", "-f", testutil.CSV_FILE],
    ["--statuses", "OPEN,CLOSED", "--severities", "MINOR,MAJOR,CRITICAL", "-f", testutil.CSV_FILE],
    ["-k", "okorach_sonar-tools", "-b", "*", "-f", testutil.CSV_FILE],
    ["-k", "training:security", "-b", "main", "-f", testutil.CSV_FILE],
    ["--useFindings", "-f", testutil.CSV_FILE],
]

__WRONG_FILTER_OPTS = [
    ["--statuses", "OPEN,NOT_OPEN"],
    ["--resolutions", "ACCEPTED,SAFE,DO_FIX,WONTFIX"],
    ["--types", "BUG,VULN"],
]


__WRONG_OPTS = [
    ["-k", "non-existing-project-key"],
]


def test_findings_export() -> None:
    """test_findings_export"""
    for opts in __GOOD_OPTS:
        testutil.clean(testutil.CSV_FILE)
        testutil.clean(testutil.JSON_FILE)
        with pytest.raises(SystemExit) as e:
            fullcmd = [CMD] + testutil.STD_OPTS + opts
            utilities.logger.info("Running %s", " ".join(fullcmd))
            with patch.object(sys, "argv", fullcmd):
                findings_export.main()
        assert int(str(e.value)) == 0
        if testutil.CSV_FILE in opts:
            assert testutil.file_not_empty(testutil.CSV_FILE)
        elif testutil.JSON_FILE in opts:
            assert testutil.file_not_empty(testutil.JSON_FILE)
        utilities.logger.info("SUCCESS running: %s", " ".join(fullcmd))
    testutil.clean(testutil.CSV_FILE)
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


def test_wrong_filters() -> None:
    """test_wrong_filters"""
    testutil.clean(testutil.CSV_FILE)
    testutil.clean(testutil.JSON_FILE)
    for bad_opts in __WRONG_FILTER_OPTS:
        with pytest.raises(SystemExit) as e:
            with patch.object(sys, "argv", CSV_OPTS + bad_opts):
                findings_export.main()
        assert int(str(e.value)) == options.ERR_WRONG_SEARCH_CRITERIA
        assert not os.path.isfile(testutil.CSV_FILE)
        assert not os.path.isfile(testutil.JSON_FILE)


def test_wrong_opts() -> None:
    """test_wrong_opts"""
    testutil.clean(testutil.CSV_FILE)
    testutil.clean(testutil.JSON_FILE)
    for bad_opts in __WRONG_OPTS:
        with pytest.raises(SystemExit) as e:
            with patch.object(sys, "argv", CSV_OPTS + bad_opts):
                findings_export.main()
        assert int(str(e.value)) == options.ERR_NO_SUCH_KEY
        assert not os.path.isfile(testutil.CSV_FILE)
        assert not os.path.isfile(testutil.JSON_FILE)


def test_findings_export_non_existing_branch() -> None:
    """test_findings_export_non_existing_branch"""
    testutil.clean(testutil.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + ["-k", "training:security", "-b", "non-existing-branch"]):
            findings_export.main()

    # FIXME: findings-export ignores the branch option see https://github.com/okorach/sonar-tools/issues/1115
    # So passing a non existing branch succeeds
    # assert int(str(e.value)) == options.ERR_NO_SUCH_KEY
    # assert not os.path.isfile(testutil.CSV_FILE)
    assert int(str(e.value)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)
