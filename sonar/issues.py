#
# sonar-tools
# Copyright (C) 2019-2026 Olivier Korach
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
from typing import Any, Union, Optional, TYPE_CHECKING

import math
from datetime import date, datetime, timedelta
import json
import re
from copy import deepcopy
import concurrent.futures
import requests.utils

import sonar.logging as log
from sonar.util import cache, issue_defs as idefs
import sonar.util.constants as c

from sonar import users, findings, changelog, rules, config, exceptions
from sonar.projects import Project

import sonar.util.misc as util
import sonar.utilities as sutil
from sonar.api.manager import ApiOperation as Oper

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import SearchParams, ApiPayload, ObjectJsonRepr, ConfigSettings

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

_TOO_MANY_ISSUES_MSG = "Too many issues, recursing..."


class TooManyIssuesError(Exception):
    """When a call to api/issues/search returns too many issues."""

    def __init__(self, nbr_issues: int, message: str) -> None:
        """Exception constructor"""
        super().__init__()
        self.nbr_issues = nbr_issues
        self.message = message


class Issue(findings.Finding):
    """Abstraction of the SonarQube 'issue' concept"""

    CACHE = cache.Cache()
    MAX_PAGE_SIZE = 500
    MAX_SEARCH = 10000

    def __init__(self, endpoint: Platform, data: ApiPayload, from_export: bool = False) -> None:
        """Constructor"""
        super().__init__(endpoint, data, from_export=from_export)
        self._debt: Optional[int] = None
        self.__class__.CACHE.put(self)

    def __str__(self) -> str:
        """Returns a string representation of the issue"""
        return f"Issue key '{self.key}'"

    def __format__(self, format_spec: str = "") -> str:
        return (
            f"Key: {self.key} - Type: {self.type} - Severity: {self.severity}"
            f" - File/Line: {self.component}/{self.line} - Rule: {self.rule} - Project: {self.projectKey}"
        )

    @classmethod
    def search_unsafe(cls, endpoint: Platform, threads: int = 8, **search_params: Any) -> dict[str, Issue]:
        """Multi-threaded search of issues

        :param params: Search criteria to narrow down the search or control ordering
        :param int threads: Nbr of parallel threads for search, defaults to 8
        :return: Dictionary of issues found indexed by issue key
        :raises: TooManyIssuesError if more than 10'000 issues found
        """
        log.debug("Searching issues with %s", search_params)
        new_params = {"ps": cls.MAX_PAGE_SIZE} | cls.sanitize_search_params(endpoint=endpoint, **search_params)
        log.debug("Sanitized search params = %s", new_params)

        api, _, api_params, ret = endpoint.api.get_details(cls, Oper.SEARCH, **new_params)
        # Get first page
        dataset = json.loads(endpoint.get(api, params=api_params).text)
        nbr_issues = sutil.nbr_total_elements(dataset)
        nbr_pages = sutil.nbr_pages(dataset)
        log.debug("Number of issues: %d - Nbr pages: %d", nbr_issues, nbr_pages)

        if nbr_pages > 20:
            msg = f"{nbr_issues} issues returned by {api}, this is more than the max {cls.MAX_SEARCH} possible"
            raise TooManyIssuesError(nbr_issues, msg)

        issue_list = cls.json_to_objects(endpoint, dataset[ret], **new_params)
        if nbr_pages == 1:
            return issue_list

        # Get remaining pages
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix="IssueSearch") as executor:
            futures = [executor.submit(cls.search_one_page, endpoint, **(new_params | {"p": page})) for page in range(2, nbr_pages + 1)]
            for future in concurrent.futures.as_completed(futures):
                try:
                    issue_list.update(future.result(timeout=30)[0])
                except Exception as e:
                    log.error(f"{e} for {future}.")
        return issue_list

    @classmethod
    def search(cls, endpoint: Platform, threads: int = 8, **search_params: Any) -> dict[str, Issue]:
        """Search issues overcoming the 10K issue limit by splitting by smaller search chunks

        :param endpoint: The SonarQube platform endpoint
        :param search_params: Search criteria to narrow down the search or control ordering
        :return: Dictionary of issues found indexed by issue key
        :rtype: dict{<key>: <Issue>}
        :raises: TooManyIssuesError if more than 10'000 issues found for the smallest search chunk
        """
        issue_list = {}
        try:
            issue_list = cls.search_unsafe(endpoint, threads=threads, **search_params)
        except TooManyIssuesError as e:
            log.info(e.message)
            search_params = cls.sanitize_search_params(endpoint, **search_params)
            if proj_key := search_params.get(component_search_field(endpoint)):
                search_params.pop(component_search_field(endpoint))
                issue_list = cls.search_by_project(endpoint, project=proj_key, search_findings=True, **search_params)
            else:
                for key in Project.search(endpoint):
                    issue_list |= cls.search_by_project(endpoint, search_findings=True, **(search_params | {"project": key}))
        return issue_list

    @classmethod
    def search_by_project(
        cls, endpoint: Platform, project: Union[str, Project], search_findings: bool = False, **search_params: Any
    ) -> dict[str, Issue]:
        """Search issues by project"""
        if isinstance(project, Project):
            project = project.key
        log.debug("Searching issues by project '%s' from %s", project, search_params)
        new_params = cls.sanitize_search_params(endpoint, **search_params) | {"project": project}
        if endpoint.edition() in (c.EE, c.DCE) and search_findings:
            log.debug("Using export_findings() to speed up issue export")
            issue_list: dict[str, Issue] = findings.export_findings(endpoint, project, new_params.get("branch"), new_params.get("pullRequest"))
        else:
            try:
                issue_list = cls.search_unsafe(endpoint, **new_params)
            except TooManyIssuesError as e:
                log.info(e.message)
                date_start = get_oldest_issue(endpoint, params=new_params)
                date_stop = get_newest_issue(endpoint, params=new_params)
                issue_list = cls.search_by_date(endpoint, date_start=date_start, date_stop=date_stop, **new_params)
        log.debug("Searching issues by project '%s': %d issues found", project, len(issue_list))
        return issue_list

    @classmethod
    def search_by_facet(cls, endpoint: Platform, project: Union[str, Project], facet: str, **search_params: Any) -> dict[str, Issue]:
        """Searches issues splitting by directory to avoid exceeding the 10K limit"""
        if isinstance(project, Project):
            project = project.key
        issue_list: dict[str, Issue] = {}
        for f in _get_facets(endpoint, project, facet=facet, **search_params):
            issue_list |= cls.search_unsafe(endpoint, components=f, **search_params)
        return issue_list

    @classmethod
    def search_by_type(cls, endpoint: Platform, issue_type: str, **search_params: Any) -> dict[str, Issue]:
        """Searches issues splitting by type to avoid exceeding the 10K limit"""
        log.debug("Searching issues by issue type '%s' from %s", issue_type, search_params)
        new_params = cls.sanitize_search_params(endpoint, **search_params) | {type_search_field(endpoint): [issue_type]}
        issue_list = {}
        try:
            issue_list = cls.search_unsafe(endpoint, **new_params)
        except TooManyIssuesError as e:
            log.info(e.message)
            project = new_params.get("project", new_params.get(component_search_field(endpoint), None))
            for f in _get_facets(endpoint, project, facet="directories", **search_params):
                issue_list |= cls.search_by_directory(endpoint, project=project, directory=f, **new_params)
        log.debug("Searching by issue type '%s': %d issues found", issue_type, len(issue_list))
        return issue_list

    @classmethod
    def search_by_directory(cls, endpoint: Platform, project: Union[str, Project], directory: str, **search_params: Any) -> dict[str, Issue]:
        """Searches issues splitting by directory to avoid exceeding the 10K limit"""
        if isinstance(project, Project):
            project = project.key
        log.debug("Searching issues by project '%s' and directory '%s' from %s", project, directory, search_params)
        new_params = cls.sanitize_search_params(endpoint, **search_params) | {component_search_field(endpoint): project, "directories": directory}
        issue_list: dict[str, Issue] = {}
        try:
            issue_list = cls.search_unsafe(endpoint, **new_params)
        except TooManyIssuesError as e:
            log.info(e.message)
            for f in _get_facets(endpoint, project, facet="files", **new_params):
                issue_list |= cls.search_by_file(endpoint, project=project, file=f, **new_params)
        log.debug("Searching issues by project '%s' and directory '%s': %d issues found", project, directory, len(issue_list))
        return issue_list

    @classmethod
    def search_by_file(cls, endpoint: Platform, project: Union[str, Project], file: str, **search_params: Any) -> dict[str, Issue]:
        """Searches issues splitting by directory to avoid exceeding the 10K limit"""
        if isinstance(project, Project):
            project = project.key
        log.debug("Searching issues by file '%s' from %s", file, search_params)
        new_params = cls.sanitize_search_params(endpoint, **search_params) | {component_search_field(endpoint): project, "files": file}
        try:
            issue_list = cls.search_unsafe(endpoint, **new_params)
        except TooManyIssuesError:
            log.error("Too many issues (>%d) in file '%s', aborting search issue for this file", cls.MAX_SEARCH, f"{project}:{file}")
        except exceptions.SonarException as e:
            log.error("Error while searching issues in file '%s': %s", f"{project}:{file}", str(e))
        log.debug("Searching issues by file '%s': %d issues found", file, len(issue_list))
        return issue_list

    @classmethod
    def search_by_severity(cls, endpoint: Platform, severity: str, **search_params: Any) -> dict[str, Issue]:
        """Searches issues splitting by severity to avoid exceeding the 10K limit"""
        log.debug("Searching issues by severity '%s' from %s", severity, search_params)
        issue_list = {}
        new_params = cls.sanitize_search_params(endpoint, **search_params)
        try:
            issue_list = cls.search_unsafe(endpoint, **new_params | {severity_search_field(endpoint): [severity]})
        except TooManyIssuesError as e:
            log.info(e.message)
            types = idefs.MQR_QUALITIES if endpoint.is_mqr_mode() else idefs.STD_TYPES
            for issue_type in types:
                issue_list |= cls.search_by_type(endpoint, issue_type=issue_type, **new_params)
        log.debug("Searching by severity '%s': %d issues found", severity, len(issue_list))
        return issue_list

    @staticmethod
    def get_search_date_range(date_start: Union[datetime, date, None], date_stop: Union[datetime, date, None]) -> dict[str, datetime]:
        """Returns the date range search parameters"""
        date_range: dict[str, datetime] = {}
        if date_start:
            if isinstance(date_start, datetime):
                date_start = date_start.date()
            date_range["createdAfter"] = sutil.date_to_string(date_start, with_time=False)
        if date_stop:
            if isinstance(date_stop, datetime):
                date_stop = date_stop.date()
            date_range["createdBefore"] = sutil.date_to_string(date_stop, with_time=False)
        return date_range

    @classmethod
    def search_by_date(
        cls, endpoint: Platform, date_start: Union[datetime, date, None], date_stop: Union[datetime, date, None], **search_params: Any
    ) -> dict[str, Issue]:
        """Searches issues splitting by date windows to avoid exceeding the 10K limit"""
        new_params = cls.sanitize_search_params(endpoint, **search_params) | cls.get_search_date_range(date_start, date_stop)
        tstart, tstop = new_params.get("createdAfter"), new_params.get("createdBefore")
        log.debug("Searching issues by date between [%s - %s] from %s", tstart, tstop, search_params)
        issue_list = {}
        try:
            issue_list = cls.search_unsafe(endpoint, **new_params)
        except TooManyIssuesError as e:
            log.info(e.message)
            diff = (date_stop - date_start).days
            if diff == 0:
                log.info(_TOO_MANY_ISSUES_MSG)
                severities = idefs.MQR_SEVERITIES if endpoint.is_mqr_mode() else idefs.STD_SEVERITIES
                for severity in severities:
                    issue_list |= cls.search_by_severity(endpoint, severity=severity, **new_params)
            elif diff == 1:
                issue_list = cls.search_by_date(endpoint, date_start=date_start, date_stop=date_start, **new_params)
                issue_list |= cls.search_by_date(endpoint, date_start=date_stop, date_stop=date_stop, **new_params)
            else:
                date_middle = date_start + timedelta(days=diff // 2)
                issue_list = cls.search_by_date(endpoint, date_start=date_start, date_stop=date_middle, **new_params)
                issue_list |= cls.search_by_date(endpoint, date_start=date_middle + timedelta(days=1), date_stop=date_stop, **new_params)
        log.debug("Searching issues by date between [%s - %s]: %d issues found", tstart, tstop, len(issue_list))
        return issue_list

    @classmethod
    def search_first(cls, endpoint: Platform, **search_params: Any) -> Optional[Issue]:
        """
        :return: The first issue of a search, for instance the oldest, if params = s="CREATION_DATE", asc=asc_sort
        :rtype: Issue or None if not issue found
        """
        issue_list, _ = cls.search_one_page(endpoint, **(search_params | {"ps": 1}))
        return None if len(issue_list) == 0 else next(iter(issue_list.values()))

    def url(self) -> str:
        """Returns a permalink URL to the issue in the SonarQube platform"""
        branch = ""
        if self.branch is not None:
            branch = f"&branch={requests.utils.quote(self.branch)}"
        elif self.pull_request is not None:
            branch = f"&pullRequest={requests.utils.quote(self.pull_request)}"
        return f"{self.base_url(local=False)}/project/issues?id={self.projectKey}{branch}&issues={self.key}"

    def debt(self) -> int:
        """Returns the remediation effort of the issue, in minutes"""
        if self._debt is not None:
            return self._debt
        if "debt" in self.sq_json:
            kdays, days, hours, minutes = 0, 0, 0, 0
            debt = self.sq_json["debt"]
            if m := re.search(r"(\d+)kd", debt):
                kdays = int(m.group(1))
            if m := re.search(r"(\d+)d", debt):
                days = int(m.group(1))
            if m := re.search(r"(\d+)h", debt):
                hours = int(m.group(1))
            if m := re.search(r"(\d+)min", debt):
                minutes = int(m.group(1))
            self._debt = ((kdays * 1000 + days) * 24 + hours) * 60 + minutes
        elif "effort" in self.sq_json:
            self._debt = 0
            if self.sq_json["effort"] != "null":
                self._debt = int(self.sq_json["effort"])
        return self._debt

    def to_json(self, without_time: bool = False) -> ObjectJsonRepr:
        """Returns the issue JSON representation"""
        data = super().to_json(without_time)
        if self.endpoint.version() >= c.MQR_INTRO_VERSION:
            data["impacts"] = {elem["softwareQuality"]: elem["severity"] for elem in self.sq_json["impacts"]}
        data["effort"] = self.debt()
        return data

    def refresh(self) -> bool:
        """Refreshes an issue from the SonarQube platform live data

        :return: whether the refresh was successful
        """
        api, _, params, ret = self.endpoint.api.get_details(self, Oper.GET, issues=self.key, additionalFields="_all")
        resp = self.get(api, params=params)
        if resp.ok:
            self.reload(json.loads(resp.text)[ret][0])
        return resp.ok

    def reload(self, data: ApiPayload, from_export: bool = False) -> Issue:
        """Loads the issue from a JSON payload"""
        super().reload(data, from_export)
        self.hash = data.get("hash")
        self.severity = data.get("severity")
        if not self.rule:
            self.rule = data.get("rule")
        self.type = data.get("type")
        self.branch, self.pull_request = self.get_branch_and_pr(data)
        if self.endpoint.version() >= c.MQR_INTRO_VERSION:
            self.impacts = {i["softwareQuality"]: i["severity"] for i in data.get("impacts", {})}
        else:
            self.impacts = {
                idefs.TYPE_QUALITY_MAPPING[data.get("type", idefs.TYPE_NONE)]: idefs.SEVERITY_MAPPING[data.get("severity", idefs.SEVERITY_NONE)]
            }
        return self

    def changelog(self, after: Optional[datetime] = None, manual_only: bool = True) -> dict[str, changelog.Changelog]:
        """Returns the changelog of an issue

        :param after: If set, only changes after that date are returned
        :param manual_only: Whether the only manual changes should be returned or all changes, defaults to True
        :return: The issue changelog
        :rtype: dict{"<date>_<sequence_nbr>": Changelog}
        """
        if self._changelog is None:
            api, _, params, ret = self.endpoint.api.get_details(self, Oper.GET_CHANGELOG, issue=self.key, format="json")
            data = json.loads(self.get(api, params=params).text)
            # util.json_dump_debug(data[ret], f"{str(self)} Changelog = ")
            self._changelog = {}
            seq = 1
            for l in data[ret]:
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

    def comments(self, after: Optional[datetime] = None) -> dict[str, dict[str, Any]]:
        """Returns the comments of an issue

        :param after: Timezone aware datetime, If set will only return comments after this datetime, else all
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
                    "date": util.to_datetime(cmt["createdAt"]),
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

        :param comment: The comment to add
        :return: Whether the operation succeeded
        """
        log.debug("Adding comment '%s' to %s", comment, str(self))
        try:
            api, _, params, _ = self.endpoint.api.get_details(self, Oper.ADD_COMMENT, issue=self.key, text=comment)
            self.post(api, params=params)
            self.refresh()
            self._comments = None
            self.comments()
            return True
        except exceptions.SonarException:
            return False

    def __set_severity(self, **params: Any) -> bool:
        """Changes the severity of an issue, in std experience or MQR depending on params"""
        log.debug("Changing severity of %s from '%s' to '%s'", str(self), self.severity, str(params))
        api, _, api_params, _ = self.endpoint.api.get_details(self, Oper.SET_SEVERITY, issue=self.key, **params)
        r = self.post(api, params=api_params)
        return r.ok

    def set_severity(self, severity: str) -> bool:
        """Changes the standard severity of an issue

        :param severity: The severity to add
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
        """Changes the MQR severity/impact of an issue

        :param software_quality: The software quality to set
        :param severity: The severity to set
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

    def get_tags(self, **kwargs: Any) -> list[str]:
        """Returns the tags of an issue"""
        use_cache = kwargs.get(c.USE_CACHE, True)
        if self._tags is None:
            self._tags = self.sq_json.get("tags")
        if not use_cache or self._tags is None:
            api, _, params, ret = self.endpoint.api.get_details(self, Oper.GET_TAGS, issues=self.key, additionalFields="")
            data = json.loads(self.get(api, params=params).text)
            self.sq_json.update(data[ret][0])
            self._tags = self.sq_json["tags"]
        return self._tags

    def add_tag(self, tag: str) -> bool:
        """Adds a tag to an issue

        :param tag: Tags to add
        :return: Whether the operation succeeded
        """
        log.debug("Adding tag '%s' to %s", tag, str(self))
        return self.set_tags((self._tags or []) + [tag])

    def remove_tag(self, tag: str) -> bool:
        """Removes a tag from an issue

        :param tag: Tag to remove
        :return: Whether the operation succeeded
        """
        log.debug("Removing tag '%s' from %s", tag, str(self))
        self._tags = self._tags or []
        tags = self._tags.copy()
        if tag in self._tags:
            tags.remove(tag)
        return self.set_tags(tags)

    def set_type(self, new_type: str) -> bool:
        """Sets an issue type

        :param new_type: New type of the issue (Can be BUG, VULNERABILITY or CODE_SMELL)
        :raises: UnsupportedOperation if MQR mode (changing type is not supported in that mode)
        :return: Whether the operation succeeded
        """
        if self.endpoint.is_mqr_mode():
            raise exceptions.UnsupportedOperation("Changing issue type is not supported in MQR mode")
        log.debug("Changing type of issue %s from %s to %s", self.key, self.type, new_type)
        api, _, params, _ = self.endpoint.api.get_details(self, Oper.SET_TYPE, issue=self.key, type=new_type)
        if ok := self.post(api, params=params).ok:
            self.type = new_type
        return ok

    def is_wont_fix(self) -> bool:
        """Returns whether the issue status is won't fix"""
        return self.resolution == "WONTFIX"

    def is_accepted(self) -> bool:
        """returns whether the issue status is Accepted"""
        return self.resolution == "ACCEPTED"

    def is_false_positive(self) -> bool:
        """Returns whether the issue status is false positive"""
        return self.resolution in ("FALSE-POSITIVE", "FALSE_POSITIVE")

    def strictly_identical_to(self, another_finding: Issue, ignore_component: bool = False) -> bool:
        """Returns whether 2 issues are strictly identical

        :param ignore_comment: Whether to consider comments or not to consider identical
        """
        return super().strictly_identical_to(another_finding, ignore_component) and (self.debt() == another_finding.debt())

    def almost_identical_to(self, another_finding: Issue, ignore_component: bool = False, **kwargs) -> bool:
        """Returns whether 2 issues are almost identical

        :param ignore_component: Whether to consider the componet or not to consider almost identical
        """
        rule_debt_calc = rules.Rule.get_object(self.endpoint, self.rule).sq_json.get("remFnType", "CONSTANT_ISSUE")
        # Rule that have linear remediation function may have slightly different debt
        return super().almost_identical_to(another_finding, ignore_component, **kwargs) and (
            self.debt() == another_finding.debt() or kwargs.get("ignore_debt", False) or rule_debt_calc != "CONSTANT_ISSUE"
        )

    def reopen(self) -> bool:
        """Re-opens an issue

        :return: Whether the operation succeeded
        """
        log.debug("Reopening %s", str(self))
        return self.do_transition("reopen")

    def mark_as_false_positive(self) -> bool:
        """Sets an issue as false positive

        :return: Whether the operation succeeded
        """
        log.debug("Marking %s as false positive", str(self))
        return self.do_transition("falsepositive")

    def confirm(self) -> bool:
        """Confirms an issue

        :return: Whether the operation succeeded
        """
        log.debug("Confirming %s", str(self))
        return self.do_transition("confirm")

    def unconfirm(self) -> bool:
        """Unconfirms an issue

        :return: Whether the operation succeeded
        """
        log.debug("Unconfirming %s", str(self))
        return self.do_transition("unconfirm")

    def resolve_as_fixed(self) -> bool:
        """Marks an issue as resolved as fixed

        :return: Whether the operation succeeded
        """
        log.debug("Marking %s as fixed", str(self))
        return self.do_transition("resolve")

    def mark_as_wont_fix(self) -> bool:
        """Marks an issue as resolved as won't fix

        :return: Whether the operation succeeded
        """
        transition = "wontfix"
        if self.endpoint.version() >= c.ACCEPT_INTRO_VERSION or self.endpoint.is_sonarcloud():
            log.warning("Marking %s as won't fix is deprecated, using Accept instead", str(self))
            transition = "accept"
        return self.do_transition(transition)

    def accept(self) -> bool:
        """Accepts an issue

        :return: Whether the operation succeeded
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
        """Applies a changelog and comments from a source to a target issue

        :param source_issue: The source issues to take changes from
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

    @classmethod
    def sanitize_search_params(cls, endpoint: Platform, **search_params: Any) -> SearchParams:
        """Returns the sanitized list of params that are allowed for api/issues/search"""
        log.debug("Sanitizing issue search filters %s", search_params)
        params = deepcopy(search_params) | {"additionalFields": "comments"}
        if params == {}:
            return params
        comp_filter = component_search_field(endpoint)
        params = util.dict_remap(original_dict=params, remapping={"project": comp_filter, "application": comp_filter, "portfolio": comp_filter})

        # Remove duplicate entries for params that may have multiple values
        params = {k: list(set(v)) if isinstance(v, (list, set, tuple)) else v for k, v in params.items() if v is not None}

        # Convert params that are comma-separated to lists
        params = {k: v if k not in _COMMA_CRITERIAS else util.csv_to_list(v) for k, v in params.items()}

        # Apply value equivalences between old and new API (on search field names and values)
        val_equiv = config.get_issues_search_values_equivalences()
        key_equiv = config.get_issues_search_fields_equivalences()
        filters_to_patch = {k: v for k, v in params.items() if isinstance(v, (list, set, str, tuple))}
        for k, v in filters_to_patch.items():
            for value_list in val_equiv:
                if any(value in value_list for value in v):
                    params[k] += value_list
            # for k in filters.copy().keys():
            for key_list in [kl for kl in key_equiv if k in kl]:
                for key in key_list:
                    params[key] = params[k]

        params = {k: v for k, v in params.items() if v is not None and (not isinstance(v, (list, set, str, tuple)) or len(v) > 0)}
        old_or_new = "new" if endpoint.version() >= c.NEW_ISSUE_SEARCH_INTRO_VERSION else "old"
        for field in params:
            allowed = config.get_issue_search_allowed_values(field, old_or_new)
            if allowed is not None and params[field] is not None:
                params[field] = list(set(params[field]) & set(allowed))

        disallowed = _STD_SEARCH_FIELDS if endpoint.is_mqr_mode() else _MQR_SEARCH_FIELDS
        params = {k: v for k, v in params.items() if k not in disallowed}

        # Convert boolean parameter values to strings
        params = {k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()}

        # Convert list parameter values to CSV
        params = {k: util.list_to_csv(v) for k, v in params.items() if v}

        log.debug("Sanitized issue search filters %s", str(params))
        return params


# ------------------------------- Static methods --------------------------------------


def component_search_field(endpoint: Platform) -> str:
    """Returns the fields used for issues/search filter by porject key"""
    return _NEW_SEARCH_COMPONENT_FIELD if endpoint.version() >= c.NEW_ISSUE_SEARCH_INTRO_VERSION else _OLD_SEARCH_COMPONENT_FIELD


def type_search_field(endpoint: Platform) -> str:
    return _OLD_SEARCH_TYPE_FIELD if endpoint.is_mqr_mode() else _NEW_SEARCH_TYPE_FIELD


def severity_search_field(endpoint: Platform) -> str:
    return _OLD_SEARCH_SEVERITY_FIELD if endpoint.is_mqr_mode() else _NEW_SEARCH_SEVERITY_FIELD


def status_search_field(endpoint: Platform) -> str:
    return _OLD_SEARCH_STATUS_FIELD if endpoint.is_mqr_mode() else _NEW_SEARCH_STATUS_FIELD


def _get_facets(endpoint: Platform, project_key: str, facet: str = "directories", **search_params: Any) -> list[str]:
    """Returns the facets of a search"""
    search_params = search_params.copy()
    search_params.update({component_search_field(endpoint): project_key, "facets": facet, "ps": Issue.MAX_PAGE_SIZE, "additionalFields": "comments"})
    log.debug("Getting facets for %s with params %s", facet, search_params)
    search_params = Issue.sanitize_search_params(endpoint=endpoint, **search_params)
    log.debug("Filtered search params = %s", search_params)
    api, _, search_params, _ = endpoint.api.get_details(Issue, Oper.SEARCH, **search_params)
    data = json.loads(endpoint.get(api, params=search_params).text)
    facets_d = {f["property"]: f["values"] for f in data["facets"] if f["property"] in util.csv_to_list(facet)}
    return [elem["val"] for elem in facets_d[facet]]


def __get_one_issue_date(endpoint: Platform, asc_sort: str = "false", **search_params: Any) -> Optional[datetime]:
    """Returns the date of one issue found"""
    issue = Issue.search_first(endpoint=endpoint, s="CREATION_DATE", **search_params, asc=asc_sort)
    if not issue:
        return None
    return issue.creation_date


def get_oldest_issue(endpoint: Platform, **search_params: Any) -> Optional[datetime]:
    """Returns the oldest date of all issues found"""
    return __get_one_issue_date(endpoint=endpoint, asc_sort="true", **search_params)


def get_newest_issue(endpoint: Platform, **search_params: Any) -> Optional[datetime]:
    """Returns the newest date of all issues found"""
    return __get_one_issue_date(endpoint=endpoint, asc_sort="false", **search_params)


def count_by_rule(endpoint: Platform, **search_params: Any) -> dict[str, int]:
    """Returns number of issues of a search"""
    nbr_slices = 1
    SLICE_SIZE = 50  # Search rules facets by bulks of 50
    if "rules" in search_params:
        ruleset = search_params.pop("rules")
        nbr_slices = math.ceil(len(ruleset) / SLICE_SIZE)
    params = Issue.sanitize_search_params(endpoint=endpoint, **search_params) | {"ps": 1, "facets": "rules"}
    rulecount = {}
    for i in range(nbr_slices):
        params["rules"] = ",".join(ruleset[i * SLICE_SIZE : min((i + 1) * SLICE_SIZE - 1, len(ruleset))])
        try:
            api, _, api_params, _ = endpoint.api.get_details(Issue, Oper.SEARCH, **params)
            data = json.loads(endpoint.get(api, params=api_params).text)["facets"][0]["values"]
            added_count = {d["val"]: d["count"] for d in data if d["val"] in ruleset}
            for k, v in added_count.items():
                rulecount[k] = rulecount.get(k, 0) + v
        except Exception as e:
            log.error("%s while counting issues per rule, count may be incomplete", sutil.error_msg(e))
    return rulecount
