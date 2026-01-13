#
# sonar-tools
# Copyright (C) 2022-2026 Olivier Korach
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
"""Findings abstraction"""

from __future__ import annotations
import concurrent.futures
from typing import Optional, Any, Union, TYPE_CHECKING

import json
import re
import Levenshtein

from sonar.sqobject import SqObject
import sonar.logging as log
from sonar.util import constants as c
from sonar import exceptions

import sonar.util.misc as util
import sonar.utilities as sutil
from sonar import projects, rules
import sonar.util.issue_defs as idefs
from sonar.api.manager import ApiOperation as Oper

if TYPE_CHECKING:
    from sonar.issues import Issue
    from sonar.hotspots import Hotspot
    from sonar.platform import Platform
    from datetime import datetime
    from sonar.util.types import ApiPayload, ObjectJsonRepr
    from sonar.changelog import Changelog

_JSON_FIELDS_REMAPPED = (("pull_request", "pullRequest"), ("_comments", "comments"))

_JSON_FIELDS_PRIVATE = (
    "endpoint",
    "id",
    "_json",
    "_changelog",
    "assignee",
    "hash",
    "sonarqube",
    "creation_date",
    "modification_date",
    "_debt",
    "component",
    "_Hotspot__details",
)

LEGACY_CSV_EXPORT_FIELDS = [
    "key",
    "rule",
    "language",
    "type",
    "severity",
    "status",
    "creationDate",
    "updateDate",
    "projectKey",
    "projectName",
    "branch",
    "pullRequest",
    "file",
    "line",
    "effort",
    "message",
    "author",
    "tags",
]

CSV_EXPORT_FIELDS = (
    "key",
    "rule",
    "language",
    "securityImpact",
    "reliabilityImpact",
    "maintainabilityImpact",
    "otherImpact",
    "status",
    "creationDate",
    "updateDate",
    "projectKey",
    "projectName",
    "branch",
    "pullRequest",
    "file",
    "line",
    "effort",
    "message",
    "author",
    "legacyType",
    "legacySeverity",
    "tags",
)

STATUS_MAPPING = {"WONTFIX": "ACCEPTED", "REOPENED": "OPEN", "REMOVED": "CLOSED", "FIXED": "CLOSED"}


