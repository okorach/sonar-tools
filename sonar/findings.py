#
# sonar-tools
# Copyright (C) 2022-2025 Olivier Korach
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
import re
import datetime
from typing import Union, Optional

from queue import Queue
from threading import Thread
from requests import RequestException
import Levenshtein

import sonar.logging as log
import sonar.sqobject as sq
import sonar.platform as pf
from sonar.util import types

import sonar.utilities as util
from sonar import projects, rules

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
)

SEVERITY_NONE = "NONE"

TYPE_VULN = "VULNERABILITY"
TYPE_BUG = "BUG"
TYPE_CODE_SMELL = "CODE_SMELL"
TYPE_HOTSPOT = "SECURITY_HOTSPOT"
TYPE_NONE = "NONE"

QUALITY_SECURITY = "SECURITY"
QUALITY_RELIABILITY = "RELIABILITY"
QUALITY_MAINTAINABILITY = "MAINTAINABILITY"
QUALITY_NONE = "NONE"

# Mapping between old issues type and new software qualities
TYPE_QUALITY_MAPPING = {
    TYPE_CODE_SMELL: QUALITY_MAINTAINABILITY,
    TYPE_BUG: QUALITY_RELIABILITY,
    TYPE_VULN: QUALITY_SECURITY,
    TYPE_HOTSPOT: QUALITY_SECURITY,
    TYPE_NONE: QUALITY_NONE,
}

# Mapping between old and new severities
SEVERITY_MAPPING = {"BLOCKER": "BLOCKER", "CRITICAL": "HIGH", "MAJOR": "MEDIUM", "MINOR": "LOW", "INFO": "INFO", "NONE": "NONE"}

STATUS_MAPPING = {"WONTFIX": "ACCEPTED", "REOPENED": "OPEN", "REMOVED": "CLOSED", "FIXED": "CLOSED"}


