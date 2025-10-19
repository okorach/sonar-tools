#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2024-2025 Olivier Korach
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

"""sonar-findings-export tests"""

import os
import sys
import csv
import json
from collections.abc import Generator
from unittest.mock import patch
import pytest

import utilities as tutil
from sonar import utilities, projects
from sonar import issues
from sonar import errcodes as e
from sonar.util import constants as c, issue_defs as idefs

from cli import findings_export
import cli.options as opt

CMD = f"sonar-findings-export.py {tutil.SQS_OPTS}"

CE_FORBIDDEN_OPTIONS = (
    f"--{opt.APPS}",
    f"--{opt.PORTFOLIOS}",
    f"--{opt.BRANCH_REGEXP}",
    f"-{opt.BRANCH_REGEXP_SHORT}",
    f"--{opt.PULL_REQUESTS}",
    f"-{opt.PULL_REQUESTS_SHORT}",
)

__GOOD_OPTS = [
    f"--{opt.FORMAT} json -{opt.KEY_REGEXP_SHORT} ({tutil.PROJECT_0}|{tutil.PROJECT_1}) -{opt.REPORT_FILE_SHORT} {tutil.JSON_FILE}",
    f"--{opt.CSV_SEPARATOR} ; -d --{opt.TAGS} cwe,convention",
    f"-{opt.KEY_REGEXP_SHORT} {tutil.PROJECT_0} -{opt.BRANCH_REGEXP_SHORT} .+",
    f"--{opt.KEY_REGEXP} training:security -{opt.BRANCH_REGEXP_SHORT} main",
    f"--{opt.USE_FINDINGS} -{opt.KEY_REGEXP_SHORT} ({tutil.PROJECT_0}|{tutil.PROJECT_1})",
    f"--{opt.APPS} -{opt.KEY_REGEXP_SHORT} APP_TEST --{opt.BRANCH_REGEXP} .+",
    # See issue #2011 f"--{opt.PORTFOLIOS} -{opt.KEY_REGEXP_SHORT} Banking -{opt.REPORT_FILE_SHORT} {tutil.CSV_FILE}",
    f"-{opt.KEY_REGEXP_SHORT} {tutil.PROJECT_0} -{opt.BRANCH_REGEXP_SHORT} .+",
    f"--{opt.STATUSES} OPEN,CLOSED --{opt.SEVERITIES} {idefs.STD_SEVERITY_BLOCKER},{idefs.STD_SEVERITY_CRITICAL}",
]

__GOOD_OPTS_LONG = [
    f"--{opt.FORMAT} json --{opt.NBR_THREADS} 16 -{opt.LOGFILE_SHORT} sonar-tools.log --{opt.VERBOSE} DEBUG",
    f"--{opt.WITH_URL} --{opt.NBR_THREADS} 16",
    f"--{opt.STATUSES} OPEN,CLOSED",
]


__WRONG_FILTER_OPTS = [
    f"--{opt.STATUSES} OPEN,NOT_OPEN",
    f"--{opt.RESOLUTIONS} ACCEPTED,SAFE,DO_FIX,WONTFIX",
    f"--{opt.TYPES} BUG,VULN",
    f"--{opt.SEVERITIES} HIGH,SUPER_HIGH",
    f"--{opt.CSV_SEPARATOR} ';' -d --{opt.TAGS} cwe,convention",
]

__WRONG_OPTS = [
    [f"-{opt.KEY_REGEXP_SHORT}", "non-existing-project-key"],
    [f"--{opt.APPS}", f"-{opt.KEY_REGEXP_SHORT}", tutil.LIVE_PROJECT],
    [f"--{opt.PORTFOLIOS}", f"-{opt.KEY_REGEXP_SHORT}", tutil.LIVE_PROJECT],
]


