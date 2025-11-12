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

import concurrent.futures
import requests.utils

import sonar.logging as log
import sonar.platform as pf
from sonar.util import cache, issue_defs as idefs
import sonar.util.constants as c

from sonar.util.types import ApiParams, ApiPayload, ObjectJsonRepr, ConfigSettings

from sonar import users, findings, changelog, projects, rules, config, exceptions
import sonar.utilities as util

_OLD_SEARCH_COMPONENT_FIELD = "componentKeys"
_NEW_SEARCH_COMPONENT_FIELD = "components"

_OLD_SEARCH_STATUS_FIELD = "resolutions"
_NEW_SEARCH_STATUS_FIELD = "issueStatuses"

_OLD_SEARCH_TYPE_FIELD = "types"
_NEW_SEARCH_TYPE_FIELD = "impactSoftwareQualities"

_OLD_SEARCH_SEVERITY_FIELD = "severities"
_NEW_SEARCH_SEVERITY_FIELD = "impactSeverities"

OLD_FP = "FALSE-POSITIVE"
NEW_FP = "FALSE_POSITIVE"

_MQR_SEARCH_FIELDS = (_NEW_SEARCH_SEVERITY_FIELD, _NEW_SEARCH_STATUS_FIELD, _NEW_SEARCH_TYPE_FIELD)
_STD_SEARCH_FIELDS = (_OLD_SEARCH_SEVERITY_FIELD, _OLD_SEARCH_STATUS_FIELD, _OLD_SEARCH_TYPE_FIELD)

_COMMA_CRITERIAS = (
    _OLD_SEARCH_COMPONENT_FIELD,
    _NEW_SEARCH_COMPONENT_FIELD,
    _OLD_SEARCH_TYPE_FIELD,
    _NEW_SEARCH_TYPE_FIELD,
    _OLD_SEARCH_SEVERITY_FIELD,
    _NEW_SEARCH_SEVERITY_FIELD,
    _OLD_SEARCH_STATUS_FIELD,
    _NEW_SEARCH_STATUS_FIELD,
    "assignees",
    "additionalFields",
    "facets",
    "issues",
    "languages",
    "rules",
    "scopes",
    "statuses",
    "tags",
)

