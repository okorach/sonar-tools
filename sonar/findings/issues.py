#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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

import datetime
import json
import re
from queue import Queue
from threading import Thread
import requests.utils

from sonar.projects import projects
from sonar import users, syncer
from sonar.findings import findings, changelog
import sonar.utilities as util

API_SET_TAGS = "issues/set_tags"
API_SET_TYPE = "issues/set_type"

SEARCH_CRITERIAS = (
    "componentKeys",
    "types",
    "severities",
    "createdAfter",
    "createdBefore",
    "createdInLast",
    "createdAt",
    "branch",
    "pullRequest",
    "statuses",
    "tags",
    "inNewCodePeriod",
    "sinceLeakPeriod",
    "p",
    "page",
    "facets",
    "onComponentOnly",
    "s",
    "timeZone",
    "cwe",
    "owaspTop10",
    "owaspTop10-21",
    "sansTop25",
    "sonarsourceSecurity",
    "additionalFields",
    "asc",
    "assigned",
    "assignees",
    "author",
    "issues",
    "languages",
    "resolutions",
    "resolved",
    "rules",
    "scopes",
)

TYPES = ("BUG", "VULNERABILITY", "CODE_SMELL")
SEVERITIES = ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO")
STATUSES = ("OPEN", "CONFIRMED", "REOPENED", "RESOLVED", "CLOSED")
RESOLUTIONS = ("FALSE-POSITIVE", "WONTFIX", "FIXED", "REMOVED")

_TOO_MANY_ISSUES_MSG = "Too many issues, recursing..."
_ISSUES = {}


class TooManyIssuesError(Exception):
    """When a call to api/issues/search returns too many issues."""

    def __init__(self, nbr_issues, message):
        super().__init__()
        self.nbr_issues = nbr_issues
        self.message = message


