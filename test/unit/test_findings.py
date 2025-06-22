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

""" sonar-findings-export tests """

import os
import sys
import csv
import json
from collections.abc import Generator
from unittest.mock import patch
import pytest

import utilities as util
import sonar.logging as log
from sonar import utilities, projects
from sonar import findings, issues
from sonar import errcodes as e
import sonar.util.constants as c

from cli import findings_export
import cli.options as opt

CMD = "sonar-findings-export.py"
SARIF_FILE = "issues.sarif"
CMD = f"{CMD} {util.SQS_OPTS}"

CE_FORBIDDEN_OPTIONS = (
    f"--{opt.APPS}",
    f"--{opt.PORTFOLIOS}",
    f"--{opt.BRANCH_REGEXP}",
    f"-{opt.BRANCH_REGEXP_SHORT}",
    f"--{opt.PULL_REQUESTS}",
    f"-{opt.PULL_REQUESTS_SHORT}",
)

if util.SQ.is_mqr_mode():
    fields = findings.CSV_EXPORT_FIELDS
    # 10.x MQR
    SECURITY_IMPACT_COL = fields.index("securityImpact")
    RELIABILITY_IMPACT_COL = fields.index("reliabilityImpact")
    MAINTAINABILITY_IMPACT_COL = fields.index("maintainabilityImpact")
    OTHER_IMPACT_COL = fields.index("otherImpact")
    TYPE_COL = fields.index("legacyType")
    SEVERITY_COL = fields.index("legacySeverity")
else:
    # 9.9
    fields = findings.LEGACY_CSV_EXPORT_FIELDS
    TYPE_COL = fields.index("type")
    SEVERITY_COL = fields.index("severity")

__GOOD_OPTS = [
    f"--{opt.FORMAT} json -{opt.KEY_REGEXP_SHORT} ({util.PROJECT_1}|{util.PROJECT_2}) -{opt.REPORT_FILE_SHORT} {util.JSON_FILE}",
    f"--{opt.CSV_SEPARATOR} ; -d --{opt.TAGS} cwe,convention",
    f"-{opt.KEY_REGEXP_SHORT} {util.PROJECT_1} -{opt.BRANCH_REGEXP_SHORT} .+",
    f"--{opt.KEY_REGEXP} training:security -{opt.BRANCH_REGEXP_SHORT} main",
    f"--{opt.USE_FINDINGS} -{opt.KEY_REGEXP_SHORT} ({util.PROJECT_1}|{util.PROJECT_2})",
    f"--{opt.APPS} -{opt.KEY_REGEXP_SHORT} APP_TEST --{opt.BRANCH_REGEXP} .+",
    f"--{opt.PORTFOLIOS} -{opt.KEY_REGEXP_SHORT} Banking -{opt.REPORT_FILE_SHORT} {util.CSV_FILE}",
    f"-{opt.KEY_REGEXP_SHORT} {util.PROJECT_1} -{opt.BRANCH_REGEXP_SHORT} .+",
    f"--{opt.STATUSES} OPEN,CLOSED --{opt.SEVERITIES} BLOCKER,CRITICAL",
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
    [f"--{opt.APPS}", f"-{opt.KEY_REGEXP_SHORT}", util.LIVE_PROJECT],
    [f"--{opt.PORTFOLIOS}", f"-{opt.KEY_REGEXP_SHORT}", util.LIVE_PROJECT],
]


def test_findings_export_sarif_explicit(json_file: Generator[str]) -> None:
    """Test SARIF export"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} --{opt.KEY_REGEXP} {util.LIVE_PROJECT} --{opt.FORMAT} sarif"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    assert util.file_contains(json_file, "schemas/json/sarif-2.1.0-rtm.4")


def test_findings_export_sarif_implicit(sarif_file: Generator[str]) -> None:
    """Test SARIF export for a single project and implicit format"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {sarif_file} --{opt.KEY_REGEXP} {util.LIVE_PROJECT} --{opt.FORMAT} sarif"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    assert util.file_contains(sarif_file, "schemas/json/sarif-2.1.0-rtm.4")


def test_wrong_filters(csv_file: Generator[str]) -> None:
    """test_wrong_filters"""
    for bad_opts in __WRONG_FILTER_OPTS:
        assert util.run_cmd(findings_export.main, f"{CMD} --{opt.REPORT_FILE} {csv_file} {bad_opts}") == e.WRONG_SEARCH_CRITERIA


