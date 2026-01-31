#
# sonar-tools tests
# Copyright (C) 2024-2026 Olivier Korach
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

"""Test of the issues module and class, as well as changelog"""

from datetime import datetime, timedelta
import pytest

from requests.exceptions import ConnectionError

import utilities as tutil
from sonar import issues, exceptions, logging
from sonar.issues import Issue
from sonar.util import constants as c
import sonar.util.issue_defs as idefs
import credentials as tconf
import sonar.util.misc as util
from sonar.api.manager import ApiOperation as Oper


def test_issue() -> None:
    """Test issues"""
    issue_key = tconf.ISSUE_FP
    issue_key_accepted = tconf.ISSUE_ACCEPTED
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1)

    issue = issues_d[issue_key]
    assert not issue.is_security_issue()
    assert not issue.is_hotspot()
    assert not issue.is_accepted()
    assert issue.is_code_smell()
    assert not issue.is_bug()
    assert not issue.is_closed()
    assert not issue.is_vulnerability()
    assert not issue.is_wont_fix()
    assert issue.is_false_positive()
    assert issue.refresh()

    assert issue_key_accepted in issues_d
    issue2 = issues_d[issue_key_accepted]
    assert not issue.almost_identical_to(issue2)

    assert f"{issue}".startswith(f"Key: {issue.key} - Type:")


def test_add_comments() -> None:
    """Test issue comments manipulations"""
    findings_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN")
    finding = list(findings_d.values())[0]
    nb_comments = len(finding.comments())

    txt = f"test comment on {datetime.now()}"
    assert finding.add_comment(txt)
    comments = finding.comments()
    assert list(comments.values())[-1]["value"] == txt
    assert len(comments) == nb_comments + 1

    just_before = datetime.now().astimezone() - timedelta(seconds=2)
    comments = finding.comments(after=just_before)
    assert len(comments) == 1
    assert list(comments.values())[-1]["value"] == txt

    issue_wo_comments = list(findings_d.values())[1]
    assert issue_wo_comments.comments() == {}


def test_set_severity() -> None:
    """Test issue severity"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN")
    issue = list(issues_d.values())[0]
    is_mqr = tutil.SQ.is_mqr_mode()
    old_sev = issue.severity
    new_sev = "MINOR" if old_sev == "CRITICAL" else "CRITICAL"
    old_impacts = issue.impacts
    new_impacts = {k: "HIGH" if v == "BLOCKER" else "BLOCKER" for k, v in old_impacts.items()}

    tutil.SQ.set_mqr_mode(False)

    assert issue.set_severity(new_sev)
    issue.refresh()
    assert issue.severity == new_sev
    with pytest.raises(exceptions.UnsupportedOperation):
        issue.set_severity("NON_EXISTING")
    issue.set_severity(old_sev)

    assert not any(issue.set_mqr_severity(k, v) for k, v in new_impacts.items())
    issue.refresh()
    assert issue.impacts == old_impacts

    if tutil.SQ.version() < c.MQR_INTRO_VERSION:
        return

    tutil.SQ.set_mqr_mode(True)

    assert not issue.set_severity(new_sev)
    issue.refresh()
    assert issue.severity == old_sev

    assert all(issue.set_mqr_severity(k, v) for k, v in new_impacts.items())
    issue.refresh()
    assert issue.impacts == new_impacts
    with pytest.raises(exceptions.UnsupportedOperation):
        issue.set_mqr_severity(idefs.QUALITY_MAINTAINABILITY, "NON_EXISTING")
    with pytest.raises(exceptions.SonarException):
        issue.set_mqr_severity("NON_EXISTING", "HIGH")
    for k, v in old_impacts.items():
        issue.set_mqr_severity(k, v)

    tutil.SQ.set_mqr_mode(is_mqr)


def test_add_remove_tag() -> None:
    """test_add_remove_tag"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN")
    issue = list(issues_d.values())[0]
    tag = "test-tag"
    issue.remove_tag(tag)
    assert tag not in issue.get_tags()
    issue.add_tag(tag)
    assert tag in issue.get_tags(use_cache=False)
    issue.remove_tag(tag)