class Issue(findings.Finding):
    """
    Abstraction of the SonarQube 'issue' concept
    """

    SEARCH_API = "issues/search"
    MAX_PAGE_SIZE = 500
    MAX_SEARCH = 10000
    OPTIONS_SEARCH = [
        "additionalFields",
        "asc",
        "assigned",
        "assignees",
        "authors",
        "componentKeys",
        "createdAfter",
        "createdAt",
        "createdBefore",
        "createdInLast",
        "directories",
        "facetMode",
        "facets",
        "files",
        "branch",
        "fileUuids",
        "issues",
        "languages",
        "onComponentOnly",
        "p",
        "ps",
        "resolutions",
        "resolved",
        "rules",
        "s",
        "severities",
        "sinceLeakPeriod",
        "statuses",
        "tags",
        "types",
    ]

    def __init__(self, key, endpoint, data=None, from_export=False):
        super().__init__(key, endpoint, data, from_export)
        self._debt = None
        self.tags = []  #: Issue tags
        if data is not None:
            self.component = data.get("component", None)
        # util.logger.debug("Loaded issue: %s", util.json_dump(data))
        _ISSUES[self.uuid()] = self

    def __str__(self):
        """
        :return: String representation of the issue
        :rtype: str
        """
        return f"Issue key '{self.key}'"

    def __format__(self, format_spec=""):
        return (
            f"Key: {self.key} - Type: {self.type} - Severity: {self.severity}"
            f" - File/Line: {self.component}/{self.line} - Rule: {self.rule} - Project: {self.projectKey}"
        )

    def url(self):
        """
        :return: A permalink URL to the issue in the SonarQube platform
        :rtype: str
        """
        branch = ""
        if self.branch is not None:
            branch = f"&branch={requests.utils.quote(self.branch)}"
        elif self.pull_request is not None:
            branch = f"pullRequest={requests.utils.quote(self.pull_request)}&"
        return f"{self.endpoint.url}/project/issues?id={self.projectKey}{branch}&issues={self.key}"

    def debt(self):
        """
        :return: The remediation effort of the issue, in minutes
        :rtype: int
        """
        if self._debt is not None:
            return self._debt
        if "debt" in self._json:
            kdays, days, hours, minutes = 0, 0, 0, 0
            debt = self._json["debt"]
            m = re.search(r"(\d+)kd", debt)
            if m:
                kdays = int(m.group(1))
            m = re.search(r"(\d+)d", debt)
            if m:
                days = int(m.group(1))
            m = re.search(r"(\d+)h", debt)
            if m:
                hours = int(m.group(1))
            m = re.search(r"(\d+)min", debt)
            if m:
                minutes = int(m.group(1))
            self._debt = ((kdays * 1000 + days) * 24 + hours) * 60 + minutes
        elif "effort" in self._json:
            self._debt = 0
            if self._json["effort"] != "null":
                self._debt = int(self._json["effort"])
        return self._debt

    def to_json(self):
        """
        :return: The issue attributes as JSON
        :rtype: dict
        """
        data = super().to_json()
        data["url"] = self.url()
        data["effort"] = self.debt()
        return data

    def refresh(self):
        """Refreshes an issue from the SonarQube platform live data
        :return: whether the refresh was successful
        :rtype: bool
        """
        resp = self.get(Issue.SEARCH_API, params={"issues": self.key, "additionalFields": "_all"})
        if resp.ok:
            self._load(resp.issues[0])
        return resp.ok

    def changelog(self):
        """
        :return: The issue changelog
        :rtype: dict{"<date>_<sequence_nbr>": <event>}
        """
        if self._changelog is None:
            data = json.loads(self.get("issues/changelog", {"issue": self.key, "format": "json"}).text)
            util.json_dump_debug(data["changelog"], f"{str(self)} Changelog = ")
            self._changelog = {}
            seq = 1
            for l in data["changelog"]:
                d = changelog.Changelog(l)
                if d.is_technical_change():
                    # Skip automatic changelog events generated by SonarSource itself
                    util.logger.debug("Changelog is a technical change: %s", str(d))
                    continue
                util.json_dump_debug(l, "Changelog item Changelog ADDED = ")
                seq += 1
                self._changelog[f"{d.date()}_{seq:03d}"] = d
        return self._changelog

    def comments(self):
        """
        :return: The issue comments
        :rtype: dict{"<date>_<sequence_nbr>": <comment>}
        """
        if "comments" not in self._json:
            self._comments = {}
        elif self._comments is None:
            self._comments = {}
            seq = 0
            for c in self._json["comments"]:
                seq += 1
                self._comments[f"{c['createdAt']}_{seq:03}"] = {
                    "date": c["createdAt"],
                    "event": "comment",
                    "value": c["markdown"],
                    "user": c["login"],
                    "userName": c["login"],
                }
        return self._comments

    def add_comment(self, comment):
        """Adds a comment to an issue

        :param comment: The comment to add
        :type comment: str
        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.debug("Adding comment '%s' to %s", comment, str(self))
        r = self.post("issues/add_comment", {"issue": self.key, "text": comment})
        return r.ok

    def set_severity(self, severity):
        """Changes the severity of an issue

        :param severity: The comment to add
        :type severity: str
        :return: Whether the operation succeeded
        :rtype: bool
        """
        if severity != self.severity:
            util.logger.debug("Changing severity of %s from '%s' to '%s'", str(self), self.severity, severity)
            return self.post("issues/set_severity", {"issue": self.key, "severity": severity}).ok
        return False

    def assign(self, assignee):
        """Assigns an issue to a user

        :param assignee: The user login
        :type assignee: str
        :return: Whether the operation succeeded
        :rtype: bool
        """
        if assignee != self.assignee:
            util.logger.debug("Assigning %s to '%s'", str(self), assignee)
            return self.post("issues/assign", {"issue": self.key, "assignee": assignee}).ok
        return False

    def set_tags(self, tags):
        """Sets tags to an issue (Replacing all previous tags)
        :param tags: Tags to set
        :type tags: list
        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.debug("Setting tags %s to %s", tags, str(self))
        if not self.post(API_SET_TAGS, {"issue": self.key, "tags": util.list_to_csv(tags)}).ok:
            return False
        self.tags = tags
        return True

    def add_tag(self, tag):
        """Adds a tag to an issue
        :param tag: Tags to add
        :type tag: str
        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.debug("Adding tag '%s' to %s", tag, str(self))
        tags = self.tags.copy()
        if tag not in self.tags:
            tags.append(tag)
        return self.set_tags(tags)

    def remove_tag(self, tag):
        """Removes a tag from an issue
        :param tag: Tags to remove
        :type tag: str
        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.debug("Removing tag '%s' from %s", tag, str(self))
        tags = self.tags.copy()
        if tag in self.tags:
            tags.remove(tag)
        return self.set_tags(tags)

    def set_type(self, new_type):
        """Sets an issue type
        :param new_type: New type of the issue (Can be BUG, VULNERABILITY or CODE_SMELL)
        :type tag: str
        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.debug("Changing type of issue %s from %s to %s", self.key, self.type, new_type)
        return self.post(API_SET_TYPE, {"issue": self.key, "type": new_type}).ok

    def is_wont_fix(self):
        """
        :return: Whether the issue is won't fix
        :rtype: bool
        """
        return self.resolution == "WONT-FIX"

    def is_false_positive(self):
        """
        :return: Whether the issue is a false positive
        :rtype: bool
        """
        return self.resolution == "FALSE-POSITIVE"

    def strictly_identical_to(self, another_finding, ignore_component=False):
        """
        :meta private:
        """
        return super.strictly_identical_to(another_finding, ignore_component) and (self.debt() == another_finding.debt())

    def almost_identical_to(self, another_finding, ignore_component=False, **kwargs):
        """
        :meta private:
        """
        return super.almost_identical_to(another_finding, ignore_component, **kwargs) and (
            self.debt() == another_finding.debt() or kwargs.get("ignore_debt", False)
        )

    def __do_transition(self, transition):
        return self.post("issues/do_transition", {"issue": self.key, "transition": transition}).ok

    def reopen(self):
        """Re-opens an issue

        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.debug("Reopening %s", str(self))
        return self.__do_transition("reopen")

    def mark_as_false_positive(self):
        """Sets an issue as false positive

        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.debug("Marking %s as false positive", str(self))
        return self.__do_transition("falsepositive")

    def confirm(self):
        """Confirms an issue

        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.debug("Confirming %s", str(self))
        return self.__do_transition("confirm")

    def unconfirm(self):
        """Unconfirms an issue

        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.debug("Unconfirming %s", str(self))
        return self.__do_transition("unconfirm")

    def resolve_as_fixed(self):
        """Marks an issue as resolved as fixed

        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.debug("Marking %s as fixed", str(self))
        return self.__do_transition("resolve")

    def mark_as_wont_fix(self):
        """Marks an issue as resolved as won't fix

        :return: Whether the operation succeeded
        :rtype: bool
        """
        util.logger.debug("Marking %s as won't fix", str(self))
        return self.__do_transition("wontfix")

    def __apply_event(self, event, settings):
        util.logger.debug("Applying event %s", str(event))
        # origin = f"originally by *{event['userName']}* on original branch"
        (event_type, data) = event.changelog_type()
        if event_type == "SEVERITY":
            self.set_severity(data)
            # self.add_comment(f"Change of severity {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "TYPE":
            self.set_type(data)
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "REOPEN":
            if event.previous_state() == "CLOSED":
                util.logger.info("Reopen from closed issue won't be applied, issue was never closed")
            else:
                self.reopen()
            # self.add_comment(f"Issue re-open {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "FALSE-POSITIVE":
            self.mark_as_false_positive()
            # self.add_comment(f"False positive {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "WONT-FIX":
            self.mark_as_wont_fix()
            # self.add_comment(f"Won't fix {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "CONFIRM":
            self.confirm()
            # self.add_comment(f"Won't fix {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "UNCONFIRM":
            self.unconfirm()
            # self.add_comment(f"Won't fix {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "ASSIGN":
            if settings[syncer.SYNC_ASSIGN]:
                u = users.get_login_from_name(data, endpoint=self.endpoint)
                if u is None:
                    u = settings[syncer.SYNC_SERVICE_ACCOUNTS][0]
                self.assign(u)
                # self.add_comment(f"Issue assigned {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "TAG":
            self.set_tags(data)
            # self.add_comment(f"Tag change {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "FIXED":
            self.resolve_as_fixed()
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "CLOSED":
            util.logger.info(
                "Changelog event is a CLOSE issue, it cannot be applied... %s",
                str(event),
            )
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "INTERNAL":
            util.logger.info("Changelog %s is internal, it will not be applied...", str(event))
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        else:
            util.logger.error("Event %s can't be applied", str(event))
            return False
        return True

    def apply_changelog(self, source_issue, settings):
        """
        :meta private:
        """
        events = source_issue.changelog()
        if events is None or not events:
            util.logger.debug("Sibling %s has no changelog, no action taken", source_issue.key)
            return False

        change_nbr = 0
        start_change = len(self.changelog()) + 1
        util.logger.debug("Issue %s: Changelog = %s", str(self), str(self.changelog()))
        util.logger.info(
            "Applying changelog of issue %s to issue %s, from change %d",
            source_issue.key,
            self.key,
            start_change,
        )
        for key in sorted(events.keys()):
            change_nbr += 1
            if change_nbr < start_change:
                util.logger.debug(
                    "Skipping change already applied in a previous sync: %s",
                    str(events[key]),
                )
                continue
            self.__apply_event(events[key], settings)

        comments = source_issue.comments()
        if len(self.comments()) == 0 and settings[syncer.SYNC_ADD_LINK]:
            util.logger.info("Target %s has 0 comments, adding sync link comment", str(self))
            start_change = 1
            self.add_comment(f"Automatically synchronized from [this original issue]({source_issue.url()})")
        else:
            start_change = len(self.comments())
            util.logger.info("Target %s already has %d comments", str(self), start_change)
        util.logger.info(
            "Applying comments of %s to %s, from comment %d",
            str(source_issue),
            str(self),
            start_change,
        )
        change_nbr = 0
        for key in sorted(comments.keys()):
            change_nbr += 1
            if change_nbr < start_change:
                util.logger.debug(
                    "Skipping comment already applied in a previous sync: %s",
                    str(comments[key]),
                )
                continue
            # origin = f"originally by *{event['userName']}* on original branch"
            self.add_comment(comments[key]["value"])
        return True


