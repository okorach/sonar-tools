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

""" sonar-findings-export tests """

import os
import sys
from unittest.mock import patch
import pytest

import utilities as util
import sonar.logging as log
from cli import findings_export
from sonar import errcodes

CMD = "sonar-findings-export.py"
CSV_OPTS = [CMD] + util.STD_OPTS + ["-f", util.CSV_FILE]
JSON_OPTS = [CMD] + util.STD_OPTS + ["-f", util.JSON_FILE]

__GOOD_OPTS = [
    ["--format", "json", "-l", "sonar-tools.log", "-v", "DEBUG"],
    ["--format", "json", "-f", util.JSON_FILE],
    ["--withURL", "--threads", "4", "-f", util.CSV_FILE],
    ["--csvSeparator", "';'", "-d", "--tags", "cwe,convention", "-f", util.CSV_FILE],
    ["--statuses", "OPEN,CLOSED", "-f", util.CSV_FILE],
    ["--createdBefore", "2024-05-01", "-f", util.JSON_FILE],
    ["--createdAfter", "2023-05-01", "-f", util.CSV_FILE],
    ["--resolutions", "FALSE-POSITIVE,REMOVED", "-f", util.CSV_FILE],
    ["--types", "BUG,VULNERABILITY", "-f", util.CSV_FILE],
    ["--statuses", "OPEN,CLOSED", "--severities", "MINOR,MAJOR,CRITICAL", "-f", util.CSV_FILE],
    ["-k", "okorach_sonar-tools", "-b", "*", "-f", util.CSV_FILE],
    ["-k", "training:security", "-b", "main", "-f", util.CSV_FILE],
    ["--useFindings", "-f", util.CSV_FILE],
]

__WRONG_FILTER_OPTS = [
    ["--statuses", "OPEN,NOT_OPEN"],
    ["--resolutions", "ACCEPTED,SAFE,DO_FIX,WONTFIX"],
    ["--types", "BUG,VULN"],
]


__WRONG_OPTS = [
    ["-k", "non-existing-project-key"],
]


def test_findings_export_sarif_explicit() -> None:
    """Test SARIF export"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ["--format", "sarif"]):
            findings_export.main()
    assert int(str(e.value)) == 0
    assert util.file_contains(util.JSON_FILE, "schemas/json/sarif-2.1.0-rtm.4")
    util.clean(util.JSON_FILE)


def test_findings_export_sarif_implicit() -> None:
    """Test SARIF export for a single project and implicit format"""
    util.clean("issues.sarif")
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + ["-k", "okorach_sonar-tools", "-f", "issues.sarif"]):
            findings_export.main()
    assert int(str(e.value)) == 0
    assert util.file_contains("issues.sarif", "schemas/json/sarif-2.1.0-rtm.4")
    util.clean("issues.sarif")


def test_wrong_filters() -> None:
    """test_wrong_filters"""
    util.clean(util.CSV_FILE, util.JSON_FILE)
    for bad_opts in __WRONG_FILTER_OPTS:
        with pytest.raises(SystemExit) as e:
            with patch.object(sys, "argv", CSV_OPTS + bad_opts):
                findings_export.main()
        assert int(str(e.value)) == errcodes.WRONG_SEARCH_CRITERIA
        assert not os.path.isfile(util.CSV_FILE)
        assert not os.path.isfile(util.JSON_FILE)


def test_wrong_opts() -> None:
    """test_wrong_opts"""
    util.clean(util.CSV_FILE, util.JSON_FILE)
    for bad_opts in __WRONG_OPTS:
        with pytest.raises(SystemExit) as e:
            with patch.object(sys, "argv", CSV_OPTS + bad_opts):
                findings_export.main()
        assert int(str(e.value)) == errcodes.NO_SUCH_KEY
        assert not os.path.isfile(util.CSV_FILE)
        assert not os.path.isfile(util.JSON_FILE)


def test_findings_export_non_existing_branch() -> None:
    """test_findings_export_non_existing_branch"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + ["-k", "training:security", "-b", "non-existing-branch"]):
            findings_export.main()


"""
Language not available in CSV output

def test_findings_filter_on_lang() -> None:
    test_findings_filter_on_lang
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + ["--languages", "py,ts"]):
            findings_export.main()

    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        fh.readline()
        for line in fh.readline():
            (_, lang, _) = line.split(maxsplit=2)
            assert lang in ("py", "ts")
    util.clean(util.CSV_FILE)
"""