_SEARCH_CRITERIAS = _COMMA_CRITERIAS + (
    "createdAfter",
    "createdBefore",
    "createdInLast",
    "createdAt",
    "branch",
    "pullRequest",
    "inNewCodePeriod",
    "sinceLeakPeriod",
    "p",
    "page",
    "ps",
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
    "author",
    "resolved",
    "files",
    "directories",
)

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
        self._debt: Optional[int] = None
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
            branch = f"&pullRequest={requests.utils.quote(self.pull_request)}"
        return f"{self.base_url(local=False)}/project/issues?id={self.projectKey}{branch}&issues={self.key}"

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
        if self.endpoint.version() >= c.MQR_INTRO_VERSION:
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

    def _load(self, data: ApiPayload, from_export: bool = False) -> None:
        """Loads the issue from a JSON payload"""
        super()._load(data, from_export)
        self.hash = data.get("hash", None)
        self.severity = data.get("severity", None)
        if not self.rule:
            self.rule = data.get("rule", None)
        self.type = data.get("type", None)
        self.branch, self.pull_request = self.get_branch_and_pr(data)
        if self.endpoint.version() >= c.MQR_INTRO_VERSION:
            self.impacts = {i["softwareQuality"]: i["severity"] for i in data.get("impacts", {})}
        else:
            self.impacts = {
                idefs.TYPE_QUALITY_MAPPING[data.get("type", idefs.TYPE_NONE)]: idefs.SEVERITY_MAPPING[data.get("severity", idefs.SEVERITY_NONE)]
            }

    def changelog(self, after: Optional[datetime] = None, manual_only: Optional[bool] = True) -> dict[str, changelog.Changelog]:
        """
        :param Optional[datetime] after: If set, only changes after that date are returned
        :param Optional[bool] manual_only: Whether the only manual changes should be returned or all changes, defaults to True
        :return: The issue changelog
        :rtype: dict{"<date>_<sequence_nbr>": Changelog}
        """
        if self._changelog is None:
            data = json.loads(self.get("issues/changelog", {"issue": self.key, "format": "json"}).text)
            # util.json_dump_debug(data["changelog"], f"{str(self)} Changelog = ")
            self._changelog = {}
            seq = 1
            for l in data["changelog"]:
                d = changelog.Changelog(l, self)
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
                self._changelog[f"{d.date_str()}_{seq:03d}"] = d
        if after is not None:
            return {k: v for k, v in self._changelog.items() if v.date_time() > after}
        return self._changelog

    def comments(self, after: Optional[datetime] = None) -> dict[str, str]:
        """
        :param Optional[datetime] after: If set will only return comments after this date, else all
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
                    "date": datetime.strptime(cmt["createdAt"], "%Y-%m-%dT%H:%M:%S%z"),
                    "event": "comment",
                    "value": cmt["markdown"],
                    "user": cmt["login"],
                    "userName": cmt["login"],
                }
        if after is not None:
            return {k: v for k, v in self._comments.items() if v["date"] and v["date"] > after}
        return self._comments

    def add_comment(self, comment: str) -> bool:
        """Adds a comment to an issue

        :param str comment: The comment to add
        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.debug("Adding comment '%s' to %s", comment, str(self))
        try:
            return self.post("issues/add_comment", {"issue": self.key, "text": comment}).ok
        except exceptions.SonarException:
            return False

    def __set_severity(self, **params) -> bool:
        log.debug("Changing severity of %s from '%s' to '%s'", str(self), self.severity, str(params))
        r = self.post("issues/set_severity", {"issue": self.key, **params})
        return r.ok

    def set_severity(self, severity: str) -> bool:
        """Changes the standard severity of an issue

        :param str severity: The comment to add
        :return: Whether the operation succeeded
        """
        if self.endpoint.is_mqr_mode():
            log.error("Can't change issue standard severity, the SonarQube Server or Cloud instance is in MQR mode")
            return False
        success = self.__set_severity(severity=severity)
        if success:
            self.severity = severity
        return success

    def set_mqr_severity(self, software_quality: str, severity: str) -> bool:
        """Changes the severity of an issue

        :param str software_quality: The software quality to set
        :param str severity: The severity to set
        :return: Whether the operation succeeded
        """
        if self.endpoint.is_sonarcloud():
            log.error("Can't change issue MQR severity, this is not supported by SonarQube Cloud")
            return False
        elif not self.endpoint.is_mqr_mode():
            log.error("Can't change issue MQR severity, the SonarQube Server instance is not in MQR mode")
            return False
        else:
            return self.__set_severity(impact=f"{software_quality}={severity}")

    def assign(self, assignee: Optional[str] = None) -> bool:
        """Assigns an issue to a user

        :param str assignee: The user login, set to None to unassign the issue
        :return: Whether the operation succeeded
        """
        try:
            params = util.remove_nones({"issue": self.key, "assignee": assignee})
            log.debug("Assigning %s to '%s'", str(self), str(assignee))
            if ok := self.post("issues/assign", params).ok:
                self.assignee = assignee
        except exceptions.SonarException:
            return False
        else:
            return ok

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
        return self.set_tags((self._tags or []) + [tag])

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
        """
        if self.endpoint.is_mqr_mode():
            raise exceptions.UnsupportedOperation("Changing issue type is not supported in MQR mode")
        log.debug("Changing type of issue %s from %s to %s", self.key, self.type, new_type)
        if ok := self.post("issues/set_type", {"issue": self.key, "type": new_type}).ok:
            self.type = new_type
        return ok

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
        if self.endpoint.version() >= c.ACCEPT_INTRO_VERSION or self.endpoint.is_sonarcloud():
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
            std_severity, mqr_severity = data
            if self.endpoint.is_mqr_mode():
                if mqr_severity is None:
                    log.warning("Original issue severity was in standard experience, converting to MQR on target")
                    severity = idefs.std_to_mqr_severity(std_severity)
                    sw_quality = idefs.QUALITY_MAINTAINABILITY  # TODO: Find a more accurate quality than hardcoding MAINTAINABILITY
                else:
                    sw_quality, severity = mqr_severity.split(":")
                self.set_mqr_severity(sw_quality, severity)
                if self.endpoint.is_sonarcloud():
                    self.add_comment(
                        f"Original issue severity was changed to {sw_quality}={severity}, but MQR severity change is not supported in SonarQube Cloud"
                    )
            else:
                self.set_severity(std_severity)
                # self.add_comment(f"Change of severity {origin}", settings[SYNC_ADD_COMMENTS])
                if self.endpoint.is_sonarcloud():
                    self.add_comment(
                        f"Original issue severity was changed to {std_severity}, but standard severity change is deprecated in SonarQube Cloud"
                    )
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
                if u:
                    self.assign(u)
                # self.add_comment(f"Issue assigned {origin}", settings[SYNC_ADD_COMMENTS])
        elif event_type == "UNASSIGN":
            self.unassign()
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

    def apply_changelog(self, source_issue: Issue, settings: ConfigSettings) -> int:
        """
        Applies a changelog and comments from a source to a target issue
        :param Issue source_hotspot: The source issues to take changes from
        :return: Number of changes applied
        """
        counter = 0
        last_target_change = self.last_changelog_date()
        events = source_issue.changelog(after=last_target_change, manual_only=True)
        if len(events) == 0:
            log.info("Source %s has no changelog added after target %s last change (%s), no changelg applied", source_issue, self, last_target_change)
        else:
            log.info("Applying %d changelogs of %s to %s, from %s", len(events), source_issue, self, last_target_change)
            # Apply all tags at once, plus synchronized tag
            for key in sorted(events.keys()):
                if events[key] != "TAG":
                    self.__apply_event(events[key], settings)
                    counter += 1

        last_target_change = self.last_comment_date()
        events = source_issue.comments(after=last_target_change)
        if len(events) == 0:
            log.info("Source %s has no comments added after target %s last change (%s), no comment added", source_issue, self, last_target_change)
        else:
            log.info("Applying %d comments of %s to %s, from %s", len(events), source_issue, self, last_target_change)
            for key in sorted(events.keys()):
                self.add_comment(events[key]["value"])
                counter += 1
        return counter


# ------------------------------- Static methods --------------------------------------


def component_search_field(endpoint: pf.Platform) -> str:
    """Returns the fields used for issues/search filter by porject key"""
    return _NEW_SEARCH_COMPONENT_FIELD if endpoint.version() >= c.NEW_ISSUE_SEARCH_INTRO_VERSION else _OLD_SEARCH_COMPONENT_FIELD


def type_search_field(endpoint: pf.Platform) -> str:
    return _OLD_SEARCH_TYPE_FIELD if endpoint.is_mqr_mode() else _NEW_SEARCH_TYPE_FIELD


def severity_search_field(endpoint: pf.Platform) -> str:
    return _OLD_SEARCH_SEVERITY_FIELD if endpoint.is_mqr_mode() else _NEW_SEARCH_SEVERITY_FIELD


def status_search_field(endpoint: pf.Platform) -> str:
    return _OLD_SEARCH_STATUS_FIELD if endpoint.is_mqr_mode() else _NEW_SEARCH_STATUS_FIELD


def search_by_directory(endpoint: pf.Platform, params: ApiParams) -> dict[str, Issue]:
    """Searches issues splitting by directory to avoid exceeding the 10K limit"""
    new_params = pre_search_filters(endpoint, params)
    proj_key = new_params.get("project", new_params.get(component_search_field(endpoint), None))
    log.info("Splitting search by directories with %s", str(new_params))
    facets = _get_facets(endpoint=endpoint, project_key=proj_key, facets="directories", params=new_params)
    log.debug("Facets %s", util.json_dump(facets))
    issue_list = {}
    for d in facets["directories"]:
        try:
            new_params["directories"] = d["val"]
            issue_list.update(search(endpoint=endpoint, params=new_params, raise_error=True))
        except TooManyIssuesError:
            log.info(_TOO_MANY_ISSUES_MSG)
            new_params[component_search_field(endpoint)] = proj_key
            issue_list.update(search_by_file(endpoint=endpoint, params=new_params))
    log.debug("Search by directory ALL: %d issues found", len(issue_list))
    return issue_list


def search_by_file(endpoint: pf.Platform, params: ApiParams) -> dict[str, Issue]:
    """Searches issues splitting by directory to avoid exceeding the 10K limit"""
    new_params = pre_search_filters(endpoint, params)
    proj_key = new_params.get("project", new_params.get(component_search_field(endpoint), None))
    log.info("Splitting search by files with %s", str(new_params))
    facets = _get_facets(endpoint=endpoint, project_key=proj_key, facets="files", params=new_params)
    log.debug("Facets %s", util.json_dump(facets))
    issue_list = {}
    for d in facets["files"]:
        try:
            new_params["files"] = d["val"]
            issue_list.update(search(endpoint=endpoint, params=new_params, raise_error=True))
        except TooManyIssuesError:
            log.error("Too many issues (>10000) in file %s, aborting search issue for this file", f'{proj_key}:{d["val"]}')
            continue
        except exceptions.SonarException as e:
            log.error("Error while searching issues in file %s: %s", f'{proj_key}:{d["val"]}', str(e))
            continue
    log.debug("Search by files ALL: %d issues found", len(issue_list))
    return issue_list


def search_by_type(endpoint: pf.Platform, params: ApiParams) -> dict[str, Issue]:
    """Searches issues splitting by type to avoid exceeding the 10K limit"""
    issue_list = {}
    new_params = pre_search_filters(endpoint, params)
    log.info("Splitting search by issue types")
    types = idefs.MQR_QUALITIES if endpoint.is_mqr_mode() else idefs.STD_TYPES
    for issue_type in types:
        try:
            new_params[type_search_field(endpoint)] = [issue_type]
            issue_list.update(search(endpoint=endpoint, params=new_params))
        except TooManyIssuesError:
            log.info(_TOO_MANY_ISSUES_MSG)
            issue_list.update(search_by_directory(endpoint=endpoint, params=new_params))
    log.debug("Search by type ALL: %d issues found", len(issue_list))
    return issue_list


def search_by_severity(endpoint: pf.Platform, params: ApiParams) -> dict[str, Issue]:
    """Searches issues splitting by severity to avoid exceeding the 10K limit"""
    issue_list = {}
    new_params = pre_search_filters(endpoint, params)
    log.info("Splitting search by severities")
    severities = idefs.MQR_SEVERITIES if endpoint.is_mqr_mode() else idefs.STD_SEVERITIES
    for sev in severities:
        try:
            new_params[severity_search_field(endpoint)] = [sev]
            issue_list.update(search(endpoint=endpoint, params=new_params))
        except TooManyIssuesError:
            log.info(_TOO_MANY_ISSUES_MSG)
            issue_list.update(search_by_type(endpoint=endpoint, params=new_params))
    log.debug("Search by severity ALL: %d issues found", len(issue_list))
    return issue_list


def search_by_date(endpoint: pf.Platform, params: ApiParams, date_start: Optional[date] = None, date_stop: Optional[date] = None) -> dict[str, Issue]:
    """Searches issues splitting by date windows to avoid exceeding the 10K limit"""
    new_params = pre_search_filters(endpoint, params)
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
        new_params.get(component_search_field(endpoint), "None"),
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
            new_params.get(component_search_field(endpoint), "None"),
            len(issue_list),
            util.date_to_string(date_start, False),
            util.date_to_string(date_stop, False),
        )
    return issue_list


def __search_all_by_project(endpoint: pf.Platform, project_key: str, params: ApiParams = None) -> dict[str, Issue]:
    """Search issues by project"""
    log.debug("Searching by project with params %s", params)
    new_params = pre_search_filters(endpoint, params)
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
    params = params or {}
    if project_key is None:
        key_list = projects.search(endpoint).keys()
    else:
        key_list = util.csv_to_list(project_key)
    issue_list = {}
    for k in key_list:
        log.info("Project '%s' issue search with filters %s", k, str(params))
        if endpoint.version() >= (9, 1, 0) and endpoint.edition() in (c.EE, c.DCE) and search_findings:
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
    new_params = pre_search_filters(endpoint, params)
    new_params["ps"] = Issue.MAX_PAGE_SIZE
    try:
        issue_list = search(endpoint=endpoint, params=new_params.copy())
    except TooManyIssuesError:
        log.info(_TOO_MANY_ISSUES_MSG)
        comp_filter = component_search_field(endpoint)
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


def __get_issue_list(endpoint: pf.Platform, data: ApiPayload, params) -> dict[str, Issue]:
    """Returns a list of issues from the API payload"""
    br, pr = params.get("branch", None), params.get("pullRequest", None)
    for i in data["issues"]:
        i["branch"], i["pullRequest"] = br, pr
    return {i["key"]: get_object(endpoint=endpoint, key=i["key"], data=i) for i in data["issues"]}


def __search_page(endpoint: pf.Platform, params: ApiParams, page: int) -> dict[str, Issue]:
    """Searches a page of issues"""
    page_params = params.copy()
    page_params["p"] = page
    log.debug("Issue search params = %s", str(page_params))
    issue_list = __get_issue_list(endpoint, json.loads(endpoint.get(Issue.API[c.SEARCH], params=page_params).text), params=page_params)
    log.debug("Added %d issues in search page %d", len(issue_list), page)
    return issue_list


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
    log.debug("Searching with %s", params)
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

    issue_list = __get_issue_list(endpoint, data, filters)
    if nbr_pages == 1:
        return issue_list

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix="IssueSearch") as executor:
        futures = [executor.submit(__search_page, endpoint, filters, page) for page in range(2, nbr_pages + 1)]
        for future in concurrent.futures.as_completed(futures):
            try:
                issue_list |= future.result(timeout=60)
            except TimeoutError:
                log.error("Timeout exporting issue page after 60 seconds - export may be incomplete.")
            except Exception as e:
                log.error(f"Exception while exporting issue page: str{e} - export may be incomplete.")
    log.debug("Issue search for %s completed with %d issues", str(params), len(issue_list))
    return issue_list


def _get_facets(endpoint: pf.Platform, project_key: str, facets: str = "directories", params: ApiParams = None) -> dict[str, str]:
    """Returns the facets of a search"""
    if not params:
        params = {}
    params.update({component_search_field(endpoint): project_key, "facets": facets, "ps": Issue.MAX_PAGE_SIZE, "additionalFields": "comments"})
    filters = pre_search_filters(endpoint=endpoint, params=params)
    data = json.loads(endpoint.get(Issue.API[c.SEARCH], params=filters).text)
    return {f["property"]: f["values"] for f in data["facets"] if f["property"] in util.csv_to_list(facets)}


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
            added_count = {d["val"]: d["count"] for d in data if d["val"] in ruleset}
            for k, v in added_count.items():
                rulecount[k] = rulecount.get(k, 0) + v
        except Exception as e:
            log.error("%s while counting issues per rule, count may be incomplete", util.error_msg(e))
    return rulecount


def get_object(endpoint: pf.Platform, key: str, data: ApiPayload = None, from_export: bool = False) -> Issue:
    """Returns an issue from its key"""
    o = Issue.CACHE.get(key, endpoint.local_url)
    if not o:
        o = Issue(endpoint=endpoint, key=key, data=data, from_export=from_export)
    return o


def pre_search_filters(endpoint: pf.Platform, params: ApiParams) -> ApiParams:
    """Returns the filtered list of params that are allowed for api/issues/search"""
    if not params:
        return {}
    log.debug("Sanitizing issue search filters %s", str(params))
    comp_filter = component_search_field(endpoint)
    filters = util.dict_remap(original_dict=params, remapping={"project": comp_filter, "application": comp_filter, "portfolio": comp_filter})
    filters = util.dict_subset(util.remove_nones(filters), _SEARCH_CRITERIAS)
    filters = {k: v if k not in _COMMA_CRITERIAS else util.csv_to_list(v) for k, v in filters.items()}
    val_equiv = config.get_issues_search_values_equivalences()
    key_equiv = config.get_issues_search_fields_equivalences()
    filters_to_patch = {k: v for k, v in filters.items() if isinstance(v, (list, set, str, tuple))}
    for k, v in filters_to_patch.items():
        for value_list in val_equiv:
            if any(value in value_list for value in v):
                filters[k] += value_list
        # for k in filters.copy().keys():
        for key_list in [kl for kl in key_equiv if k in kl]:
            for key in key_list:
                filters[key] = filters[k]

    filters = {k: v for k, v in filters.items() if v is not None and (not isinstance(v, (list, set, str, tuple)) or len(v) > 0)}

    old_or_new = "new" if endpoint.version() >= c.NEW_ISSUE_SEARCH_INTRO_VERSION else "old"
    for field in filters:
        allowed = config.get_issue_search_allowed_values(field, old_or_new)
        if allowed is not None and filters[field] is not None:
            filters[field] = list(set(util.intersection(filters[field], allowed)))

    disallowed = _STD_SEARCH_FIELDS if endpoint.is_mqr_mode() else _MQR_SEARCH_FIELDS
    filters = {k: v for k, v in filters.items() if k not in disallowed}
    # Convert boolean parameter values to strings
    filters = {k: str(v).lower() if isinstance(v, bool) else v for k, v in filters.items()}
    # Convert list parameter values to CSV
    filters = {k: util.list_to_csv(v) for k, v in filters.items() if v}
    log.debug("Sanitized issue search filters %s", str(filters))
    return filters