# ------------------------------- Static methods --------------------------------------


def __search_all_by_directories(params, endpoint=None):
    new_params = params.copy()
    facets = _get_facets(new_params["componentKeys"], facets="directories", params=new_params, endpoint=endpoint)
    issue_list = {}
    util.logger.info("Splitting search by directories")
    for d in facets["directories"]:
        new_params["directories"] = d["val"]
        issue_list.update(search(endpoint=endpoint, params=new_params, raise_error=False))
    util.logger.debug("Search by directory ALL: %d issues found", len(issue_list))
    return issue_list


def __search_all_by_types(params, endpoint=None):
    issue_list = {}
    new_params = params.copy()
    util.logger.info("Splitting search by issue types")
    for issue_type in ("BUG", "VULNERABILITY", "CODE_SMELL"):
        try:
            new_params["types"] = issue_type
            issue_list.update(search(endpoint=endpoint, params=new_params))
        except TooManyIssuesError:
            util.logger.info(_TOO_MANY_ISSUES_MSG)
            issue_list.update(__search_all_by_directories(params=new_params, endpoint=endpoint))
    util.logger.debug("Search by type ALL: %d issues found", len(issue_list))
    return issue_list


def __search_all_by_severities(params, endpoint=None):
    issue_list = {}
    new_params = params.copy()
    util.logger.info("Splitting search by severities")
    for sev in ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"):
        try:
            new_params["severities"] = sev
            issue_list.update(search(endpoint=endpoint, params=new_params))
        except TooManyIssuesError:
            util.logger.info(_TOO_MANY_ISSUES_MSG)
            issue_list.update(__search_all_by_types(params=new_params, endpoint=endpoint))
    util.logger.debug("Search by severity ALL: %d issues found", len(issue_list))
    return issue_list