def test_findings_filter_on_type() -> None:
    """test_findings_filter_on_type"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + ["--types", "VULNERABILITY,BUG"]):
            findings_export.main()

    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in fh:
            if first:
                first = False
                continue
            (_, _, issue_type, _) = line.split(",", maxsplit=3)
            assert issue_type in ("VULNERABILITY", "BUG")
    # util.clean(util.CSV_FILE)


def test_findings_filter_on_status() -> None:
    """test_findings_filter_on_status"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + ["--resolutions", "FALSE-POSITIVE,ACCEPTED"]):
            findings_export.main()
    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in fh:
            if first:
                first = False
                continue
            (_, _, _, _, status, _) = line.split(",", maxsplit=5)
            assert status in ("FALSE-POSITIVE", "ACCEPTED")
    util.clean(util.CSV_FILE)


def test_findings_filter_on_multiple_criteria() -> None:
    """test_findings_filter_on_multiple_criteria"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + ["--resolutions", "FALSE-POSITIVE,ACCEPTED", "--types", "BUG,CODE_SMELL"]):
            findings_export.main()

    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in fh:
            if first:
                first = False
                continue
            (_, _, issue_type, _, status, _) = line.split(",", maxsplit=5)
            assert status in ("FALSE-POSITIVE", "ACCEPTED")
            assert issue_type in ("BUG", "CODE_SMELL")
    util.clean(util.CSV_FILE)


def test_findings_filter_on_multiple_criteria_2() -> None:
    """test_findings_filter_on_multiple_criteria_2"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + ["--createdAfter", "2020-01-10", "--createdBefore", "2020-12-31", "--types", "SECURITY_HOTSPOT"]):
            findings_export.main()

    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in fh:
            if first:
                first = False
                continue
            (_, _, issue_type, _, _, dt) = line.split(",", maxsplit=5)
            assert dt.split("-")[0] == "2020"
            assert issue_type == "SECURITY_HOTSPOT"
    util.clean(util.CSV_FILE)

    # FIXME: findings-export ignores the branch option see https://github.com/okorach/sonar-tools/issues/1115
    # So passing a non existing branch succeeds
    # assert int(str(e.value)) == errcodes.ERR_NO_SUCH_KEY
    # assert not os.path.isfile(testutil.CSV_FILE)


def test_findings_filter_on_multiple_criteria_3() -> None:
    """test_findings_filter_on_multiple_criteria_3"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + ["--statuses", "ACCEPTED", "--resolutions", "FALSE-POSITIVE"]):
            findings_export.main()

    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in fh:
            if first:
                first = False
                continue
            assert line.split(",")[4] in ("ACCEPTED", "FALSE_POSITIVE", "FALSE-POSITIVE")
    util.clean(util.CSV_FILE)


def test_findings_filter_on_hotspots_multi_1() -> None:
    """test_findings_filter_on_hotspots_multi_1"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + ["--resolutions", "ACKNOWLEDGED, SAFE", "-k", "okorach_sonar-tools,pytorch"]):
            findings_export.main()

    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in fh:
            if first:
                first = False
                continue
            assert line.split(",")[4] in ("ACKNOWLEDGED", "SAFE")
            assert line.split(",")[7] in ("okorach_sonar-tools", "pytorch")
    util.clean(util.CSV_FILE)


def test_findings_export() -> None:
    """test_findings_export"""
    for opts in __GOOD_OPTS:
        util.clean(util.CSV_FILE, util.JSON_FILE)
        with pytest.raises(SystemExit) as e:
            fullcmd = [CMD] + util.STD_OPTS + opts
            log.info("Running %s", " ".join(fullcmd))
            with patch.object(sys, "argv", fullcmd):
                findings_export.main()
        assert int(str(e.value)) == 0
        if util.CSV_FILE in opts:
            assert util.file_not_empty(util.CSV_FILE)
        elif util.JSON_FILE in opts:
            assert util.file_not_empty(util.JSON_FILE)
        log.info("SUCCESS running: %s", " ".join(fullcmd))
    util.clean(util.CSV_FILE, util.JSON_FILE)
