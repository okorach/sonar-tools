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
import csv
import json
from unittest.mock import patch
import pytest

import utilities as util
import sonar.logging as log
from sonar import utilities, projects
from sonar import issues, errcodes
from cli import findings_export
import cli.options as opt

CMD = "sonar-findings-export.py"
SARIF_FILE = "issues.sarif"
CSV_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE]
JSON_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]

RULE_COL = 1
LANG_COL = 2
SEVERITY_COL = 3
STATUS_COL = 4
DATE_COL = 5
TYPE_COL = 3
PROJECT_COL = 7
PROJECT_NAME_COL = 8
BRANCH_COL = 9
PR_COL = 10

if util.SQ.version() < (10, 2, 0):
    SEVERITY_COL += 1
    STATUS_COL += 1
    DATE_COL += 1
    PROJECT_COL += 1

__GOOD_OPTS = [
    [f"--{opt.FORMAT}", "json", f"-{opt.LOGFILE_SHORT}", "sonar-tools.log", f"--{opt.VERBOSE}", "DEBUG"],
    [f"--{opt.FORMAT}", "json", f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE],
    [f"--{opt.WITH_URL}", f"--{opt.NBR_THREADS}", "4", f"--{opt.REPORT_FILE}", util.CSV_FILE],
    [f"--{opt.CSV_SEPARATOR}", ";", "-d", f"--{opt.TAGS}", "cwe,convention", f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE],
    [f"--{opt.STATUSES}", "OPEN,CLOSED", f"--{opt.REPORT_FILE}", util.CSV_FILE],
    [f"--{opt.DATE_BEFORE}", "2024-05-01", f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE],
    [f"--{opt.DATE_AFTER}", "2023-05-01", f"--{opt.REPORT_FILE}", util.CSV_FILE],
    [f"--{opt.RESOLUTIONS}", "FALSE-POSITIVE,REMOVED", f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE],
    [f"--{opt.TYPES}", "BUG,VULNERABILITY", f"--{opt.REPORT_FILE}", util.CSV_FILE],
    [f"--{opt.STATUSES}", "OPEN,CLOSED", f"--{opt.SEVERITIES}", "MINOR,MAJOR,CRITICAL", f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE],
    [f"-{opt.KEYS_SHORT}", "okorach_sonar-tools", f"-{opt.WITH_BRANCHES_SHORT}", "*", f"--{opt.REPORT_FILE}", util.CSV_FILE],
    [f"--{opt.KEYS}", "training:security", f"-{opt.WITH_BRANCHES_SHORT}", "main", f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE],
    [f"--{opt.USE_FINDINGS}", "-f", util.CSV_FILE],
    ["--apps", f"--{opt.BRANCHES}", "*", f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE],
    ["--portfolios", f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE],
]

__WRONG_FILTER_OPTS = [
    [f"--{opt.STATUSES}", "OPEN,NOT_OPEN"],
    [f"--{opt.RESOLUTIONS}", "ACCEPTED,SAFE,DO_FIX,WONTFIX"],
    [f"--{opt.TYPES}", "BUG,VULN"],
    [f"--{opt.SEVERITIES}", "HIGH,SUPER_HIGH"],
    [f"--{opt.CSV_SEPARATOR}", "';'", "-d", f"--{opt.TAGS}", "cwe,convention", f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE],
]

__WRONG_OPTS = [
    [f"-{opt.KEYS_SHORT}", "non-existing-project-key"],
    ["--apps", f"-{opt.KEYS_SHORT}", "okorach_sonar-tools"],
    ["--portfolios", f"-{opt.KEYS_SHORT}", "okorach_sonar-tools"],
]