class Finding(SqObject):
    """
    Abstraction of the SonarQube "findings" concept.
    A finding is a general concept that can be either an issue or a security hotspot
    """

    def __init__(self, endpoint: Platform, key: str, data: ApiPayload = None, from_export: bool = False) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.severity = None  # BLOCKER, CRITICAL, MAJOR, MINOR, INFO
        self.type: Optional[str] = None  # VULNERABILITY, BUG, CODE_SMELL or SECURITY_HOTSPOT
        self.impacts: Optional[dict[str, str]] = None  #: 10.x MQR mode
        self.author: Optional[str] = None
        self.assignee: Optional[str] = None
        self.status: Optional[str] = None  # OPEN, CONFIRMED, REOPENED, RESOLVED, CLOSED, ACCEPTED, FALSE_POSITIVE
        self.resolution: Optional[str] = None
        self.rule: Optional[str] = None
        self.projectKey: Optional[str] = None
        self._changelog: Optional[dict[str, Changelog]] = None
        self._comments: Optional[dict[str, dict[str, str]]] = None
        self.file: Optional[str] = None
        self.line: int = 0
        self.component: Optional[str] = None
        self.message: Optional[str] = None  #: Message
        self.creation_date: Optional[datetime] = None  #: Creation date (datetime)
        self.modification_date: Optional[datetime] = None  #: Last modification date (datetime)
        self.hash: Optional[str] = None  #: Hash (str)
        self.branch: Optional[str] = None  #: Branch (str)
        self.pull_request: Optional[str] = None  #: Pull request (str)
        self.reload(data, from_export)

    @classmethod
    def get_object(cls, endpoint: Platform, key: str, data: ApiPayload, from_export: bool = False) -> Union[Issue, Hotspot]:
        """Returns a finding from its key"""
        o: Optional[Union[Issue, Hotspot]] = cls.CACHE.get(endpoint.local_url, key)
        if not o:
            o = cls(endpoint=endpoint, key=key, data=data, from_export=from_export)
        return o

    @staticmethod
    def add_branch_and_pr(findings_list: dict[str, Union[Issue, Hotspot]], **search_params: Any) -> dict[str, Union[Issue, Hotspot]]:
        """Enriches findings with branch and pull request info"""
        for e_key in [elem for elem in ["branch", "pullRequest"] if elem in search_params]:
            e_val = search_params[e_key]
            for finding in findings_list.values():
                finding.sq_json[e_key] = e_val
                if e_key == "branch":
                    finding.branch = e_val
                else:
                    finding.pull_request = e_val
        return findings_list

    @classmethod
    def json_to_objects(cls, endpoint: Platform, dataset: ApiPayload, **search_params: Any) -> dict[str, Union[Issue, Hotspot]]:
        """Returns a list of findings from the API payload"""
        findings_d = {data["key"]: cls.get_object(endpoint=endpoint, key=data["key"], data=data) for data in dataset}
        return cls.add_branch_and_pr(findings_d, **search_params)

    @classmethod
    def search_one_page(cls, endpoint: Platform, **search_params: Any) -> tuple[dict[str, Union[Issue, Hotspot]], dict[str, Any]]:
        """Search one page of hotspots findings"""
        search_params = cls.sanitize_search_params(endpoint, **search_params)
        api, _, api_params, ret = endpoint.api.get_details(cls, Oper.SEARCH, **search_params)
        dataset = json.loads(endpoint.get(api, params=api_params).text)
        findings_d = cls.post_search_filters(cls.json_to_objects(endpoint, dataset[ret], **search_params), **search_params)
        return findings_d, dataset

    @staticmethod
    def post_search_filters(findings: dict[str, Union[Issue, Hotspot]], **filters: Any) -> dict[str, Union[Issue, Hotspot]]:
        return findings

    def reload(self, data: ApiPayload, from_export: bool = False) -> None:
        """Reloads a finding with JSON data"""
        super().reload(data)
        if data is not None:
            if from_export:
                self._load_from_export(data)
            else:
                self._load_from_search(data)

    def _load_common(self, jsondata: ApiPayload) -> None:
        self.author = jsondata.get("author", None)
        self.message = jsondata.get("message", None)
        self.status = jsondata["status"]
        self.resolution = jsondata.get("resolution", None)
        if not self.rule:
            self.rule = jsondata.get("rule", jsondata.get("ruleReference", None))
        try:
            self.line = int(jsondata.get("line", jsondata.get("lineNumber", 0)))
        except ValueError:
            self.line = 0

    def _load_from_search(self, jsondata: ApiPayload) -> None:
        self._load_common(jsondata)
        self.projectKey = jsondata.get("project", None)
        self.component = jsondata.get("component", None)
        self.status = jsondata.get("status", None)
        self.message = jsondata.get("message", None)
        if self.component:
            self.file = self.component.replace(f"{self.projectKey}:", "", 1)
        self.branch, self.pull_request = self.get_branch_and_pr(jsondata)
        self.creation_date = sutil.string_to_date(jsondata["creationDate"])
        self.modification_date = sutil.string_to_date(jsondata["updateDate"])

    def _load_from_export(self, jsondata: ObjectJsonRepr) -> None:
        self._load_common(jsondata)
        self.projectKey = jsondata["projectKey"]
        self.creation_date = sutil.string_to_date(jsondata["createdAt"])
        self.modification_date = sutil.string_to_date(jsondata["updatedAt"])

    def url(self) -> str:
        """Returns the URL of the finding, must be implemented in subclasses"""
        raise NotImplementedError()

    def language(self) -> str:
        """Returns the finding language"""
        try:
            return rules.Rule.get_object(endpoint=self.endpoint, key=self.rule).language
        except exceptions.ObjectNotFound:
            return rules.Rule.get_external_rule(endpoint=self.endpoint, key=self.rule).language

    def to_csv(self, without_time: bool = False) -> list[str]:
        """Returns The finding attributes as list

        :param without_time: Whether to include the time in the date fields
        """
        data = self.to_json(without_time)
        if self.endpoint.is_mqr_mode():
            data["securityImpact"] = data["impacts"].get(idefs.QUALITY_SECURITY, "")
            data["reliabilityImpact"] = data["impacts"].get(idefs.QUALITY_RELIABILITY, "")
            data["maintainabilityImpact"] = data["impacts"].get(idefs.QUALITY_MAINTAINABILITY, "")
            data["otherImpact"] = data["impacts"].get(idefs.QUALITY_NONE, "")
            data.pop("impacts", None)
        data["projectName"] = projects.Project.get_object(endpoint=self.endpoint, key=self.projectKey).name
        fields = CSV_EXPORT_FIELDS if self.endpoint.version() >= c.MQR_INTRO_VERSION else LEGACY_CSV_EXPORT_FIELDS
        return [str(data.get(field, "")) for field in fields]

    def to_json(self, without_time: bool = False) -> ObjectJsonRepr:
        """Returns the finding as dict

        :param without_time: Whether to include the time in the date fields
        """
        fmt = sutil.SQ_DATETIME_FORMAT
        if without_time:
            fmt = sutil.SQ_DATE_FORMAT
        data = vars(self).copy()
        for old_name, new_name in _JSON_FIELDS_REMAPPED:
            data[new_name] = data.pop(old_name, None)
        data["file"] = self.file
        data["creationDate"] = self.creation_date.strftime(fmt)
        data["updateDate"] = self.modification_date.strftime(fmt)
        data["language"] = self.language()
        data["url"] = self.url()
        if data["pullRequest"] is None and data["branch"] is None:
            data["branch"] = projects.Project.get_object(self.endpoint, key=self.projectKey).main_branch_name()
        if data.get("resolution", None):
            data["status"] = data.pop("resolution")
        if self.endpoint.version() >= c.ACCEPT_INTRO_VERSION:
            data["status"] = STATUS_MAPPING.get(data["status"], data["status"])
        if self.endpoint.version() >= c.MQR_INTRO_VERSION:
            data["securityImpact"] = self.impacts.get(idefs.QUALITY_SECURITY, "")
            data["reliabilityImpact"] = self.impacts.get(idefs.QUALITY_RELIABILITY, "")
            data["maintainabilityImpact"] = self.impacts.get(idefs.QUALITY_MAINTAINABILITY, "")
            data["otherImpact"] = self.impacts.get(idefs.QUALITY_NONE, "")
            data["legacyType"] = data.pop("type", "")
            data["legacySeverity"] = data.pop("severity", "")
        data["tags"] = util.list_to_csv(self.sq_json.get("tags", []))
        return {k: v for k, v in data.items() if v is not None and k not in _JSON_FIELDS_PRIVATE}

    def to_sarif(self, full: bool = True) -> dict[str, str]:
        """Returns the finding in SARIF format

        :param full: Whether all properties of the issues should be exported or only the SARIF ones
        :return: The finding in SARIF format
        """
        data = {"level": "warning", "ruleId": self.rule, "message": {"text": self.message}}
        if (
            self.is_bug()
            or self.is_vulnerability()
            or self.severity in (idefs.STD_SEVERITY_BLOCKER, idefs.STD_SEVERITY_CRITICAL, idefs.STD_SEVERITY_MAJOR)
        ):
            data["level"] = "error"
        data["properties"] = {"url": self.url()}
        try:
            rg = self.sq_json["textRange"]
        except KeyError:
            rg = {"startLine": 1, "startOffset": 1, "endLine": 1, "endOffset": 1}
        data["locations"] = [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": f"file:///{self.file}", "index": 0},
                    "region": {
                        "startLine": max(int(rg["startLine"]), 1),
                        "startColumn": max(int(rg["startOffset"]), 1),
                        "endLine": max(int(rg["endLine"]), 1),
                        "endColumn": max(int(rg["endOffset"]), 1),
                    },
                }
            }
        ]
        if full:
            data["properties"].update(self.to_json())
            # Remove props that are already in the std SARIF fields
            for prop in "rule", "file", "line", "message":
                data["properties"].pop(prop, None)
        return data

    def is_vulnerability(self) -> bool:
        return idefs.QUALITY_SECURITY in self.impacts if self.endpoint.is_mqr_mode() else self.type == idefs.TYPE_VULN

    def is_hotspot(self) -> bool:
        return self.type == idefs.TYPE_HOTSPOT

    def is_bug(self) -> bool:
        return idefs.QUALITY_RELIABILITY in self.impacts if self.endpoint.is_mqr_mode() else self.type == idefs.TYPE_BUG

    def is_code_smell(self) -> bool:
        return idefs.QUALITY_MAINTAINABILITY in self.impacts if self.endpoint.is_mqr_mode() else self.type == idefs.TYPE_CODE_SMELL

    def is_security_issue(self) -> bool:
        return self.is_vulnerability() or self.is_hotspot()

    def is_closed(self) -> bool:
        return self.status == "CLOSED"

    def changelog(self, after: Optional[datetime] = None, manual_only: bool = True) -> dict[str, Changelog]:
        # Implemented in subclasses, should not reach this
        raise NotImplementedError()

    def last_changelog_date(self) -> Optional[datetime]:
        """Returns the date of the last changelog entry, or None if no changelog"""
        ch = self.changelog(manual_only=True)
        return list(ch.values())[-1].date_time() if len(ch) > 0 else None

    def comments(self, after: Optional[datetime] = None) -> dict[str, dict[str, Any]]:
        # Implemented in subclasses, should not reach this
        raise NotImplementedError()

    def last_comment_date(self) -> Optional[datetime]:
        """Returns the date of the last comment, or None if no comment"""
        ch = self.comments()
        return list(ch.values())[-1]["date"] if len(ch) > 0 else None

    def assign(self, assignee: Optional[str]) -> bool:
        """Assigns a finding (and optionally comment)

        :param assignee: User login to assign the hotspot, None to unassign
        :return: Whether the operation succeeded
        """
        try:
            if assignee is None:
                log.debug("Unassigning %s", self)
            else:
                log.debug("Assigning %s to '%s'", self, assignee)
            params = {"hotspot": self.key, "issue": self.key, "assignee": assignee}
            api, _, api_params, _ = self.endpoint.api.get_details(self, Oper.ASSIGN, **params)
            if ok := self.post(api, params=api_params).ok:
                self.assignee = assignee
        except exceptions.SonarException:
            return False
        else:
            return ok

    def unassign(self) -> bool:
        """Unassigns a Finding and returns Whether the operation succeeded"""
        return self.assign(assignee=None)

    def has_changelog(self, after: Optional[datetime] = None, manual_only: Optional[bool] = True) -> bool:
        """
        :param Optional[datetime] after: If set, only changelogs after that date will be considered
        :param manual_only: Whether to check only manual changes
        :return: Whether the finding has a changelog
        :rtype: bool
        """
        # log.debug("%s has %d changelogs", str(self), len(self.changelog()))
        if after is not None and after > self.modification_date:
            return False
        return len(self.changelog(after=after, manual_only=manual_only)) > 0

    def has_comments(self, after: Optional[datetime] = None) -> bool:
        """
        :return: Whether the finding has comments
        :rtype: bool
        """
        return len(self.comments(after=after)) > 0

    def modifiers(self, after: Optional[datetime] = None) -> set[str]:
        """
        :return: the set of users that modified the finding
        :rtype: set(str)
        """
        return {c.author() for c in self.changelog(after=after).values()}

    def commenters(self) -> set[str]:
        """
        :return: the set of users that commented the finding
        :rtype: set(str)
        """
        return {v["user"] for v in self.comments() if "user" in v}

    def strictly_identical_to(self, another_finding: Finding, ignore_component: bool = False) -> bool:
        """
        :meta private:
        """
        if self.key == another_finding.key:
            log.debug("%s and %s are the same issue, they have the same key %s", str(self), str(another_finding), self.key)
            return True
        prelim_check = True
        if self.rule in ("python:S6540"):
            try:
                prelim_check = self.sq_json["textRange"]["startOffset"] == another_finding.sq_json["textRange"]["startOffset"]
            except KeyError:
                pass
        identical = (
            self.rule == another_finding.rule
            and self.hash == another_finding.hash
            and self.message == another_finding.message
            and self.file == another_finding.file
            and (self.component == another_finding.component or ignore_component)
            and prelim_check
        )
        log.debug("%s vs %s - identical = %s hash = %s/%s", str(self), str(another_finding), str(identical), self.hash, another_finding.hash)
        return identical

    def almost_identical_to(self, another_finding: Finding, ignore_component: bool = False, **kwargs) -> bool:
        """
        :meta private:
        """
        if self.rule != another_finding.rule:
            return False
        score = 0
        match_msg = " Match"
        if self.message == another_finding.message or kwargs.get("ignore_message", False):
            score += 2
            match_msg += " message +2"
        elif Levenshtein.distance(self.message, another_finding.message, score_cutoff=6) <= 5:
            score += 1
            match_msg += " message +1"
        if self.file == another_finding.file:
            score += 1
            match_msg += " file +1"
        if self.line == another_finding.line or kwargs.get("ignore_line", False):
            score += 1
            match_msg += " line +1"
        if self.component == another_finding.component or ignore_component:
            score += 1
            match_msg += " component +1"
        if self.author == another_finding.author or kwargs.get("ignore_author", False):
            score += 1
            match_msg += " author +1"
        if self.type == another_finding.type or kwargs.get("ignore_type", False):
            score += 1
            match_msg += " type +1"
        if self.severity == another_finding.severity or kwargs.get("ignore_severity", False):
            score += 1
            match_msg += " severity +1"

        log.debug("%s vs %s - %s score = %d", str(self), str(another_finding), match_msg, score)
        # Need at least 7 / 8 to consider it's a match
        # for some reason, rarely the hash may not be the same for 2 issues that are identical
        # In this case we match if the rest of the score is perfectly identical
        return score == 8 or score >= 7 and self.hash == another_finding.hash

    def search_siblings(
        self, findings_list: list[Finding], ignore_component: bool = False, **kwargs
    ) -> tuple[list[Finding], list[Finding], list[Finding]]:
        """
        :meta private:
        """
        exact_matches = []
        approx_matches = []
        match_but_modified = []
        log.debug("Searching for an exact match of %s", str(self))
        candidates = [f for f in findings_list if f is not self and f.strictly_identical_to(self, ignore_component, **kwargs)]
        candidate_match = None
        line_gap = None
        last_change = self.last_changelog_date()
        for finding in candidates:
            if line_gap is None or abs(finding.line - self.line) < line_gap:
                line_gap = abs(finding.line - self.line)
                candidate_match = finding
                log.info("%s and %s are exact match with a line gap of %d", str(self), str(candidate_match), line_gap)
            if line_gap == 0:
                break
        if candidate_match is not None:
            if candidate_match.last_changelog_date() is None or (last_change is not None and candidate_match.last_changelog_date() < last_change):
                log.info("%s and %s are exact match and can be synced", str(self), str(candidate_match))
                exact_matches.append(candidate_match)
            else:
                log.info(
                    "%s and %s are exact match but target has more recent changes than source, cannot be synced", str(self), str(candidate_match)
                )
                match_but_modified.append(candidate_match)
            return exact_matches, approx_matches, match_but_modified

        log.info("No exact match, searching for an approximate match of %s", str(self))
        candidates = [f for f in findings_list if f.almost_identical_to(self, ignore_component, **kwargs)]
        for finding in candidates:
            if finding.last_changelog_date() is None or (last_change is not None and finding.last_changelog_date() < last_change):
                log.info("%s and %s are approximate match and could be synced", str(self), str(finding))
                approx_matches.append(finding)
            else:
                log.info("%s and %s are approximate match but target has more recent changes than source, cannot be synced", str(self), str(finding))
                match_but_modified.append(finding)

        if len(approx_matches) + len(match_but_modified) == 0:
            log.info("No approximate match found for %s", str(self))
        return exact_matches, approx_matches, match_but_modified

    def do_transition(self, transition: str) -> bool:
        try:
            api, _, params, _ = self.endpoint.api.get_details(self, Oper.DO_TRANSITION, issue=self.key, transition=transition)
            return self.post(api, params=params).ok
        except exceptions.SonarException as e:
            if re.match(r"Transition from state [A-Za-z]+ does not exist", e.message):
                raise exceptions.UnsupportedOperation(e.message) from e
            raise

    def get_branch_and_pr(self, data: ApiPayload) -> tuple[Optional[str], Optional[str]]:
        """
        :param data: The data to extract the branch and pull request from
        :return: The branch name or pull request id
        """
        pr = data.get("pullRequest", None)
        branch = None if pr else data.get("branch", projects.Project.get_object(self.endpoint, key=self.projectKey).main_branch_name())
        return branch, pr