class Finding(sq.SqObject):
    """
    Abstraction of the SonarQube "findings" concept.
    A finding is a general concept that can be either an issue or a security hotspot
    """

    def __init__(self, endpoint: pf.Platform, key: str, data: types.ApiPayload = None, from_export: bool = False) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.severity = None  #: Severity (str)
        self.type = None  #: Type (str): VULNERABILITY, BUG, CODE_SMELL or SECURITY_HOTSPOT
        self.impacts = None  #: 10.x MQR mode
        self.author = None  #: Author (str)
        self.assignee = None  #: Assignee (str)
        self.status = None  #: Status (str)
        self.resolution = None  #: Resolution (str)
        self.rule = None  #: Rule Id (str)
        self.projectKey = None  #: Project key (str)
        self._changelog = None
        self._comments = None
        self.line = None  #: Line (int)
        self.component = None
        self.message = None  #: Message
        self.creation_date = None  #: Creation date (datetime)
        self.modification_date = None  #: Last modification date (datetime)
        self.hash = None  #: Hash (str)
        self.branch = None  #: Branch (str)
        self.pull_request = None  #: Pull request (str)
        self._load(data, from_export)

    def _load(self, data: types.ApiPayload, from_export: bool = False) -> None:
        if data is not None:
            if from_export:
                self._load_from_export(data)
            else:
                self._load_from_search(data)

    def _load_common(self, jsondata: types.ApiPayload) -> None:
        if self.sq_json is None:
            self.sq_json = jsondata
        else:
            self.sq_json.update(jsondata)
        self.author = jsondata.get("author", None)
        if "vulnerabilityProbability" in jsondata:
            self.impacts = {QUALITY_SECURITY: jsondata["vulnerabilityProbability"] + "(HOTSPOT)"}
        elif self.endpoint.version() >= (10, 2, 0):
            self.impacts = {i["softwareQuality"]: i["severity"] for i in jsondata["impacts"]}
        else:
            self.impacts = {TYPE_QUALITY_MAPPING[jsondata.get("type", TYPE_NONE)]: SEVERITY_MAPPING[jsondata.get("severity", SEVERITY_NONE)]}
        self.type = jsondata.get("type", TYPE_NONE)
        self.severity = jsondata.get("severity", SEVERITY_NONE)

        self.message = jsondata.get("message", None)
        self.status = jsondata["status"]
        self.resolution = jsondata.get("resolution", None)
        self.rule = jsondata.get("rule", jsondata.get("ruleReference", None))
        self.line = jsondata.get("line", jsondata.get("lineNumber", None))
        if self.line == "null":
            self.line = None
        if self.line is not None:
            try:
                self.line = int(self.line)
            except ValueError:
                pass

    def _load_from_search(self, jsondata: types.ApiPayload) -> None:
        self._load_common(jsondata)
        self.projectKey = jsondata["project"]
        self.creation_date = util.string_to_date(jsondata["creationDate"])
        self.modification_date = util.string_to_date(jsondata["updateDate"])
        self.hash = jsondata.get("hash", None)
        self.component = jsondata.get("component", None)
        self.pull_request = jsondata.get("pullRequest", None)
        if self.pull_request is None:
            self.branch = jsondata.get("branch", None)
            if self.branch is None:
                self.branch = projects.Project.get_object(self.endpoint, self.projectKey).main_branch_name()
            else:
                self.branch = re.sub("^BRANCH:", "", self.branch)

    def _load_from_export(self, jsondata: types.ObjectJsonRepr) -> None:
        self._load_common(jsondata)
        self.projectKey = jsondata["projectKey"]
        self.creation_date = util.string_to_date(jsondata["createdAt"])
        self.modification_date = util.string_to_date(jsondata["updatedAt"])

    def url(self) -> str:
        # Must be implemented in sub classes
        raise NotImplementedError()

    def file(self) -> Union[str, None]:
        """
        :return: The finding full file path, relative to the rpoject root directory
        :rtype: str or None if not found
        """
        if "component" in self.sq_json:
            comp = self.sq_json["component"]
            # Hack: Fix to adapt to the ugly component structure on branches and PR
            # "component": "src:sonar/hot.py:BRANCH:somebranch"
            m = re.search("(^.*):BRANCH:", comp)
            if m:
                comp = m.group(1)
            m = re.search("(^.*):PULL_REQUEST:", comp)
            if m:
                comp = m.group(1)
            return comp.split(":")[-1]
        elif "path" in self.sq_json:
            return self.sq_json["path"]
        else:
            log.warning("Can't find file name for %s", str(self))
            return None

    def language(self) -> str:
        """Returns the finding language"""
        return rules.get_object(endpoint=self.endpoint, key=self.rule).language

    def to_csv(self, without_time: bool = False) -> list[str]:
        """
        :return: The finding attributes as list
        """
        data = self.to_json(without_time)
        data["projectName"] = projects.Project.get_object(endpoint=self.endpoint, key=self.projectKey).name
        if self.endpoint.version() >= (10, 2, 0):
            data["securityImpact"] = self.impacts.get("SECURITY", "")
            data["reliabilityImpact"] = self.impacts.get("RELIABILITY", "")
            data["maintainabilityImpact"] = self.impacts.get("MAINTAINABILITY", "")
            data["otherImpact"] = self.impacts.get("NONE", "")
            data["legacyType"] = data.pop("type", "")
            data["legacySeverity"] = data.pop("severity", "")
            return [str(data.get(field, "")) for field in CSV_EXPORT_FIELDS]
        else:
            return [str(data.get(field, "")) for field in LEGACY_CSV_EXPORT_FIELDS]

    def to_json(self, without_time: bool = False) -> types.ObjectJsonRepr:
        """
        :return: The finding as dict
        :rtype: dict
        """
        fmt = util.SQ_DATETIME_FORMAT
        if without_time:
            fmt = util.SQ_DATE_FORMAT
        data = vars(self).copy()
        for old_name, new_name in _JSON_FIELDS_REMAPPED:
            data[new_name] = data.pop(old_name, None)

        data["file"] = self.file()
        data["creationDate"] = self.creation_date.strftime(fmt)
        data["updateDate"] = self.modification_date.strftime(fmt)
        data["language"] = self.language()
        data["url"] = self.url()
        if data.get("resolution", None):
            data["status"] = data.pop("resolution")
        if self.endpoint.version() >= (10, 2, 0):
            data["status"] = STATUS_MAPPING.get(data["status"], data["status"])
        return {k: v for k, v in data.items() if v is not None and k not in _JSON_FIELDS_PRIVATE}

    def to_sarif(self, full: bool = True) -> dict[str, str]:
        """
        :param bool full: Whether all properties of the issues should be exported or only the SARIF ones
        :return: The finding in SARIF format
        :rtype: dict
        """
        data = {"level": "warning", "ruleId": self.rule, "message": {"text": self.message}}
        if self.is_bug() or self.is_vulnerability() or self.severity in ("CRITICAL", "BLOCKER", "HIGH"):
            data["level"] = "error"
        data["properties"] = {"url": self.url()}
        try:
            rg = self.sq_json["textRange"]
        except KeyError:
            rg = {"startLine": 1, "startOffset": 1, "endLine": 1, "endOffset": 1}
        data["locations"] = [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": f"file:///{self.file()}", "index": 0},
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
        return self.type == "VULNERABILITY" or "SECURITY" in self.impacts

    def is_hotspot(self) -> bool:
        return self.type == "SECURITY_HOTSPOT" or "SECURITY" in self.impacts

    def is_bug(self) -> bool:
        return self.type == "BUG" or "RELIABILITY" in self.impacts

    def is_code_smell(self) -> bool:
        return self.type == "CODE_SMELL" or "MAINTAINABILITY" in self.impacts

    def is_security_issue(self) -> bool:
        return self.is_vulnerability() or self.is_hotspot()

    def is_closed(self) -> bool:
        return self.status == "CLOSED"

    def changelog(self, manual_only: bool = True) -> bool:
        # Implemented in subclasses, should not reach this
        raise NotImplementedError()

    def comments(self) -> dict[str, str]:
        # Implemented in subclasses, should not reach this
        raise NotImplementedError()

    def has_changelog(self, added_after: Optional[datetime.datetime] = None, manual_only: bool = True) -> bool:
        """
        :param manual_only: Whether to check only manual changes
        :return: Whether the finding has a changelog
        :rtype: bool
        """
        # log.debug("%s has %d changelogs", str(self), len(self.changelog()))
        if added_after is not None and added_after > self.modification_date:
            return False
        return len(self.changelog(manual_only)) > 0

    def has_comments(self) -> bool:
        """
        :return: Whether the finding has comments
        :rtype: bool
        """
        return len(self.comments()) > 0

    def modifiers(self) -> set[str]:
        """
        :return: the set of users that modified the finding
        :rtype: set(str)
        """
        return {c.author() for c in self.changelog().values()}

    def commenters(self) -> set[str]:
        """
        :return: the set of users that commented the finding
        :rtype: set(str)
        """
        return {v["user"] for v in self.comments() if "user" in v}

    def can_be_synced(self, user_list: Optional[list[str]]) -> bool:
        """
        :meta private:
        """
        log.debug("%s: Checking if modifiers %s are different from user %s", str(self), str(self.modifiers()), str(user_list))
        # If no account dedicated to sync is provided, finding can be synced only if no changelog
        if user_list is None:
            log.debug("Allowed user list empty, checking if issue has changelog")
            return not self.has_changelog()
        # Else, finding can be synced only if changes were performed by syncer accounts
        return all(u in user_list for u in self.modifiers())

    def strictly_identical_to(self, another_finding: Finding, ignore_component: bool = False) -> bool:
        """
        :meta private:
        """
        if self.key == another_finding.key:
            return True
        prelim_check = True
        if self.rule in ("python:S6540"):
            try:
                col1 = self.sq_json["textRange"]["startOffset"]
                col2 = another_finding.sq_json["textRange"]["startOffset"]
                prelim_check = col1 == col2
            except KeyError:
                pass
        if self.key == "444f6f46-9571-42e1-8ee4-d1171d8b497e":
            log.info("Source: %s / %s / %s / %s ", self.rule, self.hash, self.file(), self.message)
            log.info("Target: %s / %s / %s / %s ", another_finding.rule, another_finding.hash, another_finding.file(), another_finding.message)
        return (
            self.rule == another_finding.rule
            and self.hash == another_finding.hash
            and self.message == another_finding.message
            and self.file() == another_finding.file()
            and (self.component == another_finding.component or ignore_component)
            and prelim_check
        )

    def almost_identical_to(self, another_finding: Finding, ignore_component: bool = False, **kwargs) -> bool:
        """
        :meta private:
        """
        if self.rule != another_finding.rule or self.hash != another_finding.hash:
            return False
        score = 0
        match_msg = " Match"
        if self.message == another_finding.message or kwargs.get("ignore_message", False):
            score += 2
            match_msg += " message +2"
        elif Levenshtein.distance(self.message, another_finding.message, score_cutoff=6) <= 5:
            score += 1
            match_msg += " message +1"
        if self.file() == another_finding.file():
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
        return score >= 7

    def search_siblings(
        self, findings_list: list[Finding], allowed_users: bool = None, ignore_component: bool = False, **kwargs
    ) -> tuple[list[Finding], list[Finding], list[Finding]]:
        """
        :meta private:
        """
        exact_matches = []
        approx_matches = []
        match_but_modified = []
        log.info("Searching for an exact match of %s", str(self))
        for finding in findings_list:
            if self is finding:
                continue
            if finding.strictly_identical_to(self, ignore_component, **kwargs):
                if finding.can_be_synced(allowed_users):
                    log.info("%s and %s are exact match and can be synced", str(self), str(finding))
                    exact_matches.append(finding)
                else:
                    log.info("%s and %s are exact match but target already has changes, cannot be synced", str(self), str(finding))
                    match_but_modified.append(finding)
                return exact_matches, approx_matches, match_but_modified
            # else:
            #    log.debug("%s and %s are not identical", str(self), str(finding))

        log.info("No exact match, searching for an approximate match of %s", str(self))
        for finding in findings_list:
            if finding.almost_identical_to(self, ignore_component, **kwargs):
                if finding.can_be_synced(allowed_users):
                    log.info("%s and %s are approximate match and could be synced", str(self), str(finding))
                    approx_matches.append(finding)
                else:
                    log.info("%s and %s are approximate match but target already has changes, cannot be synced", str(self), str(finding))
                    match_but_modified.append(finding)
            else:
                log.debug("%s and %s do not match at all", str(self), str(finding))
        if len(approx_matches) + len(match_but_modified) == 0:
            log.info("No approximate match found for %s", str(self))
        return exact_matches, approx_matches, match_but_modified

    def do_transition(self, transition: str) -> bool:
        try:
            return self.post("issues/do_transition", {"issue": self.key, "transition": transition}).ok
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"applying transition {transition}")
        return False


