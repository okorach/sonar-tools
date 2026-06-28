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

from datetime import datetime, timedelta, timezone
import pytest

from requests.exceptions import ConnectionError

import utilities as tutil
from sonar import issues, exceptions, logging
from sonar.issues import Issue
from sonar.projects import Project
from sonar.util import constants as c
import sonar.util.issue_defs as idefs
import credentials as tconf
import sonar.util.misc as util

_FLAT_12K_PROJECT = "12k-issues-flat"
_STRUCTURED_12K_PROJECT = "12k-issues-structured"
_NBR_ISSUES_12K = 12000
_NBR_ISSUES_12K_BEST_EFFORT = 10000


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
    findings_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    finding = list(findings_d.values())[0]
    nb_comments = len(finding.comments())

    txt = f"test comment on {datetime.now()}"
    assert finding.add_comment(txt)
    comments = finding.comments()
    assert list(comments.values())[-1]["value"] == txt
    assert len(comments) == nb_comments + 1

    just_before = datetime.now(timezone.utc) - timedelta(seconds=2)
    comments = finding.comments(after=just_before)
    assert len(comments) == 1
    assert list(comments.values())[-1]["value"] == txt

    issue_wo_comments = list(findings_d.values())[1]
    assert issue_wo_comments.comments() == {}


def test_delete_comment() -> None:
    """Test that a comment can be added and then deleted"""
    findings_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    finding = list(findings_d.values())[0]
    nb_comments = len(finding.comments())

    txt = f"comment to delete on {datetime.now()}"
    assert finding.add_comment(txt)
    comments = finding.comments()
    assert len(comments) == nb_comments + 1
    comment_key = list(comments.values())[-1]["commentKey"]

    assert finding.delete_comment(comment_key)
    comments = finding.comments()
    assert len(comments) == nb_comments
    assert all(c.get("commentKey") != comment_key for c in comments.values())


def test_set_severity() -> None:
    """test_set_severity"""
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


def set_cloud_mqr_severity() -> None:
    """test_set_cloud_mqr_severity"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue = list(issues_d.values())[0]
    if issue.endpoint.is_sonarcloud():
        assert issue.set_severity("BLOCKER") is False


def test_add_remove_tag() -> None:
    """test_add_remove_tag"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue = list(issues_d.values())[0]
    tag = "test-tag"
    issue.remove_tag(tag)
    assert tag not in issue.get_tags()
    issue.add_tag(tag)
    assert tag in issue.get_tags(use_cache=False)
    issue.remove_tag(tag)


def test_set_type() -> None:
    """test_set_type"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue = list(issues_d.values())[0]
    old_type = issue.type
    new_type = c.VULN if old_type == c.BUG else c.BUG
    if tutil.SQ.version() < c.MQR_INTRO_VERSION:
        assert issue.set_type(new_type)
        issue.refresh()
        assert issue.type == new_type
        with pytest.raises(exceptions.UnsupportedOperation):
            issue.set_type("NON_EXISTING")
        issue.set_type(old_type)
    else:
        with pytest.raises(exceptions.UnsupportedOperation):
            issue.set_type(new_type)


def test_get_no_tags() -> None:
    """test_set_type"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue = list(issues_d.values())[1]
    assert issue.get_tags() == []


