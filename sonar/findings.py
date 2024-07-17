#
# sonar-tools
# Copyright (C) 2022-2024 Olivier Korach
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
from typing import Union

from queue import Queue
from threading import Thread

import sonar.logging as log
import sonar.sqobject as sq
import sonar.platform as pf

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

_CSV_FIELDS = (
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
)

_CSV_FIELDS_NEW = (
    "key",
    "rule",
    "language",
    "impacts",
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
)

FILTERS = ("statuses", "resolutions", "severities", "languages", "pullRequest", "branch", "tags", "types", "createdBefore", "createdAfter")


class Finding(sq.SqObject):
    """
    Abstraction of the SonarQube "findings" concept.
    A finding is a general concept that can be either an issue or a security hotspot
    """

    def __init__(self, endpoint: pf.Platform, key: str, data: dict[str, str] = None, from_export: bool = False) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.severity = None  #: Severity (str)
        self.type = None  #: Type (str): VULNERABILITY, BUG, CODE_SMELL or SECURITY_HOTSPOT
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

    def _load(self, data: dict[str, str], from_export: bool = False) -> None:
        if data is not None:
            if from_export:
                self._load_from_export(data)
            else:
                self._load_from_search(data)

    def _load_common(self, jsondata: dict[str, str]) -> None:
        if self._json is None:
            self._json = jsondata
        else:
            self._json.update(jsondata)
        self.author = jsondata.get("author", None)
        self.type = jsondata.get("type", None)
        self.severity = jsondata.get("severity", None)

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

    def _load_from_search(self, jsondata: dict[str, str]) -> None:
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
                main_branch = projects.Project.get_object(self.endpoint, self.projectKey).main_branch()
                if main_branch:
                    self.branch = main_branch.name
            else:
                self.branch = re.sub("^BRANCH:", "", self.branch)

    def _load_from_export(self, jsondata: dict[str, str]) -> None:
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
        if "component" in self._json:
            comp = self._json["component"]
            # Hack: Fix to adapt to the ugly component structure on branches and PR
            # "component": "src:sonar/hot.py:BRANCH:somebranch"
            m = re.search("(^.*):BRANCH:", comp)
            if m:
                comp = m.group(1)
            m = re.search("(^.*):PULL_REQUEST:", comp)
            if m:
                comp = m.group(1)
            return comp.split(":")[-1]
        elif "path" in self._json:
            return self._json["path"]
        else:
            log.warning("Can't find file name for %s", str(self))
            return None

    def language(self) -> str:
        """Returns the finding languae"""
        return rules.get_object(endpoint=self.endpoint, key=self.rule).language

    def to_csv(self, separator: str = ",", without_time: bool = False) -> list[str]:
        """
        :param separator: CSV separator, defaults to ","
        :type separator: str, optional
        :return: The finding as CSV
        :rtype: str
        """
        data = self.to_json(without_time)
        data["projectName"] = projects.Project.get_object(endpoint=self.endpoint, key=self.projectKey).name
        if "impacts" in data:
            data["impacts"] = util.quote(", ".join([f"{k}:{v}" for k, v in data["impacts"].items()]), separator)
            return [str(data.get(field, "")) for field in _CSV_FIELDS_NEW]
        else:
            return [str(data.get(field, "")) for field in _CSV_FIELDS]

    def to_json(self, without_time: bool = False) -> dict[str, str]:
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
        status_conversion = {"WONTFIX": "ACCEPTED", "REOPENED": "OPEN", "REMOVED": "CLOSED", "FIXED": "CLOSED"}
        for old, new in status_conversion.items():
            if data["status"] == old:
                data["status"] = new
                break
        for field in _JSON_FIELDS_PRIVATE:
            data.pop(field, None)
        for k in data.copy():
            if data[k] is None or data[k] == "":
                data.pop(k)
        return data

    def to_sarif(self, full: bool = True) -> dict[str, str]:
        """
        :param bool full: Whether all properties of the issues should be exported or only the SARIF ones
        :return: The finding in SARIF format
        :rtype: dict
        """
        data = {"level": "warning", "ruleId": self.rule, "message": {"text": self.message}}
        if self.is_bug() or self.is_vulnerability() or self.severity in ("CRITICAL", "BLOCKER"):
            data["level"] = "error"
        data["properties"] = {"url": self.url()}
        try:
            rg = self._json["textRange"]
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
        return self.type == "VULNERABILITY"

    def is_hotspot(self) -> bool:
        return self.type == "SECURITY_HOTSPOT"

    def is_bug(self) -> bool:
        return self.type == "BUG"

    def is_code_smell(self) -> bool:
        return self.type == "CODE_SMELL"

    def is_security_issue(self) -> bool:
        return self.is_vulnerability() or self.is_hotspot()

    def is_closed(self) -> bool:
        return self.status == "CLOSED"

    def changelog(self) -> bool:
        # Implemented in subclasses, should not reach this
        raise NotImplementedError()

    def comments(self) -> dict[str, str]:
        # Implemented in subclasses, should not reach this
        raise NotImplementedError()

    def has_changelog(self, added_after: datetime.datetime = None) -> bool:
        """
        :return: Whether the finding has a changelog
        :rtype: bool
        """
        # log.debug("%s has %d changelogs", str(self), len(self.changelog()))
        if added_after is not None and added_after > self.modification_date:
            return False
        return len(self.changelog()) > 0

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
        return set([c.author() for c in self.changelog().values()])

    def commenters(self) -> set[str]:
        """
        :return: the set of users that commented the finding
        :rtype: set(str)
        """
        return set([v["user"] for v in self.comments() if "user" in v])

    def can_be_synced(self, user_list: list[str]) -> bool:
        """
        :meta private:
        """
        log.debug(
            "Issue %s: Checking if modifiers %s are different from user %s",
            str(self),
            str(self.modifiers()),
            str(user_list),
        )
        # If no account dedicated to sync is provided, finding can be synced only if no changelog
        if user_list is None:
            log.debug("Allowed user list empty, checking if issue has changelog")
            return not self.has_changelog()
        # Else, finding can be synced only if changes were performed by syncer accounts
        for u in self.modifiers():
            if u not in user_list:
                return False
        return True

    def strictly_identical_to(self, another_finding: Finding, ignore_component: bool = False) -> bool:
        """
        :meta private:
        """
        if self.key == another_finding.key:
            return True
        prelim_check = True
        if self.rule in ("python:S6540"):
            try:
                col1 = self._json["textRange"]["startOffset"]
                col2 = another_finding._json["textRange"]["startOffset"]
                prelim_check = col1 == col2
            except KeyError:
                pass
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
        if self.message == another_finding.message or kwargs.get("ignore_message", False):
            score += 2
        if self.file() == another_finding.file():
            score += 2
        if self.line == another_finding.line or kwargs.get("ignore_line", False):
            score += 1
        if self.component == another_finding.component or ignore_component:
            score += 1
        if self.author == another_finding.author or kwargs.get("ignore_author", False):
            score += 1
        if self.type == another_finding.type or kwargs.get("ignore_type", False):
            score += 1
        if self.severity == another_finding.severity or kwargs.get("ignore_severity", False):
            score += 1
        # Need at least 7 / 9 to match
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
        log.debug("Searching for an exact match of %s", self.uuid())
        for finding in findings_list:
            if self.uuid() == finding.uuid():
                continue
            if finding.strictly_identical_to(self, ignore_component, **kwargs):
                if finding.can_be_synced(allowed_users):
                    log.info("Issues %s and %s are strictly identical and can be synced", self.uuid(), finding.uuid())
                    exact_matches.append(finding)
                else:
                    log.info("Issues %s and %s are strictly identical but target already has changes, cannot be synced", self.uuid(), finding.uuid())
                    match_but_modified.append(finding)
                return exact_matches, approx_matches, match_but_modified

        log.debug("No exact match, searching for an approximate match of %s", self.uuid())
        for finding in findings_list:
            if finding.almost_identical_to(self, ignore_component, **kwargs):
                if finding.can_be_synced(allowed_users):
                    log.info("Issues %s and %s are almost identical and could be synced", self.uuid(), finding.uuid())
                    approx_matches.append(finding)
                else:
                    log.info("Issues %s and %s are almost identical but target already has changes, cannot be synced", self.uuid(), finding.uuid())
                    match_but_modified.append(finding)
            else:
                log.debug("Issues %s and %s are not siblings", self.uuid(), finding.uuid())
        return exact_matches, approx_matches, match_but_modified

    def do_transition(self, transition: str) -> bool:
        return self.post("issues/do_transition", {"issue": self.key, "transition": transition}).ok


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


def to_csv_header() -> list[str]:
    """Returns the list of CSV fields provided by an issue CSV export"""
    # return "# " + separator.join(_CSV_FIELDS)
    return list(_CSV_FIELDS_NEW)


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
