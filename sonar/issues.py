#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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

"""Abstraction of the SonarQube issue concept"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
import json
import re

from typing import Union, Optional
from queue import Queue
from threading import Thread
import requests.utils

import sonar.logging as log
import sonar.platform as pf
from sonar.util import cache
import sonar.util.constants as c

from sonar.util.types import ApiParams, ApiPayload, ObjectJsonRepr, ConfigSettings

from sonar import users, findings, changelog, projects, rules, config, exceptions
import sonar.utilities as util

COMPONENT_FILTER_OLD = "componentKeys"
COMPONENT_FILTER = "components"

OLD_STATUS = "resolutions"
NEW_STATUS = "issueStatuses"

OLD_FP = "FALSE-POSITIVE"
NEW_FP = "FALSE_POSITIVE"

_SEARCH_CRITERIAS = (
    COMPONENT_FILTER_OLD,
    COMPONENT_FILTER,
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
    "ps",
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
    OLD_STATUS,
    "resolved",
    "rules",
    "scopes",
    # 10.2 new filter
    "impactSeverities",
    # 10.4 new filter
    NEW_STATUS,
)

_FILTERS_10_2_REMAPPING = {"severities": "impactSeverities"}

TYPES = ("BUG", "VULNERABILITY", "CODE_SMELL")
SEVERITIES = ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO")
IMPACT_SEVERITIES = ("HIGH", "MEDIUM", "LOW")
IMPACT_SOFTWARE_QUALITIES = ("SECURITY", "RELIABILITY", "MAINTAINABILITY")
STATUSES = ("OPEN", "CONFIRMED", "REOPENED", "RESOLVED", "CLOSED", "ACCEPTED", "FALSE_POSITIVE")
RESOLUTIONS = ("FALSE-POSITIVE", "WONTFIX", "FIXED", "REMOVED", "ACCEPTED")
FILTERS_MAP = {
    "types": TYPES,
    "severities": SEVERITIES,
    "impactSoftwareQualities": IMPACT_SOFTWARE_QUALITIES,
    "impactSeverities": IMPACT_SEVERITIES,
    "statuses": STATUSES,
    OLD_STATUS: RESOLUTIONS,
}

_TOO_MANY_ISSUES_MSG = "Too many issues, recursing..."


class TooManyIssuesError(Exception):
    """When a call to api/issues/search returns too many issues."""

    def __init__(self, nbr_issues: int, message: str) -> None:
        super().__init__()
        self.nbr_issues = nbr_issues
        self.message = message


class Issue(findings.Finding):
    """
    Abstraction of the SonarQube 'issue' concept
    """

    CACHE = cache.Cache()
    MAX_PAGE_SIZE = 500
    MAX_SEARCH = 10000
    API = {c.SEARCH: "issues/search", c.GET_TAGS: "issues/search", c.SET_TAGS: "issues/set_tags"}

    def __init__(self, endpoint: pf.Platform, key: str, data: ApiPayload = None, from_export: bool = False) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key, data=data, from_export=from_export)
        self._debt = None
        Issue.CACHE.put(self)

    def __str__(self) -> str:
        """
        :return: String representation of the issue
        :rtype: str
        """
        return f"Issue key '{self.key}'"

    def __format__(self, format_spec: str = "") -> str:
        return (
            f"Key: {self.key} - Type: {self.type} - Severity: {self.severity}"
            f" - File/Line: {self.component}/{self.line} - Rule: {self.rule} - Project: {self.projectKey}"
        )

    def api_params(self, op: str = c.LIST) -> ApiParams:
        ops = {c.LIST: {"issues": self.key}, c.SET_TAGS: {"issue": self.key}, c.GET_TAGS: {"issues": self.key}}
        return ops[op] if op in ops else ops[c.LIST]

    def url(self) -> str:
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

    def debt(self) -> int:
        """
        :return: The remediation effort of the issue, in minutes
        """
        if self._debt is not None:
            return self._debt
        if "debt" in self.sq_json:
            kdays, days, hours, minutes = 0, 0, 0, 0
            debt = self.sq_json["debt"]
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
        elif "effort" in self.sq_json:
            self._debt = 0
            if self.sq_json["effort"] != "null":
                self._debt = int(self.sq_json["effort"])
        return self._debt

    def to_json(self, without_time: bool = False) -> ObjectJsonRepr:
        """
        :return: The issue attributes as JSON
        :rtype: dict
        """
        data = super().to_json(without_time)
        if self.endpoint.version() >= (10, 2, 0):
            data["impacts"] = {elem["softwareQuality"]: elem["severity"] for elem in self.sq_json["impacts"]}
        data["effort"] = self.debt()
        return data

    def refresh(self) -> bool:
        """Refreshes an issue from the SonarQube platform live data
        :return: whether the refresh was successful
        :rtype: bool
        """
        resp = self.get(Issue.API[c.SEARCH], params={"issues": self.key, "additionalFields": "_all"})
        if resp.ok:
            self._load(json.loads(resp.text)["issues"][0])
        return resp.ok

    def changelog(self, manual_only: bool = True) -> dict[str, str]:
        """
        :param bool manual_only: Whether the only manual changes should be returned or all changes
        :return: The issue changelog
        :rtype: dict{"<date>_<sequence_nbr>": <event>}
        """
        if self._changelog is None:
            data = json.loads(self.get("issues/changelog", {"issue": self.key, "format": "json"}).text)
            # util.json_dump_debug(data["changelog"], f"{str(self)} Changelog = ")
            self._changelog = {}
            seq = 1
            for l in data["changelog"]:
                d = changelog.Changelog(l)
                if d.is_technical_change():
                    # Skip automatic changelog events generated by SonarSource itself
                    log.debug("%s: Changelog is a technical change: %s", str(self), str(d))
                    continue
                if manual_only and not d.is_manual_change():
                    # Skip automatic changelog events generated by SonarSource itself
                    log.debug("%s: Changelog is an automatic change: %s", str(self), str(d))
                    continue
                log.debug("%s: Changelog item Changelog ADDED = %s", str(self), str(d))
                seq += 1
                self._changelog[f"{d.date()}_{seq:03d}"] = d
        return self._changelog

    def comments(self) -> dict[str, str]:
        """
        :return: The issue comments
        :rtype: dict{"<date>_<sequence_nbr>": <comment>}
        """
        if "comments" not in self.sq_json:
            self._comments = {}
        elif self._comments is None:
            self._comments = {}
            seq = 0
            for cmt in self.sq_json["comments"]:
                seq += 1
                self._comments[f"{cmt['createdAt']}_{seq:03}"] = {
                    "date": cmt["createdAt"],
                    "event": "comment",
                    "value": cmt["markdown"],
                    "user": cmt["login"],
                    "userName": cmt["login"],
                }
        return self._comments

    def add_comment(self, comment: str) -> bool:
        """Adds a comment to an issue

        :param str comment: The comment to add
        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.debug("Adding comment '%s' to %s", comment, str(self))
        try:
            r = self.post("issues/add_comment", {"issue": self.key, "text": comment})
        except (ConnectionError, requests.RequestException) as e:
            util.handle_error(e, "adding comment", catch_all=True)
            return False
        return r.ok

    def set_severity(self, severity: str) -> bool:
        """Changes the severity of an issue

        :param str severity: The comment to add
        :return: Whether the operation succeeded
        :rtype: bool
        """
        try:
            log.debug("Changing severity of %s from '%s' to '%s'", str(self), self.severity, severity)
            r = self.post("issues/set_severity", {"issue": self.key, "severity": severity})
            if r.ok:
                self.severity = severity
        except (ConnectionError, requests.RequestException) as e:
            util.handle_error(e, "changing issue severity", catch_all=True)
            return False
        return r.ok

    def assign(self, assignee: str) -> bool:
        """Assigns an issue to a user

        :param str assignee: The user login
        :return: Whether the operation succeeded
        :rtype: bool
        """
        try:
            log.debug("Assigning %s to '%s'", str(self), assignee)
            r = self.post("issues/assign", {"issue": self.key, "assignee": assignee})
            if r.ok:
                self.assignee = assignee
        except (ConnectionError, requests.RequestException) as e:
            util.handle_error(e, "assigning issue", catch_all=True)
            return False
        return r.ok

    def get_tags(self, **kwargs) -> list[str]:
        """Returns issues tags"""
        api = self.__class__.API[c.GET_TAGS]
        if self._tags is None:
            self._tags = self.sq_json.get("tags", None)
        if not kwargs.get(c.USE_CACHE, True) or self._tags is None:
            data = json.loads(self.get(api, params=self.api_params(c.GET_TAGS)).text)
            self.sq_json.update(data["issues"][0])
            self._tags = self.sq_json["tags"]
        return self._tags

    def add_tag(self, tag: str) -> bool:
        """Adds a tag to an issue
        :param str tag: Tags to add
        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.debug("Adding tag '%s' to %s", tag, str(self))
        tags = [] if not self._tags else self._tags.copy()
        if tag not in self._tags:
            tags.append(tag)
        return self.set_tags(tags)

    def remove_tag(self, tag: str) -> bool:
        """Removes a tag from an issue
        :param str tag: Tag to remove
        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.debug("Removing tag '%s' from %s", tag, str(self))
        if self._tags is None:
            self._tags = []
        tags = self._tags.copy()
        if tag in self._tags:
            tags.remove(tag)
        return self.set_tags(tags)

    def set_type(self, new_type: str) -> bool:
        """Sets an issue type
        :param str new_type: New type of the issue (Can be BUG, VULNERABILITY or CODE_SMELL)
        :return: Whether the operation succeeded
        :rtype: bool
        """
        if self.endpoint.is_mqr_mode():
            raise exceptions.UnsupportedOperation("Changing issue type is not supported in MQR mode")
        log.debug("Changing type of issue %s from %s to %s", self.key, self.type, new_type)
        try:
            r = self.post("issues/set_type", {"issue": self.key, "type": new_type})
            if r.ok:
                self.type = new_type
        except (ConnectionError, requests.RequestException) as e:
            util.handle_error(e, "setting issue type", catch_all=True)
            return False
        return r.ok

    def is_wont_fix(self) -> bool:
        """
        :return: Whether the issue is won't fix
        :rtype: bool
        """
        return self.resolution == "WONTFIX"

    def is_accepted(self) -> bool:
        """
        :return: Whether the issue is won't fix
        :rtype: bool
        """
        return self.resolution == "ACCEPTED"

    def is_false_positive(self) -> bool:
        """
        :return: Whether the issue is a false positive
        :rtype: bool
        """
        return self.resolution in ("FALSE-POSITIVE", "FALSE_POSITIVE")

    def strictly_identical_to(self, another_finding: Issue, ignore_component: bool = False) -> bool:
        """
        :meta private:
        """
        return super().strictly_identical_to(another_finding, ignore_component) and (self.debt() == another_finding.debt())

    def almost_identical_to(self, another_finding: Issue, ignore_component: bool = False, **kwargs) -> bool:
        """
        :meta private:
        """
        rule_debt_calc = rules.Rule.get_object(self.endpoint, self.rule).sq_json.get("remFnType", "CONSTANT_ISSUE")
        # Rule that have linear remediation function may have slightly different debt
        return super().almost_identical_to(another_finding, ignore_component, **kwargs) and (
            self.debt() == another_finding.debt() or kwargs.get("ignore_debt", False) or rule_debt_calc != "CONSTANT_ISSUE"
        )

    def reopen(self) -> bool:
        """Re-opens an issue

        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.debug("Reopening %s", str(self))
        return self.do_transition("reopen")

    def mark_as_false_positive(self) -> bool:
        """Sets an issue as false positive

        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.debug("Marking %s as false positive", str(self))
        return self.do_transition("falsepositive")

    def confirm(self) -> bool:
        """Confirms an issue

        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.debug("Confirming %s", str(self))
        return self.do_transition("confirm")

    def unconfirm(self) -> bool:
        """Unconfirms an issue

        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.debug("Unconfirming %s", str(self))
        return self.do_transition("unconfirm")

    def resolve_as_fixed(self) -> bool:
        """Marks an issue as resolved as fixed

        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.debug("Marking %s as fixed", str(self))
        return self.do_transition("resolve")

    def mark_as_wont_fix(self) -> bool:
        """Marks an issue as resolved as won't fix

        :return: Whether the operation succeeded
        :rtype: bool
        """
        if self.endpoint.version() >= (10, 4, 0) or self.endpoint.is_sonarcloud():
            log.warning("Marking %s as won't fix is deprecated, using Accept instead", str(self))
            return self.do_transition("accept")
        else:
            return self.do_transition("wontfix")

    def accept(self) -> bool:
        """Marks an issue as resolved as won't fix

        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.debug("Marking %s as accepted", str(self))
        return self.do_transition("accept")

    def __apply_event(self, event: changelog.Changelog, settings: ConfigSettings) -> bool:
        from sonar import syncer

        # origin = f"originally by *{event['userName']}* on original branch"
        (event_type, data) = event.changelog_type()
        log.debug("Applying event type %s - %s", event_type, str(event))
        if event_type == "SEVERITY":
            self.set_severity(data)
            # self.add_comment(f"Change of severity {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "TYPE":
            self.set_type(data)
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "REOPEN":
            if event.previous_state() == "CLOSED":
                log.info("Reopen from closed issue won't be applied, issue was never closed")
            else:
                self.reopen()
            # self.add_comment(f"Issue re-open {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type in ("FALSE-POSITIVE", "FALSE_POSITIVE"):
            self.mark_as_false_positive()
            # self.add_comment(f"False positive {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "WONT-FIX":
            self.mark_as_wont_fix()
            # self.add_comment(f"Won't fix {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "ACCEPT":
            self.accept()
            # self.add_comment(f"Accept {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "CONFIRM":
            self.confirm()
            # self.add_comment(f"Won't fix {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "UNCONFIRM":
            self.unconfirm()
            # self.add_comment(f"Won't fix {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "ASSIGN":
            if settings[syncer.SYNC_ASSIGN]:
                u = users.get_login_from_name(endpoint=self.endpoint, name=data)
                if u is None:
                    u = settings[syncer.SYNC_SERVICE_ACCOUNTS][0]
                self.assign(u)
                # self.add_comment(f"Issue assigned {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "UNASSIGN":
            # TODO: Handle uassign
            return False
        elif event_type == "TAG":
            self.set_tags(data)
            # self.add_comment(f"Tag change {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "FIXED":
            log.debug("Event %s is not applied", str(event))
            # self.resolve_as_fixed()
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
            return False
        elif event_type == "CLOSED":
            log.info("Changelog event is a CLOSE issue, it cannot be applied... %s", str(event))
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "INTERNAL":
            log.info("Changelog %s is internal, it will not be applied...", str(event))
            # self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        else:
            log.error("Event %s can't be applied", str(event))
            return False
        return True

    def apply_changelog(self, source_issue: Issue, settings: ConfigSettings) -> bool:
        """
        :meta private:
        """
        from sonar import syncer

        events = source_issue.changelog()
        if events is None or not events:
            log.debug("Sibling %s has no changelog, no action taken", source_issue.key)
            return False

        change_nbr = 0
        # FIXME: There can be a glitch if there are non manual changes in the changelog
        start_change = len(self.changelog()) + 1
        log.info("Applying changelog of %s to %s, from change %d", str(source_issue), str(self), start_change)
        for key in sorted(events.keys()):
            change_nbr += 1
            if change_nbr < start_change:
                log.debug("Skipping change already applied in a previous sync: %s", str(events[key]))
                continue
            self.__apply_event(events[key], settings)

        comments = source_issue.comments()
        if len(self.comments()) == 0 and settings[syncer.SYNC_ADD_LINK]:
            log.info("Target %s has 0 comments, adding sync link comment", str(self))
            start_change = 1
            self.add_comment(f"Automatically synchronized from [this original issue]({source_issue.url()})")
        else:
            start_change = len(self.comments())
            log.info("Target %s already has %d comments", str(self), start_change)
        log.info("Applying comments of %s to %s, from comment %d", str(source_issue), str(self), start_change)
        change_nbr = 0
        for key in sorted(comments.keys()):
            change_nbr += 1
            if change_nbr < start_change:
                log.debug("Skipping comment already applied in a previous sync: %s", str(comments[key]))
                continue
            # origin = f"originally by *{event['userName']}* on original branch"
            self.add_comment(comments[key]["value"])
        return True