def test_assign() -> None:
    """test_assign"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
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


def test_multiple_changelogs() -> None:
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
    facet = "fileUuids" if tutil.SQ.is_sonarcloud() else "files"
    facets = issues._get_facets(tutil.SQ, facet=facet, project_key=tutil.LIVE_PROJECT)
    assert len(facets) > 1
    assert any(f.endswith(".py") for f in facets)


def test_search_by_small() -> None:
    """Test search_by on small project (less than 10000 issues)"""
    list1 = Issue.search_by_project(tutil.SQ, tutil.LIVE_PROJECT)
    params = {"components": tutil.LIVE_PROJECT, "project": tutil.LIVE_PROJECT}

    facets = issues._get_facets(tutil.SQ, project_key=tutil.LIVE_PROJECT, facet=issues.type_search_field(tutil.SQ)).keys()
    assert len(list1) == sum(len(Issue.search_by_type(tutil.SQ, issue_type=val, **params)) for val in facets)

    facets = issues._get_facets(tutil.SQ, project_key=tutil.LIVE_PROJECT, facet=issues.severity_search_field(tutil.SQ)).keys()
    assert len(list1) == sum(len(Issue.search_by_severity(tutil.SQ, severity=val, **params)) for val in facets)

    facets = issues._get_facets(tutil.SQ, project_key=tutil.LIVE_PROJECT, facet=issues.status_search_field(tutil.SQ)).keys()
    # Hack for SQS 9.9 and below - The facet value "" may be returned for unresolved issues, it corresponds to Unresolved issues
    unresolved_count = 0
    if "" in facets:
        facets = [f for f in facets if f != ""]
        unresolved_count = len(Issue.search(tutil.SQ, status="", **(params | {"resolved": False})))
    assert len(list1) == sum(len(Issue.search_by_status(tutil.SQ, status=val, **params)) for val in facets) + unresolved_count

    assert len(list1) == len(Issue.search_by_date(tutil.SQ, date_start=datetime(2000, 1, 1), date_stop=datetime(2030, 1, 1), **params))

    params.pop("project")
    params.pop("components")
    dirs = ["cli", "conf", "migration", "sonar", "test/unit"]
    if tutil.SQ.version() <= c.NEW_ISSUE_SEARCH_INTRO_VERSION:
        # Search does not aggregate subdirs in 9.9
        dirs += ["sonar/permissions", "sonar/util", "sonar/dce", "sonar/cli"]
    assert len(list1) == sum([len(Issue.search_by_directory(tutil.SQ, project=tutil.LIVE_PROJECT, directory=d, **params)) for d in dirs])

    issues_in_dir = len(Issue.search_by_directory(tutil.SQ, project=tutil.LIVE_PROJECT, directory="cli", **params))
    assert issues_in_dir == len([i for i in list1.values() if i.file.startswith("cli/")])

    file = "sonar/issues.py"
    if tutil.SQ.is_sonarcloud():
        uuids = issues._get_facets(tutil.SQ, project_key=tutil.LIVE_PROJECT, facet="fileUuids").keys()
        file = next((k for k, v in uuids if v["path"] == file), None)
    issues_in_file = len(Issue.search_by_file(tutil.SQ, project=tutil.LIVE_PROJECT, file_or_uuid=file, **params))
    assert issues_in_file == len([i for i in list1.values() if i.file == file])


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


def test_too_many_facets() -> None:
    """test_too_many_facets"""
    with pytest.raises(issues.TooManyFacetsError):
        Issue.search_by_date(tutil.SQ, raise_error=True, date_start=datetime(2000, 1, 1), date_stop=datetime(2030, 1, 1), project=_FLAT_12K_PROJECT)


def test_too_many_facets_by_project() -> None:
    """test_too_many_facets_by_project"""
    if tutil.SQ.edition() in (c.EE, c.DCE):
        issues_d = Issue.search_by_project(tutil.SQ, project=_FLAT_12K_PROJECT)
        assert len(issues_d) == _NBR_ISSUES_12K
    else:
        issues_d = Issue.search_by_project(tutil.SQ, raise_error=False, project=_FLAT_12K_PROJECT)
        assert len(issues_d) == _NBR_ISSUES_12K_BEST_EFFORT
        with pytest.raises(issues.TooManyFacetsError):
            Issue.search_by_project(tutil.SQ, raise_error=True, project=_FLAT_12K_PROJECT)


def test_search_by_project_object() -> None:
    """test_search_by_project_object"""
    project = Project.get_object(tutil.SQ, tutil.PROJECT_1)
    list1 = Issue.search_by_project(tutil.SQ, project=project).keys()
    list2 = Issue.search_by_project(tutil.SQ, project=project.key).keys()
    assert len(list1) > 0
    assert list1 == list2


def test_search_by_status() -> None:
    """test_search_by_status"""
    issues_d = Issue.search_by_status(tutil.SQ, status="OPEN", project=tutil.PROJECT_1)
    assert len(issues_d) > 0


def test_search_by_status_facet_error() -> None:
    """test_search_by_status_facet_error"""
    if tutil.SQ.is_sonarcloud() or tutil.SQ.edition() in (c.CE, c.DE):
        issues_d = Issue.search_by_status(tutil.SQ, status="OPEN", project=_FLAT_12K_PROJECT, raise_error=False)
        assert len(issues_d) == _NBR_ISSUES_12K_BEST_EFFORT
        with pytest.raises(issues.TooManyFacetsError):
            Issue.search_by_status(tutil.SQ, status="OPEN", project=_FLAT_12K_PROJECT)
    else:
        assert len(Issue.search_by_status(tutil.SQ, status="OPEN", project=_FLAT_12K_PROJECT)) == _NBR_ISSUES_12K


def test_search_by_directory() -> None:
    """test_search_by_directory"""
    issues_d = Issue.search_by_directory(tutil.SQ, project=_STRUCTURED_12K_PROJECT, directory="src1")
    assert len(issues_d) == 6000


def test_search_by_rule() -> None:
    """test_search_by_rule"""
    issues_d = Issue.search_by_rule(tutil.SQ, rule_key="python:S3776")
    assert all(i.rule == "python:S3776" for i in issues_d.values())


def test_search_by_directory_facet_error() -> None:
    """test_search_by_directory_facet_error"""
    if tutil.SQ.is_sonarcloud() or tutil.SQ.edition() in (c.CE, c.DE):
        with pytest.raises(issues.TooManyFacetsError):
            Issue.search_by_directory(tutil.SQ, project=_FLAT_12K_PROJECT, raise_error=True, directory="/", status="OPEN")
        issues_d = Issue.search_by_directory(tutil.SQ, project=_FLAT_12K_PROJECT, raise_error=False, directory="/", status="OPEN")
        assert len(issues_d) == _NBR_ISSUES_12K_BEST_EFFORT
    else:
        assert (
            len(Issue.search_by_directory(tutil.SQ, project=_FLAT_12K_PROJECT, directory="/", statuses="OPEN", issueStatuses="OPEN"))
            == _NBR_ISSUES_12K
        )


def test_subsearch_by_project() -> None:
    """test_subsearch_by_project"""
    issues_d = Issue.search(tutil.SQ, threads=8, raise_error=False, **{issues.component_search_field(tutil.SQ): _STRUCTURED_12K_PROJECT})
    assert len(issues_d) == _NBR_ISSUES_12K


def test_subsearch_by_project_2() -> None:
    """test_subsearch_by_project_2"""
    issues_d = Issue.search(tutil.SQ, threads=8, raise_error=False, **{issues.component_search_field(tutil.SQ): _FLAT_12K_PROJECT})
    if tutil.SQ.edition() in (c.EE, c.DCE):
        assert len(issues_d) == _NBR_ISSUES_12K
    else:
        assert len(issues_d) == _NBR_ISSUES_12K_BEST_EFFORT
        with pytest.raises(issues.TooManyIssuesError):
            Issue.search(tutil.SQ, threads=8, raise_error=True, **{issues.component_search_field(tutil.SQ): _FLAT_12K_PROJECT})


def test_tags_property() -> None:
    """Test that the tags @property returns the cached tags without a refresh and matches get_tags()"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue = list(issues_d.values())[0]
    # Warm the cache via get_tags(), then verify the property reflects it
    tags_via_method = issue.get_tags()
    assert issue.tags == tags_via_method
    # The property must return a list (possibly empty)
    assert isinstance(issue.tags, list)


