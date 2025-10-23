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

"""Test of the issues module and class, as well as changelog"""

from datetime import datetime, timedelta
import pytest

from requests.exceptions import ConnectionError

import utilities as tutil
from sonar import issues, exceptions, logging
from sonar import utilities as util
from sonar.util import constants as c
import credentials as tconf


def test_issue() -> None:
    """Test issues"""
    issue_key = tconf.ISSUE_FP
    issue_key_accepted = tconf.ISSUE_ACCEPTED
    issues_d = issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.PROJECT_1)

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
    assert issue.api_params(c.LIST) == {"issues": issue_key}
    assert issue.api_params(c.SET_TAGS) == {"issue": issue_key}
    assert issue.api_params(c.GET_TAGS) == {"issues": issue_key}

    assert issue_key_accepted in issues_d
    issue2 = issues_d[issue_key_accepted]
    assert not issue.almost_identical_to(issue2)

    assert f"{issue}".startswith(f"Key: {issue.key} - Type:")


def test_add_comments() -> None:
    """Test issue comments manipulations"""
    issues_d = issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.PROJECT_1, params={"statuses": "OPEN"})
    issue = list(issues_d.values())[0]
    comment = f"NOW is {str(datetime.now())}"
    assert issue.add_comment(comment)
    issue.refresh()
    issue_comments = [cmt["value"] for cmt in issue.comments().values()]
    assert comment in issue_comments
    issue_wo_comments = list(issues_d.values())[1]
    assert issue_wo_comments.comments() == {}


def test_set_severity() -> None:
    """Test issue severity"""
    issues_d = issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.PROJECT_1, params={"statuses": "OPEN"})
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
        issue.set_mqr_severity("MAINTAINABILITY", "NON_EXISTING")
    with pytest.raises(exceptions.SonarException):
        issue.set_mqr_severity("NON_EXISTING", "HIGH")
    for k, v in old_impacts.items():
        issue.set_mqr_severity(k, v)

    tutil.SQ.set_mqr_mode(is_mqr)


def test_add_remove_tag() -> None:
    """test_add_remove_tag"""
    issues_d = issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.PROJECT_1, params={"statuses": "OPEN"})
    issue = list(issues_d.values())[0]
    tag = "test-tag"
    issue.remove_tag(tag)
    assert tag not in issue.get_tags()
    issue.add_tag(tag)
    assert tag in issue.get_tags(use_cache=False)
    issue.remove_tag(tag)


def test_set_type() -> None:
    """test_set_type"""
    issues_d = issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.PROJECT_1, params={"statuses": "OPEN"})
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
    issues_d = issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.PROJECT_1, params={"statuses": "OPEN"})
    issue = list(issues_d.values())[0]
    old_assignee = issue.assignee
    new_assignee = "olivier" if old_assignee is None or old_assignee != "olivier" else "michal"
    assert issue.assign(new_assignee)
    issue.refresh()
    assert issue.assignee == new_assignee
    issue.assign("michal")


def test_changelog() -> None:
    """Test changelog"""
    issues_d = issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.PROJECT_1)
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
    assert changelog.author() == "admin"


def test_multiple_changelogs():
    """test_multiple_changelogs"""
    issue_key = tconf.ISSUE_FP
    issues_d = issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.PROJECT_1)
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
    issues_d = issues.search_by_project(endpoint=tutil.TEST_SQ, project_key=tutil.PROJECT_1)
    issue = list(issues_d.values())[0]
    url = tutil.TEST_SQ.local_url
    tutil.TEST_SQ.local_url = "http://localhost:3337"
    with pytest.raises(ConnectionError):
        issue.add_comment("Won't work")
    with pytest.raises(ConnectionError):
        issue.assign("admin")
    tutil.TEST_SQ.local_url = url


def test_transitions() -> None:
    """test_transitions"""
    issues_d = issues.search_by_project(endpoint=tutil.SQ, project_key=tutil.PROJECT_1, params={"statuses": "OPEN"})
    issue = list(issues_d.values())[0]

    assert issue.confirm()
    with pytest.raises(exceptions.UnsupportedOperation):
        issue.confirm()
    assert issue.unconfirm()
    with pytest.raises(exceptions.UnsupportedOperation):
        issue.unconfirm()

    assert issue.resolve_as_fixed()
    with pytest.raises(exceptions.UnsupportedOperation):
        issue.resolve_as_fixed()
    assert issue.reopen()
    with pytest.raises(exceptions.UnsupportedOperation):
        issue.reopen()

    if tutil.SQ.version() >= c.ACCEPT_INTRO_VERSION:
        assert issue.accept()
        with pytest.raises(exceptions.UnsupportedOperation):
            issue.accept()
    else:
        assert issue.mark_as_wont_fix()
        with pytest.raises(exceptions.UnsupportedOperation):
            issue.mark_as_wont_fix()
    assert issue.reopen()
    with pytest.raises(exceptions.UnsupportedOperation):
        issue.reopen()

    assert issue.mark_as_false_positive()
    with pytest.raises(exceptions.UnsupportedOperation):
        issue.mark_as_false_positive()
    assert issue.reopen()
    with pytest.raises(exceptions.UnsupportedOperation):
        issue.reopen()


def test_search_first() -> None:
    """test_search_first"""
    assert issues.search_first(tutil.SQ, components="non-existing-project-key") is None


def test_get_facets() -> None:
    """test_get_facets"""
    facets = issues._get_facets(tutil.SQ, project_key=tutil.LIVE_PROJECT)
    assert len(facets["directories"]) > 1


def test_search_by_small() -> None:
    """Test search_by on small project (less than 10000 issues)"""
    list1 = issues.search_by_project(tutil.SQ, tutil.LIVE_PROJECT)
    params = {"components": tutil.LIVE_PROJECT, "project": tutil.LIVE_PROJECT}
    assert list1 == issues.search_by_type(tutil.SQ, params)
    assert list1 == issues.search_by_severity(tutil.SQ, params)
    assert list1 == issues.search_by_date(tutil.SQ, params)
    assert list1 == issues.search_by_directory(tutil.SQ, params)