def test_findings_export_sarif_explicit() -> None:
    """Test SARIF export"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + [f"--{opt.FORMAT}", "sarif"]):
            findings_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_contains(util.JSON_FILE, "schemas/json/sarif-2.1.0-rtm.4")
    util.clean(util.JSON_FILE)


def test_findings_export_sarif_implicit() -> None:
    """Test SARIF export for a single project and implicit format"""
    util.clean(SARIF_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + [f"-{opt.KEYS_SHORT}", "okorach_sonar-tools", f"-{opt.REPORT_FILE_SHORT}", SARIF_FILE]):
            findings_export.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_contains(SARIF_FILE, "schemas/json/sarif-2.1.0-rtm.4")
    util.clean(SARIF_FILE)


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
        assert int(str(e.value)) == errcodes.NO_SUCH_KEY or (
            int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION and util.SQ.edition() in ("community", "developer")
        )
        assert not os.path.isfile(util.CSV_FILE)
        assert not os.path.isfile(util.JSON_FILE)


def test_findings_export_non_existing_branch() -> None:
    """test_findings_export_non_existing_branch"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.KEYS}", "training:security", f"-{opt.BRANCHES_SHORT}", "non-existing-branch"]):
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
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.TYPES}", "VULNERABILITY,BUG"]):
            findings_export.main()

    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in csv.reader(fh):
            if first:
                first = False
                continue
            if util.SQ.version() >= (10, 2, 0):
                # FIXME: Hack because SonarQube returns rule S2310 in the SECURITY or RELIABILITY although it's maintainability
                assert line[RULE_COL] == "javascript:S2310" or "SECURITY:" in line[TYPE_COL] or "RELIABILITY:" in line[TYPE_COL]
            else:
                assert line[TYPE_COL] in ("VULNERABILITY", "BUG")
        util.clean(util.CSV_FILE)


def test_findings_filter_on_resolution() -> None:
    """test_findings_filter_on_resolution"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.RESOLUTIONS}", "FALSE-POSITIVE,ACCEPTED,SAFE"]):
            findings_export.main()
    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in csv.reader(fh):
            if first:
                first = False
                continue
            assert line[STATUS_COL] in ("FALSE-POSITIVE", "ACCEPTED", "SAFE")
    util.clean(util.CSV_FILE)


def test_findings_filter_on_severity() -> None:
    """test_findings_filter_on_resolution"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.SEVERITIES}", "CRITICAL,MAJOR"]):
            findings_export.main()
    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in csv.reader(fh):
            if first:
                first = False
                continue
            if util.SQ.version() >= (10, 2, 0):
                assert ":HIGH" in line[SEVERITY_COL] or ":MEDIUM" in line[SEVERITY_COL]
            else:
                assert line[SEVERITY_COL] in ("CRITICAL", "MAJOR")
    util.clean(util.CSV_FILE)


def test_findings_filter_on_multiple_criteria() -> None:
    """test_findings_filter_on_multiple_criteria"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.RESOLUTIONS}", "FALSE-POSITIVE,ACCEPTED", f"--{opt.TYPES}", "BUG,CODE_SMELL"]):
            findings_export.main()

    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in csv.reader(fh):
            if first:
                first = False
                continue
            assert line[STATUS_COL] in ("FALSE-POSITIVE", "ACCEPTED")
            if util.SQ.version() >= (10, 2, 0):
                assert "MAINTAINABILITY:" in line[TYPE_COL] or "RELIABILITY:" in line[TYPE_COL]
            else:
                assert line[TYPE_COL] in ("BUG", "CODE_SMELL")
    util.clean(util.CSV_FILE)


def test_findings_filter_on_multiple_criteria_2() -> None:
    """test_findings_filter_on_multiple_criteria_2"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(
            sys, "argv", CSV_OPTS + [f"--{opt.DATE_AFTER}", "2020-01-10", f"--{opt.DATE_BEFORE}", "2020-12-31", f"--{opt.TYPES}", "SECURITY_HOTSPOT"]
        ):
            findings_export.main()

    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in csv.reader(fh):
            if first:
                first = False
                continue
            if util.SQ.version() >= (10, 2, 0):
                assert line[SEVERITY_COL] == "SECURITY:UNDEFINED"
            else:
                assert line[TYPE_COL] == "SECURITY_HOTSPOT"
            assert line[DATE_COL].split("-")[0] == "2020"
    util.clean(util.CSV_FILE)

    # FIXME: findings-export ignores the branch option see https://github.com/okorach/sonar-tools/issues/1115
    # So passing a non existing branch succeeds
    # assert int(str(e.value)) == errcodes.ERR_NO_SUCH_KEY
    # assert not os.path.isfile(testutil.CSV_FILE)