def export_findings(endpoint: Platform, project_key: str, branch: Optional[str] = None, pull_request: Optional[str] = None) -> dict[str, Finding]:
    """Export all findings of a given project

    :param Platform endpoint: Reference to the SonarQube platform
    :param project_key: The project key
    :type project_key: str
    :param str branch: Branch to select for export (exclusive of pull_request), defaults to None
    :param str pull_request: Pull request to select for export (exclusive of branch), default to None
    :return: list of Findings (Issues or Hotspots)
    :rtype: dict{<key>: <Finding>}
    """
    log.info("Using new export findings to speed up issue export")
    return projects.Project(key=project_key, endpoint=endpoint).get_findings(branch=branch, pull_request=pull_request)


def to_csv_header(endpoint: Platform) -> list[str]:
    """Returns the list of CSV fields provided by an issue CSV export"""
    if endpoint.version() >= c.MQR_INTRO_VERSION:
        return list(CSV_EXPORT_FIELDS)
    else:
        return list(LEGACY_CSV_EXPORT_FIELDS)


def __get_changelog(finding: Finding, after: Optional[datetime] = None) -> Finding:
    """Collect the changelog and comments of an issue"""
    finding.has_changelog(after=after, manual_only=True)
    finding.has_comments(after=after)
    return finding


def get_changelogs(issue_list: list[Finding], added_after: Optional[datetime] = None, threads: int = 8) -> None:
    """Performs a mass, multithreaded collection of finding changelogs (one API call per issue)"""
    if len(issue_list) == 0:
        return
    count, total = 0, len(issue_list)
    log.info("Mass changelog collection for %d findings on %d threads", total, threads)
    log_frequency = max(total // 50, 100)
    log_frequency = 1000 if log_frequency >= 1000 else 500 if log_frequency >= 500 else 200 if log_frequency >= 200 else 100
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix="GetChangelog") as executor:
        futures = [executor.submit(__get_changelog, finding, added_after) for finding in issue_list]
        for future in concurrent.futures.as_completed(futures):
            try:
                count += 1
                _ = future.result(timeout=30)
                if count % log_frequency == 0 or count == total:
                    log.info("Collected changelog for %d of %d findings (%d%%)", count, total, count * 100 // total)
            except Exception as e:
                log.error(f"Changelog collection error {str(e)} for {str(future)}.")