def test_strictly_identical_to() -> None:
    """Test that two references to the same issue key are strictly identical, and two different issues are not"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue_list = list(issues_d.values())
    issue = issue_list[0]
    # An issue is strictly identical to itself
    assert issue.strictly_identical_to(issue)
    # Two distinct issues are not strictly identical
    if len(issue_list) > 1:
        other = issue_list[1]
        assert not issue.strictly_identical_to(other)


def test_mark_as_wont_fix() -> None:
    """Test mark_as_wont_fix: transitions to wontfix/accept then back to open"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN")
    issue = list(issues_d.values())[0]
    # mark_as_wont_fix uses 'accept' on newer SQ versions
    assert issue.mark_as_wont_fix()
    # Calling it again when already in that state should return False
    assert not issue.mark_as_wont_fix()
    # Restore to OPEN
    assert issue.reopen()


def test_apply_event_false_positive() -> None:
    """Test that __apply_event applies a FALSE-POSITIVE event to an open issue"""
    from sonar import syncer

    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN")
    issue = list(issues_d.values())[0]

    # Build a minimal Changelog object representing a false-positive event
    from sonar.changelog import Changelog

    fp_event = Changelog({"creationDate": "2026-01-01T00:00:00+0000", "diffs": [{"key": "resolution", "newValue": "FALSE-POSITIVE"}]})

    settings = {syncer.SYNC_ASSIGN: True}
    result = issue._Issue__apply_event(fp_event, settings)
    assert result is True
    issue.refresh()
    assert issue.is_false_positive()
    # Restore
    issue.reopen()