# ------------------------------- Static methods --------------------------------------


def component_filter(endpoint: pf.Platform) -> str:
    """Returns the fields used for issues/search filter by porject key"""
    if endpoint.version() >= (10, 2, 0):
        return COMPONENT_FILTER
    else:
        return COMPONENT_FILTER_OLD


def search_by_directory(endpoint: pf.Platform, params: ApiParams) -> dict[str, Issue]:
    """Searches issues splitting by directory to avoid exceeding the 10K limit"""
    new_params = params.copy()
    if "components" in params:
        new_params[component_filter(endpoint)] = params["components"]
    log.info("Splitting search by directories with %s", util.json_dump(new_params))
    facets = _get_facets(endpoint=endpoint, project_key=new_params[component_filter(endpoint)], facets="directories", params=new_params)
    issue_list = {}
    for d in facets["directories"]:
        new_params["directories"] = d["val"]
        issue_list.update(search(endpoint=endpoint, params=new_params, raise_error=True))
    log.debug("Search by directory ALL: %d issues found", len(issue_list))
    return issue_list


def search_by_type(endpoint: pf.Platform, params: ApiParams) -> dict[str, Issue]:
    """Searches issues splitting by type to avoid exceeding the 10K limit"""
    issue_list = {}
    new_params = params.copy()
    log.info("Splitting search by issue types")
    for issue_type in ("BUG", "VULNERABILITY", "CODE_SMELL"):
        try:
            new_params["types"] = [issue_type]
            issue_list.update(search(endpoint=endpoint, params=new_params))
        except TooManyIssuesError:
            log.info(_TOO_MANY_ISSUES_MSG)
            issue_list.update(search_by_directory(endpoint=endpoint, params=new_params))
    log.debug("Search by type ALL: %d issues found", len(issue_list))
    return issue_list