def __search_all_by_date(params, date_start=None, date_stop=None, endpoint=None):
    new_params = params.copy()
    if date_start is None:
        date_start = get_oldest_issue(endpoint=endpoint, params=new_params).replace(hour=0, minute=0, second=0, microsecond=0)
    if date_stop is None:
        date_stop = get_newest_issue(endpoint=endpoint, params=new_params).replace(hour=0, minute=0, second=0, microsecond=0)
    util.logger.info("Splitting search by date between [%s - %s]", util.date_to_string(date_start, False), util.date_to_string(date_stop, False))
    issue_list = {}
    new_params.update({"createdAfter": date_start, "createdBefore": date_stop})
    try:
        issue_list = search(endpoint=endpoint, params=new_params)
    except TooManyIssuesError as e:
        util.logger.debug("Too many issues (%d), splitting time window", e.nbr_issues)
        diff = (date_stop - date_start).days
        if diff == 0:
            util.logger.info(_TOO_MANY_ISSUES_MSG)
            issue_list = __search_all_by_severities(new_params, endpoint=endpoint)
        elif diff == 1:
            issue_list.update(__search_all_by_date(new_params, date_start=date_start, date_stop=date_start, endpoint=endpoint))
            issue_list.update(__search_all_by_date(new_params, date_start=date_stop, date_stop=date_stop, endpoint=endpoint))
        else:
            date_middle = date_start + datetime.timedelta(days=diff // 2)
            issue_list.update(__search_all_by_date(new_params, date_start=date_start, date_stop=date_middle, endpoint=endpoint))
            date_middle = date_middle + datetime.timedelta(days=1)
            issue_list.update(__search_all_by_date(new_params, date_start=date_middle, date_stop=date_stop, endpoint=endpoint))
    if date_start is not None and date_stop is not None:
        util.logger.debug(
            "Project %s has %d issues between %s and %s",
            new_params["componentKeys"],
            len(issue_list),
            util.date_to_string(date_start, False),
            util.date_to_string(date_stop, False),
        )
    return issue_list


def __search_all_by_project(project_key, params, endpoint=None):
    new_params = {} if params is None else params.copy()
    if project_key is None:
        key_list = projects.search(endpoint).keys()
    else:
        key_list = util.csv_to_list(project_key)
    issue_list = {}
    for k in key_list:
        new_params["componentKeys"] = k
        util.logger.debug("Searching for issues of project '%s'", k)
        try:
            issue_list.update(search(endpoint=endpoint, params=new_params))
        except TooManyIssuesError:
            util.logger.info(_TOO_MANY_ISSUES_MSG)
            issue_list.update(__search_all_by_date(params=new_params, endpoint=endpoint))
    return issue_list


def search_by_project(project_key, endpoint, params=None, search_findings=False):
    """Search all issues of a given project

    :param project_key: The project key
    :type project_key: str
    :param endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :param params: List of search filters to narrow down the search, defaults to None
    :type params: dict
    :param search_findings: Whether to use the api/project_search/findings API or not, defaults to False
    :type search_findings: bool, optional
    :return: list of Issues
    :rtype: dict{<key>: <Issue>}
    """
    if params is None:
        params = {}
    if project_key is None:
        key_list = projects.search(endpoint).keys()
    else:
        key_list = util.csv_to_list(project_key)
    issue_list = {}
    for k in key_list:
        util.logger.info("Project '%s' issue search", k)
        if endpoint.version() >= (9, 1, 0) and endpoint.edition() in ("enterprise", "datacenter") and search_findings:
            util.logger.info("Using new export findings to speed up issue export")
            issue_list.update(findings.export_findings(endpoint, k, params.get("branch", None), params.get("pullRequest", None)))
        else:
            issue_list.update(__search_all_by_project(k, params=params, endpoint=endpoint))
        util.logger.info("Project '%s' has %d issues", k, len(issue_list))
    return issue_list


def search_all(endpoint, params=None):
    """Returns all issues of the platforms

    :param endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :param params: List of search filters to narrow down the search, defaults to None
    :type params: dict
    :return: list of Issues
    :rtype: dict{<key>: <Issue>}
    """
    new_params = {} if params is None else params.copy()
    util.logger.info("Issue search all with %s", str(params))
    issue_list = {}
    try:
        issue_list = search(endpoint=endpoint, params=params)
    except TooManyIssuesError:
        util.logger.info(_TOO_MANY_ISSUES_MSG)
        for k in projects.search(endpoint):
            issue_list.update(__search_all_by_project(k, params=new_params, endpoint=endpoint))
    return issue_list


def __search_thread(queue):
    while not queue.empty():
        (endpoint, api, issue_list, params, page) = queue.get()
        page_params = params.copy()
        page_params["p"] = page
        util.logger.debug("Threaded issue search params = %s", str(page_params))
        data = json.loads(endpoint.get(api, params=page_params).text)
        for i in data["issues"]:
            i["branch"] = page_params.get("branch", None)
            i["pullRequest"] = page_params.get("pullRequest", None)
            issue_list[i["key"]] = get_object(i["key"], endpoint=endpoint, data=i)
        util.logger.debug("Added %d issues in threaded search page %d", len(data["issues"]), page)
        queue.task_done()


def search_first(endpoint, **params):
    """
    :return: The first issue of a search, for instance the oldest, if params = s="CREATION_DATE", asc=asc_sort
    :rtype: Issue or None if not issue found
    """
    params["ps"] = 1
    data = json.loads(endpoint.get(Issue.SEARCH_API, params=params).text)
    if len(data) == 0:
        return None
    i = data["issues"][0]
    return get_object(i["key"], endpoint=endpoint, data=i)


def search(endpoint, params=None, raise_error=True, threads=8):
    """Multi-threaded search of issues

    :param params: Search filter criteria to narrow down the search
    :type params: dict
    :param raise_error: Whether to raise exception if more than 10'000 issues returned, defaults to True
    :type raise_error: bool
    :param threads: Nbr of parallel threads for search, defaults to 8
    :type threads: int
    :return: List of issues found
    :rtype: dict{<key>: <Issue>}
    :raises: TooManyIssuesError if more than 10'000 issues found
    """
    new_params = {} if params is None else params.copy()
    util.logger.debug("Search params = %s", str(new_params))
    if "ps" not in new_params:
        new_params["ps"] = Issue.MAX_PAGE_SIZE
    issue_list = {}

    data = json.loads(endpoint.get(Issue.SEARCH_API, params=new_params).text)
    nbr_issues = data["paging"]["total"]
    nbr_pages = util.nbr_pages(data)
    util.logger.debug("Number of issues: %d - Nbr pages: %d", nbr_issues, nbr_pages)
    if nbr_pages > 20 and raise_error:
        raise TooManyIssuesError(
            nbr_issues,
            f"{nbr_issues} issues returned by api/{Issue.SEARCH_API}, this is more than the max {Issue.MAX_SEARCH} possible",
        )
    for i in data["issues"]:
        i["branch"] = new_params.get("branch", None)
        i["pullRequest"] = new_params.get("pullRequest", None)
        issue_list[i["key"]] = get_object(i["key"], endpoint=endpoint, data=i)
    if nbr_pages == 1:
        return issue_list
    q = Queue(maxsize=0)
    for page in range(2, nbr_pages + 1):
        q.put((endpoint, Issue.SEARCH_API, issue_list, new_params, page))
    for i in range(threads):
        util.logger.debug("Starting issue search thread %d", i)
        worker = Thread(target=__search_thread, args=[q])
        worker.setDaemon(True)
        worker.start()
    q.join()
    return issue_list


def _get_facets(project_key, facets="directories", endpoint=None, params=None):
    new_params = {} if params is None else params.copy()
    new_params.update({"componentKeys": project_key, "facets": facets, "ps": 500})
    new_params = __get_issues_search_params(new_params)
    data = json.loads(endpoint.get(Issue.SEARCH_API, params=new_params).text)
    l = {}
    facets_list = util.csv_to_list(facets)
    for f in data["facets"]:
        if f["property"] in facets_list:
            l[f["property"]] = f["values"]
    return l


def __get_one_issue_date(endpoint=None, asc_sort="false", params=None):
    """Returns the date of one issue found"""
    issue = search_first(endpoint=endpoint, s="CREATION_DATE", asc=asc_sort, **params)
    if not issue:
        return None
    return issue.creation_date


def get_oldest_issue(endpoint=None, params=None):
    """Returns the oldest date of all issues found"""
    return __get_one_issue_date(endpoint=endpoint, asc_sort="true", params=params)


def get_newest_issue(endpoint=None, params=None):
    """Returns the newest date of all issues found"""
    return __get_one_issue_date(endpoint=endpoint, asc_sort="false", params=params)


def count(endpoint=None, **kwargs):
    """Returns number of issues of a search"""
    returned_data = search(endpoint=endpoint, params=kwargs.copy().update({"ps": 1}))
    util.logger.debug("Issue search %s would return %d issues", str(kwargs), returned_data["total"])
    return returned_data["total"]


def identical_attributes(o1, o2, key_list):
    for key in key_list:
        if o1[key] != o2[key]:
            return False
    return True


def __get_issues_search_params(params):
    outparams = {"additionalFields": "comments"}
    for key in params:
        if params[key] is not None and key in Issue.OPTIONS_SEARCH:
            outparams[key] = params[key]
    return outparams


def get_object(key, data=None, endpoint=None, from_export=False):
    if key not in _ISSUES:
        _ = Issue(key=key, data=data, endpoint=endpoint, from_export=from_export)
    return _ISSUES[key]


def get_search_criteria(params):
    """Returns the filtered list of params that are allowed for api/issue/search"""
    criterias = params.copy()
    if criterias.get("types", None) is not None:
        criterias["types"] = util.allowed_values_string(criterias["types"], TYPES)
    if criterias.get("severities", None) is not None:
        criterias["severities"] = util.allowed_values_string(criterias["severities"], SEVERITIES)
    if criterias.get("statuses", None) is not None:
        criterias["statuses"] = util.allowed_values_string(criterias["statuses"], STATUSES)
    if criterias.get("resolutions", None) is not None:
        criterias["resolutions"] = util.allowed_values_string(criterias["resolutions"], RESOLUTIONS)
    criterias = util.dict_subset(util.remove_nones(criterias), SEARCH_CRITERIAS)
    return criterias