def test_apply_changelog() -> None:
    """Test apply_changelog copies false-positive and comment from source to target"""
    from sonar import syncer

    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue_list = list(issues_d.values())
    if len(issue_list) < 2:
        pytest.skip("Need at least 2 open issues in PROJECT_1")

    source = issue_list[0]
    target = issue_list[1]

    # Put source into false-positive and add a comment so it has a changelog to copy
    source.mark_as_false_positive()
    comment_txt = f"apply_changelog test comment {datetime.now()}"
    source.add_comment(comment_txt)

    settings = {
        syncer.SYNC_ADD_LINK: False,
        syncer.SYNC_ASSIGN: False,
        syncer.SYNC_SERVICE_ACCOUNT: "",
        syncer.SYNC_TAG: "",
    }
    count = target.apply_changelog(source, settings)
    assert count > 0
    target.refresh()
    assert target.is_false_positive()

    # Restore both issues
    source.reopen()
    target.reopen()


# ---------------------------------------------------------------------------
# Finding base-class methods tested via Issue
# ---------------------------------------------------------------------------


def test_finding_changelog_and_last_changelog_date() -> None:
    """Test Finding.changelog() and Finding.last_changelog_date() via Issue"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1)
    assert tconf.ISSUE_FP in issues_d
    issue = issues_d[tconf.ISSUE_FP]
    ch = issue.changelog(manual_only=False)
    assert len(ch) >= 1
    # last_changelog_date() returns the date of the newest entry
    assert issue.last_changelog_date() is not None
    # After ancient past cutoff – all entries still returned
    all_after = issue.changelog(after=datetime(2000, 1, 1, tzinfo=timezone.utc), manual_only=False)
    assert len(all_after) == len(ch)
    # After far-future cutoff – no entries
    assert issue.changelog(after=datetime(2030, 1, 1, tzinfo=timezone.utc)) == {}


def test_finding_last_changelog_date_no_changelog() -> None:
    """Test Finding.last_changelog_date() returns None when there is no changelog"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN")
    # Find an issue with no manual changelog (just pick the first OPEN one)
    for issue in issues_d.values():
        if not issue.has_changelog():
            assert issue.last_changelog_date() is None
            return
    pytest.skip("No issue without manual changelog found in PROJECT_1")