def test_set_type() -> None:
    """test_set_type"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN")
    issue = list(issues_d.values())[0]
    old_type = issue.type
    new_type = c.VULN if old_type == c.BUG else c.BUG
    if tutil.SQ.is_mqr_mode():
        with pytest.raises(exceptions.UnsupportedOperation):
            issue.set_type(new_type)
    else:
        assert issue.set_type(new_type)
        issue.refresh()
        assert issue.type == new_type
        with pytest.raises(exceptions.UnsupportedOperation):
            issue.set_type("NON_EXISTING")
        issue.set_type(old_type)


def test_assign() -> None:
    """test_assign"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN")
    issue = list(issues_d.values())[0]
    old_assignee = issue.assignee
    new_assignee = "olivier" if old_assignee is None or old_assignee != "olivier" else "michal"
    assert issue.assign(new_assignee)
    issue.refresh()
    assert issue.assignee == new_assignee
    issue.assign("michal")


def test_changelog() -> None:
    """Test changelog"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1)
    issue_key = tconf.ISSUE_FP
    assert issue_key in issues_d
    issue = issues_d[issue_key]
    assert issue.key == issue_key
    assert str(issue) == f"Issue key '{issue_key}'"
    assert issue.is_false_positive()
    changelog_l = list(issue.changelog(manual_only=False).values())
    assert len(changelog_l) == tconf.ISSUE_FP_NBR_CHANGELOGS
    changelog = changelog_l[-1]
    assert changelog.is_resolve_as_fp()
    assert not changelog.is_closed()
    assert not changelog.is_resolve_as_wf()
    assert not changelog.is_confirm()
    assert not changelog.is_unconfirm()
    assert not changelog.is_reopen()
    assert not changelog.is_mark_as_safe()
    assert not changelog.is_mark_as_to_review()
    assert not changelog.is_mark_as_fixed()
    assert not changelog.is_mark_as_acknowledged()
    assert not changelog.is_change_severity()
    assert changelog.new_severity() == (None, None)
    assert not changelog.is_change_type()
    assert changelog.new_type() is None
    assert not changelog.is_technical_change()
    assert not changelog.is_assignment()
    assert changelog.assignee() is None
    assert changelog.assignee(False) is None
    delta = timedelta(days=1)
    date_change = tconf.ISSUE_FP_CHANGELOG_DATE
    assert date_change <= changelog.date_time().replace(tzinfo=None) < date_change + delta
    assert changelog.author() == tconf.ADMIN_USER


def test_multiple_changelogs():
    """test_multiple_changelogs"""
    issue_key = tconf.ISSUE_FP
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1)
    assert issue_key in issues_d
    issue = issues_d[issue_key]
    state_list = ("ACCEPT", "CONFIRM", "UNCONFIRM", "FP", "REOPEN", "SEVERITY", "ASSIGN", "UNASSIGN", "SEVERITY")
    results = dict.fromkeys(state_list, False)
    for cl in issue.changelog().values():
        (t, _) = cl.changelog_type()
        assert t is not None
        results["ACCEPT"] |= cl.is_resolve_as_accept() or cl.is_resolve_as_wf()
        results["CONFIRM"] |= cl.is_confirm()
        results["UNCONFIRM"] |= cl.is_unconfirm()
        if cl.is_resolve_as_fp():
            results["FP"] = True
            assert cl.previous_state() in ("OPEN", "REOPENED")
        if cl.is_assignment():
            results["ASSIGN"] = True
            assert len(cl.assignee()) > 0
        results["UNASSIGN"] |= cl.is_unassign()
        results["SEVERITY"] |= cl.is_change_severity()
        results["REOPEN"] |= cl.is_reopen()
    for s in state_list:
        if s != "REOPEN" or (s == "REOPEN" and tutil.SQ.version() < (10, 0, 0)):
            logging.debug("Checking that changelog %s was found", s)
            assert results[s]


def test_request_error() -> None:
    """test_request_error"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1)
    issue = list(issues_d.values())[0]
    url = tutil.SQ.local_url
    tutil.SQ.local_url = "http://localhost:3337"
    with pytest.raises(ConnectionError):
        issue.add_comment("Won't work")
    with pytest.raises(ConnectionError):
        issue.assign(tconf.ADMIN_USER)
    tutil.SQ.local_url = url