def search_by_severity(endpoint: pf.Platform, params: ApiParams) -> dict[str, Issue]:
    """Searches issues splitting by severity to avoid exceeding the 10K limit"""
    issue_list = {}
    new_params = params.copy()
    log.info("Splitting search by severities")
    for sev in ("BLOCKER", "CRITICAL", "MAJOR", "MINOR", "INFO"):
        try:
            new_params["severities"] = [sev]
            issue_list.update(search(endpoint=endpoint, params=new_params))
        except TooManyIssuesError:
            log.info(_TOO_MANY_ISSUES_MSG)
            issue_list.update(search_by_type(endpoint=endpoint, params=new_params))
    log.debug("Search by severity ALL: %d issues found", len(issue_list))
    return issue_list


def search_by_date(endpoint: pf.Platform, params: ApiParams, date_start: Optional[date] = None, date_stop: Optional[date] = None) -> dict[str, Issue]:
    """Searches issues splitting by date windows to avoid exceeding the 10K limit"""
    new_params = params.copy()
    if date_start is None:
        date_start = get_oldest_issue(endpoint=endpoint, params=new_params).replace(hour=0, minute=0, second=0, microsecond=0)
        if isinstance(date_start, datetime):
            date_start = date_start.date()
    if date_stop is None:
        date_stop = get_newest_issue(endpoint=endpoint, params=new_params).replace(hour=0, minute=0, second=0, microsecond=0)
        if isinstance(date_stop, datetime):
            date_stop = date_stop.date()
    log.info(
        "Project '%s' Splitting search by date between [%s - %s]",
        params["project"],
        util.date_to_string(date_start, False),
        util.date_to_string(date_stop, False),
    )
    issue_list = {}
    new_params["createdAfter"] = util.date_to_string(date_start, with_time=False)
    new_params["createdBefore"] = util.date_to_string(date_stop, with_time=False)
    try:
        issue_list = search(endpoint=endpoint, params=new_params)
    except TooManyIssuesError as e:
        log.debug("Too many issues (%d), splitting time window", e.nbr_issues)
        diff = (date_stop - date_start).days
        if diff == 0:
            log.info(_TOO_MANY_ISSUES_MSG)
            issue_list = search_by_severity(endpoint, new_params)
        elif diff == 1:
            issue_list.update(search_by_date(endpoint=endpoint, params=new_params, date_start=date_start, date_stop=date_start))
            issue_list.update(search_by_date(endpoint=endpoint, params=new_params, date_start=date_stop, date_stop=date_stop))
        else:
            date_middle = date_start + timedelta(days=diff // 2)
            issue_list.update(search_by_date(endpoint=endpoint, params=new_params, date_start=date_start, date_stop=date_middle))
            date_middle = date_middle + timedelta(days=1)
            issue_list.update(search_by_date(endpoint=endpoint, params=new_params, date_start=date_middle, date_stop=date_stop))
    if date_start is not None and date_stop is not None:
        log.debug(
            "Project '%s' has %d issues between %s and %s",
            params["project"],
            len(issue_list),
            util.date_to_string(date_start, False),
            util.date_to_string(date_stop, False),
        )
    return issue_list


def __search_all_by_project(endpoint: pf.Platform, project_key: str, params: ApiParams = None) -> dict[str, Issue]:
    """Search issues by project"""
    new_params = {} if params is None else params.copy()
    new_params["project"] = project_key
    issue_list = {}
    log.debug("Searching for issues of project '%s'", project_key)
    try:
        issue_list.update(search(endpoint=endpoint, params=new_params))
    except TooManyIssuesError:
        log.info(_TOO_MANY_ISSUES_MSG)
        issue_list.update(search_by_date(endpoint=endpoint, params=new_params))
    return issue_list


def search_by_project(endpoint: pf.Platform, project_key: str, params: ApiParams = None, search_findings: bool = False) -> dict[str, Issue]:
    """Search all issues of a given project

    :param Platform endpoint: Reference to the Sonar platform
    :param str project_key: The project key
    :param dict params: List of search filters to narrow down the search, defaults to None
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
        log.info("Project '%s' issue search with filters %s", k, str(params))
        if endpoint.version() >= (9, 1, 0) and endpoint.edition() in ("enterprise", "datacenter") and search_findings:
            log.info("Using new export findings to speed up issue export")
            issue_list.update(findings.export_findings(endpoint, k, params.get("branch", None), params.get("pullRequest", None)))
        else:
            issue_list.update(__search_all_by_project(endpoint=endpoint, project_key=k, params=params))
        log.info("Project '%s' has %d issues", k, len(issue_list))
    return issue_list


def search_all(endpoint: pf.Platform, params: ApiParams = None) -> dict[str, Issue]:
    """Returns all issues of the platforms with chosen filtering parameters

    :param Platform endpoint: Reference to the Sonar platform
    :param params: List of search filters to narrow down the search, defaults to None
    :type params: dict
    :return: list of Issues
    :rtype: dict{<key>: <Issue>}
    """
    issue_list = {}
    new_params = params.copy() if params else {}
    new_params["ps"] = Issue.MAX_PAGE_SIZE
    try:
        issue_list = search(endpoint=endpoint, params=new_params.copy())
    except TooManyIssuesError:
        log.info(_TOO_MANY_ISSUES_MSG)
        comp_filter = component_filter(endpoint)
        if params and "project" in params:
            key_list = util.csv_to_list(params["project"])
        elif params and comp_filter in params:
            key_list = util.csv_to_list(params[comp_filter])
        else:
            key_list = projects.search(endpoint).keys()
        for k in key_list:
            issue_list.update(__search_all_by_project(endpoint=endpoint, project_key=k, params=new_params))
    log.debug("SEARCH ALL %s returns %d issues", str(params), len(issue_list))
    return issue_list


def __search_thread(queue: Queue) -> None:
    """Callback function for multithreaded issue search"""
    while not queue.empty():
        (endpoint, api, issue_list, params, page) = queue.get()
        page_params = params.copy()
        page_params["p"] = page
        log.debug("Threaded issue search params = %s", str(page_params))
        try:
            data = json.loads(endpoint.get(api, params=page_params).text)
            for i in data["issues"]:
                i["branch"] = page_params.get("branch", None)
                i["pullRequest"] = page_params.get("pullRequest", None)
                issue_list[i["key"]] = get_object(endpoint=endpoint, key=i["key"], data=i)
            log.debug("Added %d issues in threaded search page %d", len(data["issues"]), page)
        except Exception as e:
            log.error("%s while searching issues, search may be incomplete", util.error_msg(e))
        queue.task_done()


def search_first(endpoint: pf.Platform, **params) -> Union[Issue, None]:
    """
    :return: The first issue of a search, for instance the oldest, if params = s="CREATION_DATE", asc=asc_sort
    :rtype: Issue or None if not issue found
    """
    filters = pre_search_filters(endpoint=endpoint, params=params)
    filters["ps"] = 1
    data = json.loads(endpoint.get(Issue.API[c.SEARCH], params=filters).text)["issues"]
    if len(data) == 0:
        return None
    return get_object(endpoint=endpoint, key=data[0]["key"], data=data[0])


def search(endpoint: pf.Platform, params: ApiParams = None, raise_error: bool = True, threads: int = 8) -> dict[str, Issue]:
    """Multi-threaded search of issues

    :param dict params: Search filter criteria to narrow down the search
    :param bool raise_error: Whether to raise exception if more than 10'000 issues returned, defaults to True
    :param int threads: Nbr of parallel threads for search, defaults to 8
    :return: List of issues found
    :rtype: dict{<key>: <Issue>}
    :raises: TooManyIssuesError if more than 10'000 issues found
    """
    filters = pre_search_filters(endpoint=endpoint, params=params.copy())
    if "ps" not in filters:
        filters["ps"] = Issue.MAX_PAGE_SIZE

    log.debug("Search filters = %s", str(filters))
    issue_list = {}
    data = json.loads(endpoint.get(Issue.API[c.SEARCH], params=filters).text)
    nbr_issues = util.nbr_total_elements(data)
    nbr_pages = util.nbr_pages(data)
    log.debug("Number of issues: %d - Nbr pages: %d", nbr_issues, nbr_pages)

    if nbr_pages > 20 and raise_error:
        raise TooManyIssuesError(
            nbr_issues,
            f"{nbr_issues} issues returned by api/{Issue.API[c.SEARCH]}, this is more than the max {Issue.MAX_SEARCH} possible",
        )

    for i in data["issues"]:
        i["branch"] = filters.get("branch", None)
        i["pullRequest"] = filters.get("pullRequest", None)
        issue_list[i["key"]] = get_object(endpoint=endpoint, key=i["key"], data=i)
    if nbr_pages == 1:
        return issue_list
    q = Queue(maxsize=0)
    for page in range(2, nbr_pages + 1):
        q.put((endpoint, Issue.API[c.SEARCH], issue_list, filters, page))
    for i in range(threads):
        log.debug("Starting issue search thread %d", i)
        worker = Thread(target=__search_thread, args=[q])
        worker.setDaemon(True)
        worker.start()
    q.join()
    log.debug("Issue search for %s completed with %d issues", str(params), len(issue_list))
    return issue_list


def _get_facets(endpoint: pf.Platform, project_key: str, facets: str = "directories", params: ApiParams = None) -> dict[str, str]:
    """Returns the facets of a search"""
    if not params:
        params = {}
    params.update({component_filter(endpoint): project_key, "facets": facets, "ps": Issue.MAX_PAGE_SIZE, "additionalFields": "comments"})
    filters = pre_search_filters(endpoint=endpoint, params=params)
    data = json.loads(endpoint.get(Issue.API[c.SEARCH], params=filters).text)
    l = {}
    facets_list = util.csv_to_list(facets)
    for f in data["facets"]:
        if f["property"] in facets_list:
            l[f["property"]] = f["values"]
    return l


def __get_one_issue_date(endpoint: pf.Platform, asc_sort: str = "false", params: ApiParams = None) -> Optional[datetime]:
    """Returns the date of one issue found"""
    issue = search_first(endpoint=endpoint, s="CREATION_DATE", asc=asc_sort, **params)
    if not issue:
        return None
    return issue.creation_date


def get_oldest_issue(endpoint: pf.Platform, params: ApiParams = None) -> Union[datetime, None]:
    """Returns the oldest date of all issues found"""
    return __get_one_issue_date(endpoint=endpoint, asc_sort="true", params=params)


def get_newest_issue(endpoint: pf.Platform, params: ApiParams = None) -> Union[datetime, None]:
    """Returns the newest date of all issues found"""
    return __get_one_issue_date(endpoint=endpoint, asc_sort="false", params=params)


def count(endpoint: pf.Platform, **kwargs) -> int:
    """Returns number of issues of a search"""
    filters = pre_search_filters(endpoint=endpoint, params=kwargs)
    filters["ps"] = 1
    nbr_issues = util.nbr_total_elements(json.loads(endpoint.get(Issue.API[c.SEARCH], params=filters).text))
    log.debug("Count issues with filters %s returned %d issues", str(kwargs), nbr_issues)
    return nbr_issues


def count_by_rule(endpoint: pf.Platform, **kwargs) -> dict[str, int]:
    """Returns number of issues of a search"""
    nbr_slices = 1
    SLICE_SIZE = 50  # Search rules facets by bulks of 50
    if "rules" in kwargs:
        ruleset = kwargs.pop("rules")
        nbr_slices = math.ceil(len(ruleset) / SLICE_SIZE)
    params = pre_search_filters(endpoint=endpoint, params=kwargs)
    params.update({"ps": 1, "facets": "rules"})
    rulecount = {}
    for i in range(nbr_slices):
        params["rules"] = ",".join(ruleset[i * SLICE_SIZE : min((i + 1) * SLICE_SIZE - 1, len(ruleset))])
        try:
            data = json.loads(endpoint.get(Issue.API[c.SEARCH], params=params).text)["facets"][0]["values"]
            for d in data:
                if d["val"] not in ruleset:
                    continue
                if d["val"] not in rulecount:
                    rulecount[d["val"]] = 0
                rulecount[d["val"]] += d["count"]
        except Exception as e:
            log.error("%s while counting issues per rule, count may be incomplete", util.error_msg(e))
    return rulecount


def get_object(endpoint: pf.Platform, key: str, data: ApiPayload = None, from_export: bool = False) -> Issue:
    """Returns an issue from its key"""
    o = Issue.CACHE.get(key, endpoint.url)
    if not o:
        o = Issue(endpoint=endpoint, key=key, data=data, from_export=from_export)
    return o


def pre_search_filters(endpoint: pf.Platform, params: ApiParams) -> ApiParams:
    """Returns the filtered list of params that are allowed for api/issue/search"""
    if not params:
        return {}
    log.debug("Sanitizing issue search filters %s", str(params))
    version = endpoint.version()
    comp_filter = component_filter(endpoint)
    filters = util.dict_remap(original_dict=params.copy(), remapping={"project": comp_filter, "application": comp_filter, "portfolio": comp_filter})
    filters = util.dict_subset(util.remove_nones(filters), _SEARCH_CRITERIAS)
    types = filters.pop("types", []) + filters.pop("impactSoftwareQualities", [])
    severities = filters.pop("severities", []) + filters.pop("impactSeverities", [])
    statuses = filters.pop("statuses", []) + filters.pop("NEW_STATUS", []) + filters.pop(OLD_STATUS, [])
    if endpoint.is_mqr_mode():
        log.debug("MAP Type = %s", str(config.get_issues_map("impactSoftwareQualities")))
        filters["impactSoftwareQualities"] = util.list_remap(types, config.get_issues_map("types"))
        filters["impactSeverities"] = util.list_remap(severities, config.get_issues_map("severities"))
        filters[NEW_STATUS] = util.list_remap(statuses, mapping=config.get_issues_map(OLD_STATUS))
    else:
        filters["types"] = util.list_remap(types, config.get_issues_map("impactSoftwareQualities"))
        filters["severities"] = util.list_remap(severities, config.get_issues_map("impactSeverities"))
        filters[OLD_STATUS] = util.list_remap(statuses, mapping=config.get_issues_map(NEW_STATUS))

    if version < (10, 2, 0):
        # Starting from 10.2 - "componentKeys" was renamed "components"
        filters = util.dict_remap(original_dict=filters, remapping={COMPONENT_FILTER: COMPONENT_FILTER_OLD})

    filters = {k: v for k, v in filters.items() if v is not None and (not isinstance(v, (list, set, str, tuple)) or len(v) > 0)}
    for field in filters:
        allowed = config.get_issue_search_allowed_values(field)
        if allowed is not None and filters[field] is not None:
            filters[field] = util.intersection(filters[field], allowed)

    filters = {k: util.list_to_csv(v) for k, v in filters.items() if v}
    log.debug("Sanitized issue search filters %s", str(filters))
    return filters