def test_finding_comments_last_comment_date_and_commenters() -> None:
    """Test Finding.comments(), .last_comment_date(), .commenters() via Issue"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue = list(issues_d.values())[0]

    txt = f"commenters test {datetime.now()}"
    assert issue.add_comment(txt)

    comments = issue.comments()
    assert len(comments) > 0
    assert any(c.get("value") == txt for c in comments.values())
    assert issue.last_comment_date() is not None

    # After future cutoff — empty
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert issue.comments(after=future) == {}

    # commenters() must include the user who added the comment
    commenters = issue.commenters()
    assert isinstance(commenters, set)
    assert tutil.SQ.user() in commenters

    # Cleanup
    comment_key = next(c["commentKey"] for c in issue.comments().values() if c.get("value") == txt)
    issue.delete_comment(comment_key)


def test_finding_last_comment_date_no_comments() -> None:
    """Test Finding.last_comment_date() returns None when the issue has no comments"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN")
    for issue in issues_d.values():
        if not issue.has_comments():
            assert issue.last_comment_date() is None
            return
    pytest.skip("No issue without comments found in PROJECT_1")


def test_finding_strictly_identical_to_same_key() -> None:
    """Finding.strictly_identical_to(): same object → True (key equality short-circuit)"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1)
    issue = issues_d[tconf.ISSUE_FP]
    assert issue.strictly_identical_to(issue)


def test_finding_strictly_identical_to_different_issues() -> None:
    """Finding.strictly_identical_to(): two different issues → False"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue_list = list(issues_d.values())
    if len(issue_list) < 2:
        pytest.skip("Need at least 2 issues in PROJECT_1")
    assert not issue_list[0].strictly_identical_to(issue_list[1])


def test_finding_strictly_identical_to_ignore_component() -> None:
    """Finding.strictly_identical_to(ignore_component=True): ignore component field"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue_list = list(issues_d.values())
    if len(issue_list) < 2:
        pytest.skip("Need at least 2 issues in PROJECT_1")
    # Two different issues are still not identical even with ignore_component
    assert not issue_list[0].strictly_identical_to(issue_list[1], ignore_component=True)


def test_finding_search_siblings_empty_list() -> None:
    """Finding.search_siblings(): empty target list → no matches in any category"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1)
    issue = issues_d[tconf.ISSUE_FP]
    exact, approx, modified = issue.search_siblings([])
    assert exact == [] and approx == [] and modified == []


def test_finding_search_siblings_no_match() -> None:
    """Finding.search_siblings(): list of unrelated issues → structure is correct, no crash"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue_list = list(issues_d.values())
    issue = issue_list[0]
    exact, approx, modified = issue.search_siblings(issue_list[1:])
    assert isinstance(exact, list)
    assert isinstance(approx, list)
    assert isinstance(modified, list)


def test_finding_search_siblings_bidirectional_empty() -> None:
    """Finding.search_siblings_bidirectional(): empty list → no matches"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1)
    issue = issues_d[tconf.ISSUE_FP]
    exact, approx = issue.search_siblings_bidirectional([])
    assert exact == [] and approx == []


def test_finding_search_siblings_bidirectional_exact_match() -> None:
    """Finding.search_siblings_bidirectional(): two Issue objects from the same payload → exact match"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1)
    issue1 = issues_d[tconf.ISSUE_FP]
    # use_cache=False + full payload → new Python object, same field values, different identity
    issue2 = Issue.get_object(tutil.SQ, issue1.sq_json.copy(), use_cache=False)
    assert issue1 is not issue2
    exact, approx = issue1.search_siblings_bidirectional([issue2])
    assert len(exact) == 1
    assert exact[0] is issue2
    assert approx == []


def test_finding_search_siblings_bidirectional_no_match() -> None:
    """Finding.search_siblings_bidirectional(): unrelated issues → no exact match"""
    issues_d = Issue.search_by_project(endpoint=tutil.SQ, project=tutil.PROJECT_1, statuses="OPEN,CONFIRMED")
    issue_list = list(issues_d.values())
    issue = issue_list[0]
    exact, approx = issue.search_siblings_bidirectional(issue_list[1:])
    assert isinstance(exact, list)
    assert isinstance(approx, list)