def test_transitions() -> None:
    """test_transitions"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN")
    issue = list(issues_d.values())[0]

    assert issue.confirm()
    assert not issue.confirm()
    assert issue.unconfirm()
    assert not issue.unconfirm()

    assert issue.resolve_as_fixed()
    assert not issue.resolve_as_fixed()
    assert issue.reopen()
    assert not issue.reopen()

    if tutil.SQ.version() >= c.ACCEPT_INTRO_VERSION:
        assert issue.accept()
        assert not issue.accept()
    else:
        assert issue.mark_as_wont_fix()
        assert not issue.mark_as_wont_fix()
    assert issue.reopen()
    assert not issue.reopen()

    assert issue.mark_as_false_positive()
    assert not issue.mark_as_false_positive()
    assert issue.reopen()
    assert not issue.reopen()


def test_search_first() -> None:
    """test_search_first"""
    assert Issue.search_first(tutil.SQ, components="non-existing-project-key") is None


def test_get_facets() -> None:
    """test_get_facets"""
    facets = issues._get_facets(tutil.SQ, project_key=tutil.LIVE_PROJECT)
    assert len(facets) > 1
    assert not any(f.endswith(".py") for f in facets)
    facets = issues._get_facets(tutil.SQ, facet="files", project_key=tutil.LIVE_PROJECT)
    assert len(facets) > 1
    assert any(f.endswith(".py") for f in facets)


def test_search_by_small() -> None:
    """Test search_by on small project (less than 10000 issues)"""
    list1 = Issue.search_by_project(tutil.SQ, tutil.LIVE_PROJECT)
    params = {"components": tutil.LIVE_PROJECT, "project": tutil.LIVE_PROJECT}

    type_list = idefs.STD_TYPES if tutil.SQ.version() < c.MQR_INTRO_VERSION else idefs.MQR_QUALITIES
    assert len(list1) == sum(len(Issue.search_by_type(tutil.SQ, issue_type=i_type, **params)) for i_type in type_list)

    sev_list = idefs.STD_SEVERITIES if tutil.SQ.version() < c.MQR_INTRO_VERSION else idefs.MQR_SEVERITIES
    assert len(list1) == sum(len(Issue.search_by_severity(tutil.SQ, severity=i_severity, **params)) for i_severity in sev_list)
    assert len(list1) == len(Issue.search_by_date(tutil.SQ, date_start=datetime(2000, 1, 1), date_stop=datetime(2030, 1, 1), **params))

    params.pop("project")
    params.pop("components")
    dirs = ["cli", "conf", "migration", "sonar", "test/gen"]
    if tutil.SQ.version() <= c.NEW_ISSUE_SEARCH_INTRO_VERSION:
        # Search does not aggregate subdirs in 9.9
        dirs += ["sonar/permissions", "sonar/util", "sonar/dce", "sonar/cli"]
    assert len(list1) == sum([len(Issue.search_by_directory(tutil.SQ, project=tutil.LIVE_PROJECT, directory=dir, **params)) for dir in dirs])
    assert len(list1) > len(Issue.search_by_file(tutil.SQ, project=tutil.LIVE_PROJECT, file="sonar/issues.py", **params))


def test_changelog_after() -> None:
    """test_changelog_after"""
    issue = Issue.search_by_project(tutil.SQ, tutil.PROJECT_1)[tconf.ISSUE_ACCEPTED]
    after = util.add_tz(datetime(2024, 1, 1))
    changelog = issue.changelog(after=after)
    assert all(c.date_time() >= after for c in changelog.values())


def test_comments_after() -> None:
    """test_comments_after"""
    issue = Issue.search_by_project(tutil.SQ, tutil.PROJECT_1)[tconf.ISSUE_ACCEPTED]
    after = util.add_tz(datetime(2024, 1, 1))
    comments = issue.comments(after=after)
    assert all(c["date"] >= after for c in comments.values())