def test_findings_filter_on_multiple_criteria_3() -> None:
    """test_findings_filter_on_multiple_criteria_3"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.STATUSES}", "ACCEPTED", f"--{opt.RESOLUTIONS}", "FALSE-POSITIVE"]):
            findings_export.main()

    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in csv.reader(fh):
            if first:
                first = False
                continue
            assert line[STATUS_COL] in ("ACCEPTED", "FALSE_POSITIVE", "FALSE-POSITIVE")
    util.clean(util.CSV_FILE)


def test_findings_filter_on_hotspots_multi_1() -> None:
    """test_findings_filter_on_hotspots_multi_1"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(
            sys, "argv", CSV_OPTS + [f"--{opt.RESOLUTIONS}", "ACKNOWLEDGED, SAFE", f"-{opt.KEYS_SHORT}", "okorach_sonar-tools,pytorch"]
        ):
            findings_export.main()

    first = True
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in csv.reader(fh):
            if first:
                first = False
                continue
            assert line[STATUS_COL] in ("ACKNOWLEDGED", "SAFE")
            assert line[PROJECT_COL] in ("okorach_sonar-tools", "pytorch")
    util.clean(util.CSV_FILE)


def test_findings_filter_hotspot_on_lang() -> None:
    """test_findings_filter_hotspot_on_lang"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit):
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.LANGUAGES}", "java,js"]):
            findings_export.main()
    # TODO Add Language column on findings export
    util.clean(util.CSV_FILE)


def test_findings_export() -> None:
    """test_findings_export"""
    for opts in __GOOD_OPTS:
        if (util.SQ.edition() == "community" and ("--apps" in opts or "--portfolios" in opts)) or (
            util.SQ.edition() == "developer" and "--portfolios" in opts
        ):
            with pytest.raises(SystemExit) as e:
                fullcmd = [CMD] + util.STD_OPTS + opts
                with patch.object(sys, "argv", fullcmd):
                    findings_export.main()
            assert int(str(e.value)) == errcodes.UNSUPPORTED_OPERATION
        else:
            util.clean(util.CSV_FILE, util.JSON_FILE)
            with pytest.raises(SystemExit) as e:
                fullcmd = [CMD] + util.STD_OPTS + opts
                log.info("Running %s", " ".join(fullcmd))
                with patch.object(sys, "argv", fullcmd):
                    findings_export.main()
            assert int(str(e.value)) == errcodes.OK
            if util.CSV_FILE in opts:
                assert util.file_not_empty(util.CSV_FILE)
            elif util.JSON_FILE in opts:
                assert util.file_not_empty(util.JSON_FILE)
            log.info("SUCCESS running: %s", " ".join(fullcmd))
    util.clean(util.CSV_FILE, util.JSON_FILE)


def test_issues_count_0() -> None:
    """test_issues_count"""
    assert issues.count(util.SQ) > 10000


def test_issues_count_1() -> None:
    """test_issues_count"""
    total = issues.count(util.SQ)
    assert issues.count(util.SQ, severities=["BLOCKER"]) < int(total / 3)


def test_issues_count_2() -> None:
    """test_issues_count"""
    total = issues.count(util.SQ)
    assert issues.count(util.SQ, types=["VULNERABILITY"]) < int(total / 10)


def test_issues_count_3() -> None:
    """test_issues_count"""
    assert issues.count(util.SQ, createdBefore="1970-01-08") == 0


def test_search_issues_by_project() -> None:
    """test_search_issues_by_project"""
    nb_issues = len(issues.search_by_project(endpoint=util.SQ, project_key="okorach_sonar-tools", search_findings=True))
    if util.SQ.version() < (10, 0, 0):
        assert 200 <= nb_issues <= 1000
    else:
        assert 500 <= nb_issues <= 1500
    nb_issues = len(issues.search_by_project(endpoint=util.SQ, project_key="okorach_sonar-tools", params={"resolved": "false"}))
    assert nb_issues < 1000
    nb_issues = len(issues.search_by_project(endpoint=util.SQ, project_key=None))
    assert nb_issues > 1000


def test_search_too_many_issues() -> None:
    """test_search_too_many_issues"""
    issue_list = issues.search_all(endpoint=util.SQ)
    assert len(issue_list) > 10000


def test_output_format_sarif() -> None:
    """test_output_format_sarif"""
    util.clean(SARIF_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", [CMD] + util.STD_OPTS + [f"--{opt.REPORT_FILE}", SARIF_FILE, f"--{opt.KEYS}", "okorach_sonar-tools"]):
            findings_export.main()
    assert int(str(e.value)) == errcodes.OK
    with open(SARIF_FILE, encoding="utf-8") as fh:
        sarif_json = json.loads(fh.read())
    assert sarif_json["$schema"] == "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0-rtm.4.json"
    run = sarif_json["runs"][0]
    assert run["tool"]["driver"]["name"] == "SonarQube"
    for issue in run["results"]:
        for k in "message", "locations", "ruleId", "level":
            assert k in issue
        loc = issue["locations"][0]["physicalLocation"]
        assert "region" in loc
        assert "uri" in loc["artifactLocation"]
        for k in "startLine", "endLine", "startColumn", "endColumn":
            assert k in loc["region"]
        for k in "creationDate", "key", "projectKey", "updateDate":
            assert k in issue["properties"]
        assert "effort" in issue["properties"] or issue["properties"]["type"] == "SECURITY_HOTSPOT"
        assert "language" in issue["properties"] or issue["ruleId"].startswith("external")
        assert issue["level"] in ("warning", "error")
    util.clean(SARIF_FILE)


def test_output_format_json() -> None:
    """test_output_format_json"""
    util.clean(util.JSON_FILE)
    log.set_debug_level("INFO")
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + [f"--{opt.KEYS}", "okorach_sonar-tools"]):
            findings_export.main()
    assert int(str(e.value)) == errcodes.OK
    with open(util.JSON_FILE, encoding="utf-8") as fh:
        json_data = json.loads(fh.read())
    for issue in json_data:
        log.info("ISSUE = %s", json.dumps(issue))
        for k in "creationDate", "type", "file", "key", "message", "projectKey", "rule", "updateDate":
            assert k in issue
        assert "effort" in issue or issue["type"] == "SECURITY_HOTSPOT"
        assert "language" in issue or issue["rule"].startswith("external")
        # Some issues have no author so we cannot expect the below assertion to succeed all the time
        # assert issue["status"] in ("FIXED", "CLOSED") or "author" in issue
    util.clean(util.JSON_FILE)


def test_output_format_csv() -> None:
    """test_output_format_csv"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.KEYS}", "okorach_sonar-tools"]):
            findings_export.main()
    assert int(str(e.value)) == errcodes.OK
    with open(util.CSV_FILE, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        row = next(reader)
        for k in "creationDate", "effort", "file", "key", "line", "language", "author", "message", "projectKey", "rule", "updateDate":
            assert k in row
    util.clean(util.CSV_FILE)


def test_output_format_branch() -> None:
    """test_output_format_branch"""
    for br in "develop", "master,develop":
        util.clean(util.CSV_FILE)
        with pytest.raises(SystemExit) as e:
            with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.KEYS}", "okorach_sonar-tools", f"--{opt.BRANCHES}", br]):
                findings_export.main()
        assert int(str(e.value)) == errcodes.OK
        br_list = utilities.csv_to_list(br)
        br, pr = BRANCH_COL, PR_COL
        if util.SQ.version() < (10, 2, 0):
            br += 1
            pr += 1
        with open(util.CSV_FILE, encoding="utf-8") as fd:
            reader = csv.reader(fd)
            next(reader)
            for line in reader:
                assert line[br] in br_list
                assert line[pr] == ""
                assert line[PROJECT_COL] == "okorach_sonar-tools"
        util.clean(util.CSV_FILE)