def test_findings_export_sarif_explicit(json_file: Generator[str]) -> None:
    """Test SARIF export"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} --{opt.KEY_REGEXP} {tutil.LIVE_PROJECT} --{opt.FORMAT} sarif"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    assert tutil.file_contains(json_file, "schemas/json/sarif-2.1.0-rtm.4")


def test_findings_export_sarif_implicit(sarif_file: Generator[str]) -> None:
    """Test SARIF export for a single project and implicit format"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {sarif_file} --{opt.KEY_REGEXP} {tutil.LIVE_PROJECT} --{opt.FORMAT} sarif"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    assert tutil.file_contains(sarif_file, "schemas/json/sarif-2.1.0-rtm.4")


def test_wrong_filters(csv_file: Generator[str]) -> None:
    """test_wrong_filters"""
    for bad_opts in __WRONG_FILTER_OPTS:
        assert tutil.run_cmd(findings_export.main, f"{CMD} --{opt.REPORT_FILE} {csv_file} {bad_opts}") == e.WRONG_SEARCH_CRITERIA


def test_wrong_opts(csv_file: Generator[str]) -> None:
    """test_wrong_opts"""
    for bad_opts in __WRONG_OPTS:
        with pytest.raises(SystemExit) as exc:
            with patch.object(sys, "argv", [CMD] + tutil.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", csv_file] + bad_opts):
                findings_export.main()
        assert int(str(exc.value)) == e.WRONG_SEARCH_CRITERIA or (
            int(str(exc.value)) == e.UNSUPPORTED_OPERATION and tutil.SQ.edition() in (c.CE, c.DE)
        )
        assert not os.path.isfile(csv_file)


def test_findings_export_non_existing_branch() -> None:
    """test_findings_export_non_existing_branch"""
    cmd = f"{CMD} --{opt.KEY_REGEXP} training:security --{opt.BRANCH_REGEXP} non-existing-branch"
    err = e.UNSUPPORTED_OPERATION if tutil.SQ.edition() == c.CE else e.WRONG_SEARCH_CRITERIA
    assert tutil.run_cmd(findings_export.main, cmd) == err


def test_findings_filter_on_date_after(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_date_after"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} -{opt.KEY_REGEXP_SHORT} {tutil.LIVE_PROJECT} --{opt.DATE_AFTER} 2023-05-01"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        (date_col,) = tutil.get_cols(next(csvreader), "creationDate")
        for line in csvreader:
            assert line[date_col][:10] >= "2023-05-01"


def test_findings_filter_on_date_before(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_date_before"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} -{opt.KEY_REGEXP_SHORT} {tutil.LIVE_PROJECT} --{opt.DATE_BEFORE} 2024-05-01"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        (date_col,) = tutil.get_cols(next(csvreader), "creationDate")
        for line in csvreader:
            assert line[date_col][:10] <= "2024-05-01"


def test_findings_filter_on_type(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_type"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.TYPES} {idefs.TYPE_VULN},{idefs.TYPE_BUG}"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    col_name = "legacyType" if tutil.SQ.version() >= c.MQR_INTRO_VERSION else "type"
    tutil.csv_col_is_value(csv_file, col_name, idefs.TYPE_VULN, idefs.TYPE_BUG)


def test_findings_filter_on_resolution(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_resolution"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.RESOLUTIONS} FALSE-POSITIVE,ACCEPTED,SAFE"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    statuses = ("FALSE-POSITIVE", "SAFE")
    statuses += ("ACCEPTED",) if tutil.SQ.version() >= c.ACCEPT_INTRO_VERSION else ("WONTFIX",)
    assert tutil.csv_col_is_value(csv_file, "status", *statuses)


def test_findings_filter_on_severity(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_severity"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.SEVERITIES} {idefs.STD_SEVERITY_BLOCKER},{idefs.STD_SEVERITY_CRITICAL}"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    if tutil.SQ.version() < c.MQR_INTRO_VERSION:
        assert tutil.csv_col_is_value(csv_file, "severity", idefs.STD_SEVERITY_BLOCKER, idefs.STD_SEVERITY_CRITICAL)
        return
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        (sec, other, legacy) = tutil.get_cols(next(csvreader := csv.reader(fh)), "securityImpact", "otherImpact", "legacySeverity")
        other += 1
        for line in csvreader:
            if tutil.SQ.version() < (10, 7, 0):
                sev1, sev2, sev3 = "HIGH", "MEDIUM", "HIGH(HOTSPOT)"
            else:
                sev1, sev2, sev3 = idefs.MQR_SEVERITY_BLOCKER, idefs.MQR_SEVERITY_HIGH, "HIGH(HOTSPOT)"
            assert (
                sev1 in line[sec:other]
                or sev2 in line[sec:other]
                or sev3 in line[sec:other]
                or line[legacy] in (idefs.STD_SEVERITY_BLOCKER, idefs.STD_SEVERITY_CRITICAL)
            )


def test_findings_filter_on_multiple_criteria(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_multiple_criteria"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.RESOLUTIONS} FALSE-POSITIVE,ACCEPTED --{opt.TYPES} {idefs.TYPE_BUG},{idefs.TYPE_CODE_SMELL}"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    assert tutil.csv_col_is_value(
        csv_file, "type" if tutil.SQ.version() < c.MQR_INTRO_VERSION else "legacyType", idefs.TYPE_BUG, idefs.TYPE_CODE_SMELL
    )
    assert tutil.csv_col_is_value(csv_file, "status", "FALSE-POSITIVE", "WONTFIX" if tutil.SQ.version() < c.ACCEPT_INTRO_VERSION else "ACCEPTED")
    if tutil.SQ.version() < c.MQR_INTRO_VERSION:
        return
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        (maint_col, rel_col) = tutil.get_cols(next(csvreader := csv.reader(fh)), "maintainabilityImpact", "reliabilityImpact")
        for line in csvreader:
            assert line[maint_col] != "" or line[rel_col] != ""


def test_findings_filter_on_multiple_criteria_2(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_multiple_criteria_2"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.DATE_AFTER} 2020-01-10 --{opt.DATE_BEFORE} 2020-12-31 --{opt.TYPES} {idefs.TYPE_HOTSPOT}"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    assert tutil.csv_col_match(csv_file, "creationDate", r"2020-\d\d-\d\d")
    colname = "legacyType" if tutil.SQ.version() >= c.MQR_INTRO_VERSION else "type"
    assert tutil.csv_col_is_value(csv_file, colname, idefs.TYPE_HOTSPOT)


def test_findings_filter_on_status(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_multiple_criteria_2"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.STATUSES} FALSE_POSITIVE,ACCEPTED"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    assert tutil.csv_col_is_value(csv_file, "status", "FALSE-POSITIVE", "ACCEPTED", "WONTFIX")


def test_findings_filter_on_multiple_criteria_3(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_multiple_criteria_3"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.STATUSES} ACCEPTED --{opt.RESOLUTIONS} FALSE-POSITIVE"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    statuses = ("FALSE_POSITIVE", "FALSE-POSITIVE")
    statuses += ("ACCEPTED",) if tutil.SQ.version() >= c.ACCEPT_INTRO_VERSION else ("WONTFIX",)
    assert tutil.csv_col_is_value(csv_file, "status", *statuses)
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        (status_col,) = tutil.get_cols(next(csvreader), "status")
        for line in csvreader:
            assert line[status_col] in statuses


def test_findings_filter_on_hotspots_multi_1(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_hotspots_multi_1"""
    projs = [tutil.PROJECT_0, tutil.PROJECT_1]
    regexp = utilities.list_to_regexp(projs)
    cmd = f'{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.RESOLUTIONS} "ACKNOWLEDGED, SAFE" -{opt.KEY_REGEXP_SHORT} {regexp}'
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    assert tutil.csv_col_is_value(csv_file, "projectKey", *projs)
    assert tutil.csv_col_is_value(csv_file, "status", "ACKNOWLEDGED", "SAFE")


def test_findings_filter_on_lang(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_lang"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.LANGUAGES} java,js"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    assert tutil.csv_col_is_value(csv_file, "language", "java", "js")
    assert tutil.csv_col_has_values(csv_file, "language", "java", "js")


def test_findings_filter_on_hotspot_type(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_hotspot_type"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.TYPES} {idefs.TYPE_HOTSPOT}"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    col = "legacyType" if tutil.SQ.version() >= c.MQR_INTRO_VERSION else "type"
    assert tutil.csv_col_is_value(csv_file, col, idefs.TYPE_HOTSPOT)


def test_findings_export(csv_file: Generator[str]) -> None:
    """test_findings_export"""
    # util.start_logging()
    cmd_csv = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file}"
    for opts in __GOOD_OPTS:
        err = e.OK
        if tutil.SQ.edition() == c.CE and sum(1 for cli_option in CE_FORBIDDEN_OPTIONS if f" {cli_option} " in f" {opts}") > 0:
            err = e.UNSUPPORTED_OPERATION
        if tutil.SQ.edition() == c.DE and f"--{opt.PORTFOLIOS}" in opts:
            err = e.UNSUPPORTED_OPERATION
        assert tutil.run_cmd(findings_export.main, f"{cmd_csv} {opts}", True) == err


def test_findings_export_long(csv_file: Generator[str]) -> None:
    """test_findings_export_long"""
    pytest.skip("Test too long")
    cmd_csv = f"{CMD} --{opt.REPORT_FILE} {csv_file}"
    for opts in __GOOD_OPTS_LONG:
        assert tutil.run_cmd(findings_export.main, f"{cmd_csv} {opts}") == e.OK


def test_issues_count_0() -> None:
    """test_issues_count_0"""
    assert issues.count(tutil.SQ) > 10000


def test_issues_count_1() -> None:
    """test_issues_count_1"""
    total = issues.count(tutil.SQ)
    assert issues.count(tutil.SQ, severities=[idefs.MQR_SEVERITY_BLOCKER]) < int(total / 3)


def test_issues_count_2() -> None:
    """test_issues_count_2"""
    total = issues.count(tutil.SQ)
    assert issues.count(tutil.SQ, types=[idefs.TYPE_VULN]) < int(total / 10)


def test_issues_count_3() -> None:
    """test_issues_count"""
    assert issues.count(tutil.SQ, createdBefore="1970-01-08") == 0


def test_search_issues_by_project() -> None:
    """test_search_issues_by_project"""
    nb_issues = len(issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.LIVE_PROJECT, search_findings=True))
    assert 100 <= nb_issues <= 3700
    nb_issues = len(issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.LIVE_PROJECT, params={"resolved": "false"}))
    assert nb_issues < 1800
    nb_issues = len(issues.search_by_project(endpoint=tutil.SQ, project_key=None))
    assert nb_issues > 3500


def test_search_too_many_issues() -> None:
    """test_search_too_many_issues"""
    issue_list = issues.search_all(endpoint=tutil.SQ)
    assert len(issue_list) > 10000


def test_output_format_sarif(sarif_file: Generator[str]) -> None:
    """test_output_format_sarif"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {sarif_file} -{opt.KEY_REGEXP_SHORT} {tutil.LIVE_PROJECT}"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    with open(sarif_file, encoding="utf-8") as fh:
        sarif_json = json.loads(fh.read())
    assert sarif_json["$schema"] == "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0-rtm.4.json"
    run = sarif_json["runs"][0]
    assert run["tool"]["driver"]["name"] == "SonarQube"
    type_for_issue = "legacyType" if tutil.SQ.version() >= c.MQR_INTRO_VERSION else "type"
    for issue in run["results"]:
        print(f"{utilities.json_dump(issue)}")
        for k in "message", "locations", "ruleId", "level":
            assert k in issue
        loc = issue["locations"][0]["physicalLocation"]
        assert "region" in loc
        assert "uri" in loc["artifactLocation"]
        for k in "startLine", "endLine", "startColumn", "endColumn":
            assert k in loc["region"]
        for k in "creationDate", "key", "projectKey", "updateDate":
            assert k in issue["properties"]
        assert "impacts" in issue["properties"]
        assert "effort" in issue["properties"] or issue["properties"][type_for_issue] == idefs.TYPE_HOTSPOT
        assert "language" in issue["properties"] or issue["ruleId"].startswith("external")
        assert issue["level"] in ("warning", "error")


def test_output_format_json(json_file: Generator[str]) -> None:
    """test_output_format_json"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} -{opt.KEY_REGEXP_SHORT} {tutil.LIVE_PROJECT}"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    with open(json_file, encoding="utf-8") as fh:
        json_data = json.loads(fh.read())
    type_for_issue = "legacyType" if tutil.SQ.version() >= c.MQR_INTRO_VERSION else "type"
    for issue in json_data:
        print(f"{json.dumps(issue)}")
        for k in "creationDate", "file", "key", "message", "projectKey", "rule", "updateDate":
            assert k in issue
        assert "impacts" in issue
        assert "effort" in issue or issue[type_for_issue] == idefs.TYPE_HOTSPOT
        assert "language" in issue or issue["rule"].startswith("external")
        # Some issues have no author so we cannot expect the below assertion to succeed all the time
        # assert issue["status"] in ("FIXED", "CLOSED") or "author" in issue


def test_output_format_csv(csv_file: Generator[str]) -> None:
    """test_output_format_csv"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} -{opt.KEY_REGEXP_SHORT} {tutil.LIVE_PROJECT}"
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    assert tutil.csv_cols_present(
        csv_file, "creationDate", "effort", "file", "key", "line", "language", "author", "message", "projectKey", "rule", "updateDate"
    )


def test_output_format_branch(csv_file: Generator[str]) -> None:
    """test_output_format_branch"""

    for br in "develop", "master,develop":
        br_list = utilities.csv_to_list(br)
        regexp = utilities.csv_to_regexp(br)
        cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.KEY_REGEXP} {tutil.LIVE_PROJECT} --{opt.BRANCH_REGEXP} {regexp}"
        if tutil.SQ.edition() == c.CE:
            assert tutil.run_cmd(findings_export.main, cmd) == e.UNSUPPORTED_OPERATION
            continue
        assert tutil.run_cmd(findings_export.main, cmd) == e.OK
        assert tutil.csv_col_is_value(csv_file, "branch", *br_list)
        assert tutil.csv_col_is_value(csv_file, "pullRequest", "")
        assert tutil.csv_col_is_value(csv_file, "projectKey", tutil.LIVE_PROJECT)


def test_all_prs(csv_file: Generator[str]) -> None:
    """Tests that findings extport for all PRs of a project works"""
    cmd = f'{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.KEY_REGEXP} {tutil.LIVE_PROJECT} --{opt.PULL_REQUESTS} "*"'
    if tutil.SQ.edition() == c.CE:
        assert tutil.run_cmd(findings_export.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert tutil.run_cmd(findings_export.main, cmd) == e.OK
    assert tutil.csv_col_is_value(csv_file, "branch", "")
    assert tutil.csv_col_match(csv_file, "pullRequest", r"\d+")
    assert tutil.csv_col_is_value(csv_file, "projectKey", tutil.LIVE_PROJECT)


def test_one_pr(csv_file: Generator[str]) -> None:
    """Tests that findings export for a single name PR of a project works"""
    proj = projects.Project.get_object(endpoint=tutil.SQ, key=tutil.LIVE_PROJECT)
    for pr in proj.pull_requests().keys():
        cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.KEY_REGEXP} {tutil.LIVE_PROJECT} -{opt.PULL_REQUESTS_SHORT} {pr}"
        print(cmd)
        if tutil.SQ.edition() == c.CE:
            assert tutil.run_cmd(findings_export.main, cmd) == e.UNSUPPORTED_OPERATION
            break
        assert tutil.run_cmd(findings_export.main, cmd) == e.OK
        assert tutil.csv_col_is_value(csv_file, "pullRequest", pr)
        assert tutil.csv_col_is_value(csv_file, "projectKey", tutil.LIVE_PROJECT)