def export_findings(endpoint: pf.Platform, project_key: str, branch: str = None, pull_request: str = None) -> dict[str, Finding]:
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
    return projects.Project(key=project_key, endpoint=endpoint).get_findings(branch, pull_request)


def to_csv_header(endpoint: pf.Platform) -> list[str]:
    """Returns the list of CSV fields provided by an issue CSV export"""
    if endpoint.version() >= (10, 2, 0):
        return list(CSV_EXPORT_FIELDS)
    else:
        return list(LEGACY_CSV_EXPORT_FIELDS)


def __get_changelog(queue: Queue[Finding], added_after: datetime.datetime = None) -> None:
    """Collect the changelog and comments of an issue"""
    while not queue.empty():
        findings = queue.get()
        findings.has_changelog(added_after=added_after)
        findings.has_comments()
        queue.task_done()
    log.debug("Queue empty, exiting thread")


def get_changelogs(issue_list: list[Finding], added_after: datetime.datetime = None, threads: int = 8) -> None:
    """Performs a mass, multithreaded collection of finding changelogs (one API call per issue)"""
    if len(issue_list) == 0:
        return
    log.info("Mass changelog collection for %d findings on %d threads", len(issue_list), threads)
    q = Queue(maxsize=0)
    for finding in issue_list:
        q.put(finding)
    for i in range(threads):
        log.debug("Starting issue changelog thread %d", i)
        worker = Thread(target=__get_changelog, args=(q, added_after))
        worker.setDaemon(True)
        worker.setName(f"Changelog{i}")
        worker.start()
    q.join()