def test_wrong_opts(csv_file: Generator[str]) -> None:
    """test_wrong_opts"""
    for bad_opts in __WRONG_OPTS:
        with pytest.raises(SystemExit) as e:
            with patch.object(sys, "argv", [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", csv_file] + bad_opts):
                findings_export.main()
        assert int(str(e.value)) == e.WRONG_SEARCH_CRITERIA or (
            int(str(e.value)) == e.UNSUPPORTED_OPERATION and util.SQ.edition() in (c.CE, c.DE)
        )
        assert not os.path.isfile(csv_file)


def test_findings_export_non_existing_branch() -> None:
    """test_findings_export_non_existing_branch"""
    cmd = f"{CMD} --{opt.KEY_REGEXP} training:security --{opt.BRANCH_REGEXP} non-existing-branch"
    err = e.UNSUPPORTED_OPERATION if util.SQ.edition() == c.CE else e.WRONG_SEARCH_CRITERIA
    assert util.run_cmd(findings_export.main, cmd) == err


def test_findings_filter_on_date_after(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_type"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} -{opt.KEY_REGEXP_SHORT} {util.LIVE_PROJECT} --{opt.DATE_AFTER} 2023-05-01"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        (date_col,) = util.get_cols(next(csvreader), "creationDate")
        for line in csvreader:
            assert line[date_col][:10] >= "2023-05-01"


def test_findings_filter_on_date_before(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_type"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} -{opt.KEY_REGEXP_SHORT} {util.LIVE_PROJECT} --{opt.DATE_BEFORE} 2024-05-01"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        (date_col,) = util.get_cols(next(csvreader), "creationDate")
        for line in csvreader:
            assert line[date_col][:10] <= "2024-05-01"


def test_findings_filter_on_type(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_type"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.TYPES} VULNERABILITY,BUG"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        next(csvreader)
        for line in csvreader:
            if util.SQ.is_mqr_mode():
                assert line[SECURITY_IMPACT_COL] != "" or line[RELIABILITY_IMPACT_COL] != ""
            else:
                assert line[TYPE_COL] in ("BUG", "VULNERABILITY")


def test_findings_filter_on_resolution(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_resolution"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.RESOLUTIONS} FALSE-POSITIVE,ACCEPTED,SAFE"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    if util.SQ.version() < (10, 0, 0):
        statuses = ("FALSE-POSITIVE", "WONTFIX", "SAFE")
    else:
        statuses = ("FALSE-POSITIVE", "ACCEPTED", "SAFE")
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        (status_col,) = util.get_cols(next(csvreader), "status")
        for line in csvreader:
            assert line[status_col] in statuses


def test_findings_filter_on_severity(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_severity"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.SEVERITIES} BLOCKER,CRITICAL"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        next(csvreader)
        for line in csvreader:
            if not util.SQ.is_mqr_mode():
                assert line[SEVERITY_COL] in ("BLOCKER", "CRITICAL")
            elif util.SQ.version() < (10, 7, 0):
                assert (
                    "HIGH" in line[SECURITY_IMPACT_COL:OTHER_IMPACT_COL]
                    or "MEDIUM" in line[SECURITY_IMPACT_COL:OTHER_IMPACT_COL]
                    or "HIGH(HOTSPOT)" in line[SECURITY_IMPACT_COL:OTHER_IMPACT_COL]
                )
            else:
                assert (
                    "BLOCKER" in line[SECURITY_IMPACT_COL:OTHER_IMPACT_COL]
                    or "HIGH" in line[SECURITY_IMPACT_COL:OTHER_IMPACT_COL]
                    or "HIGH(HOTSPOT)" in line[SECURITY_IMPACT_COL:OTHER_IMPACT_COL]
                )


def test_findings_filter_on_multiple_criteria(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_multiple_criteria"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.RESOLUTIONS} FALSE-POSITIVE,ACCEPTED --{opt.TYPES} BUG,CODE_SMELL"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        (status_col,) = util.get_cols(next(csvreader), "status")
        for line in csvreader:
            if util.SQ.version() < (10, 0, 0):
                assert line[status_col] in ("FALSE-POSITIVE", "WONTFIX")
            else:
                assert line[status_col] in ("FALSE-POSITIVE", "ACCEPTED")
            if util.SQ.version() >= c.MQR_INTRO_VERSION:
                assert line[MAINTAINABILITY_IMPACT_COL] != "" or line[RELIABILITY_IMPACT_COL] != ""
            else:
                assert line[TYPE_COL] in ("BUG", "CODE_SMELL")


def test_findings_filter_on_multiple_criteria_2(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_multiple_criteria_2"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.DATE_AFTER} 2020-01-10 --{opt.DATE_BEFORE} 2020-12-31 --{opt.TYPES} SECURITY_HOTSPOT"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        (date_col,) = util.get_cols(next(csvreader), "creationDate")
        for line in csvreader:
            log.info(str(line))
            if util.SQ.version() >= c.MQR_INTRO_VERSION:
                assert "HOTSPOT" in line[SECURITY_IMPACT_COL]
            else:
                assert "HOTSPOT" in line[TYPE_COL]
            assert line[date_col].split("-")[0] == "2020"

    # FIXME: findings-export ignores the branch option see https://github.com/okorach/sonar-tools/issues/1115
    # So passing a non existing branch succeeds
    # assert int(str(e.value)) == e.ERR_NO_SUCH_KEY
    # assert not os.path.isfile(testutil.CSV_FILE)


def test_findings_filter_on_multiple_criteria_3(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_multiple_criteria_3"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.STATUSES} ACCEPTED --{opt.RESOLUTIONS} FALSE-POSITIVE"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    if util.SQ.version() < (10, 0, 0):
        statuses = ("WONTFIX", "FALSE_POSITIVE", "FALSE-POSITIVE")
    else:
        statuses = ("ACCEPTED", "FALSE_POSITIVE", "FALSE-POSITIVE")
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        (status_col,) = util.get_cols(next(csvreader), "status")
        for line in csvreader:
            assert line[status_col] in statuses


def test_findings_filter_on_hotspots_multi_1(csv_file: Generator[str]) -> None:
    """test_findings_filter_on_hotspots_multi_1"""
    projs = [util.PROJECT_1, util.PROJECT_2]
    regexp = utilities.list_to_regexp(projs)
    cmd = f'{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.RESOLUTIONS} "ACKNOWLEDGED, SAFE" -{opt.KEY_REGEXP_SHORT} {regexp}'
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        status_col, proj_col = util.get_cols(next(csvreader), "status", "projectKey")
        next(csvreader)
        for line in csvreader:
            assert line[status_col] in ("ACKNOWLEDGED", "SAFE")
            assert line[proj_col] in projs


def test_findings_filter_on_lang(csv_file: Generator[str]) -> None:
    """test_findings_filter_hotspot_on_lang"""
    cmd = f'{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.LANGUAGES} java,js"'
    assert util.run_cmd(findings_export.main, cmd) == e.OK


def test_findings_export(csv_file: Generator[str]) -> None:
    """test_findings_export"""
    # util.start_logging()
    cmd_csv = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file}"
    for opts in __GOOD_OPTS:
        err = e.OK
        if util.SQ.edition() == c.CE and sum(1 for cli_option in CE_FORBIDDEN_OPTIONS if f" {cli_option} " in f" {opts}") > 0:
            err = e.UNSUPPORTED_OPERATION
        if util.SQ.edition() == c.DE and f"--{opt.PORTFOLIOS}" in opts:
            err = e.UNSUPPORTED_OPERATION
        assert util.run_cmd(findings_export.main, f"{cmd_csv} {opts}", True) == err


def test_findings_export_long(csv_file: Generator[str]) -> None:
    """test_findings_export_long"""
    cmd_csv = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file}"
    for opts in __GOOD_OPTS_LONG:
        assert util.run_cmd(findings_export.main, f"{cmd_csv} {opts}", True) == e.OK


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
    nb_issues = len(issues.search_by_project(endpoint=util.SQ, project_key=util.LIVE_PROJECT, search_findings=True))
    assert 100 <= nb_issues <= 500
    nb_issues = len(issues.search_by_project(endpoint=util.SQ, project_key=util.LIVE_PROJECT, params={"resolved": "false"}))
    assert nb_issues < 500
    nb_issues = len(issues.search_by_project(endpoint=util.SQ, project_key=None))
    assert nb_issues > 1000


def test_search_too_many_issues() -> None:
    """test_search_too_many_issues"""
    issue_list = issues.search_all(endpoint=util.SQ)
    assert len(issue_list) > 10000


def test_output_format_sarif(sarif_file: Generator[str]) -> None:
    """test_output_format_sarif"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {sarif_file} -{opt.KEY_REGEXP_SHORT} {util.LIVE_PROJECT}"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    with open(sarif_file, encoding="utf-8") as fh:
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
        if util.SQ.is_mqr_mode():
            assert "effort" in issue["properties"] or "HOTSPOT" in issue["properties"]["impacts"].get("SECURITY", "")
        else:
            assert "effort" in issue["properties"] or issue["properties"]["type"] == "SECURITY_HOTSPOT"
        assert "language" in issue["properties"] or issue["ruleId"].startswith("external")
        assert issue["level"] in ("warning", "error")


def test_output_format_json(json_file: Generator[str]) -> None:
    """test_output_format_json"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} -{opt.KEY_REGEXP_SHORT} {util.LIVE_PROJECT}"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    with open(json_file, encoding="utf-8") as fh:
        json_data = json.loads(fh.read())
    for issue in json_data:
        log.info("ISSUE = %s", json.dumps(issue))
        for k in "creationDate", "file", "key", "message", "projectKey", "rule", "updateDate":
            assert k in issue
        if util.SQ.is_mqr_mode():
            assert "impacts" in issue
            assert "effort" in issue or "HOTSPOT" in issue["impacts"].get("SECURITY", "")
        else:
            assert "type" in issue
            assert "effort" in issue or issue["type"] == "SECURITY_HOTSPOT"

        assert "language" in issue or issue["rule"].startswith("external")
        # Some issues have no author so we cannot expect the below assertion to succeed all the time
        # assert issue["status"] in ("FIXED", "CLOSED") or "author" in issue


def test_output_format_csv(csv_file: Generator[str]) -> None:
    """test_output_format_csv"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} -{opt.KEY_REGEXP_SHORT} {util.LIVE_PROJECT}"
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    with open(csv_file, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        row = next(reader)
        row[0] = row[0][2:]
        for k in "creationDate", "effort", "file", "key", "line", "language", "author", "message", "projectKey", "rule", "updateDate":
            assert k in row


def test_output_format_branch(csv_file: Generator[str]) -> None:
    """test_output_format_branch"""

    for br in "develop", "master,develop":
        br_list = utilities.csv_to_list(br)
        regexp = utilities.csv_to_regexp(br)
        cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.KEY_REGEXP} {util.LIVE_PROJECT} --{opt.BRANCH_REGEXP} {regexp}"
        if util.SQ.edition() == c.CE:
            assert util.run_cmd(findings_export.main, cmd) == e.UNSUPPORTED_OPERATION
            continue
        assert util.run_cmd(findings_export.main, cmd) == e.OK
        with open(csv_file, encoding="utf-8") as fd:
            reader = csv.reader(fd)
            proj_col, branch_col, pr_col = util.get_cols(next(reader), "projectKey", "branch", "pullRequest")
            for line in reader:
                assert line[branch_col] in br_list
                assert line[pr_col] == ""
                assert line[proj_col] == util.LIVE_PROJECT


def test_all_prs(csv_file: Generator[str]) -> None:
    """Tests that findings extport for all PRs of a project works"""
    cmd = f'{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.KEY_REGEXP} {util.LIVE_PROJECT} --{opt.PULL_REQUESTS} "*"'
    if util.SQ.edition() == c.CE:
        assert util.run_cmd(findings_export.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert util.run_cmd(findings_export.main, cmd) == e.OK
    with open(csv_file, encoding="utf-8") as fd:
        reader = csv.reader(fd)
        try:
            nbcol = len(header := next(reader))
            proj_col, branch_col, pr_col = util.get_cols(header, "projectKey", "branch", "pullRequest")
            for line in reader:
                assert len(line) == nbcol
                assert line[branch_col] == ""
                assert line[pr_col] != ""
                assert line[proj_col] == util.LIVE_PROJECT
        except StopIteration:
            pass


def test_one_pr(csv_file: Generator[str]) -> None:
    """Tests that findings extport for a single name PR of a project works"""
    proj = projects.Project.get_object(endpoint=util.SQ, key=util.LIVE_PROJECT)
    for pr in list(proj.pull_requests().keys()):
        cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.KEY_REGEXP} {util.LIVE_PROJECT} -{opt.PULL_REQUESTS_SHORT} {pr}"
        if util.SQ.edition() == c.CE:
            assert util.run_cmd(findings_export.main, cmd) == e.UNSUPPORTED_OPERATION
            break
        assert util.run_cmd(findings_export.main, cmd) == e.OK
        with open(csv_file, encoding="utf-8") as fd:
            reader = csv.reader(fd)
            try:
                nbcol = len(header := next(reader))
                proj_col, branch_col, pr_col = util.get_cols(header, "projectKey", "branch", "pullRequest")
                for line in reader:
                    assert len(line) == nbcol
                    assert line[branch_col] == ""
                    assert line[pr_col] == pr
                    assert line[proj_col] == util.LIVE_PROJECT
            except StopIteration:
                pass