def test_all_prs() -> None:
    """Tests that findings extport for all PRs of a project works"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.KEYS}", "okorach_sonar-tools", f"--{opt.PULL_REQUESTS}", "*"]):
            findings_export.main()
    assert int(str(e.value)) == errcodes.OK
    with open(util.CSV_FILE, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        next(reader)
        for line in reader:
            assert line[BRANCH_COL] == ""
            assert line[PR_COL] != ""
            assert line[PROJECT_COL] == "okorach_sonar-tools"
    util.clean(util.CSV_FILE)


def test_one_pr() -> None:
    """Tests that findings extport for a single name PR of a project works"""
    proj = projects.Project.get_object(endpoint=util.SQ, key="okorach_sonar-tools")
    for pr in proj.pull_requests().keys():
        util.clean(util.CSV_FILE)
        with pytest.raises(SystemExit) as e:
            with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.KEYS}", "okorach_sonar-tools", f"--{opt.PULL_REQUESTS}", pr]):
                findings_export.main()
        assert int(str(e.value)) == errcodes.OK
        with open(util.CSV_FILE, encoding="utf-8") as fd:
            reader = csv.reader(fd)
            next(reader)
            for line in reader:
                assert line[BRANCH_COL] == ""
                assert line[PR_COL] == pr
                assert line[PROJECT_COL] == "okorach_sonar-tools"
        util.clean(util.CSV_FILE)
