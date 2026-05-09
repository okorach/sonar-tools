#
# sonar-tools
# Copyright (C) 2026 Olivier Korach
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

"""Abstraction of SonarQube SCA dependency risks (issue-release pairs)"""

from __future__ import annotations
from typing import Any, Optional, TYPE_CHECKING

import json
from http import HTTPStatus

from sonar.sqobject import SqObject
from sonar.dependency_risk_changelog import DependencyRiskChangelog
import sonar.logging as log
from sonar.util import cache
from sonar import exceptions
import sonar.util.issue_defs as idefs
from sonar.api.manager import ApiOperation as Oper

if TYPE_CHECKING:
    from datetime import datetime
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload, ConfigSettings, ObjectJsonRepr

_MIN_SQ_VERSION = (2025, 4, 0)
_CB_VERSION_OFFSET = 2000
_SUPPORTED_EDITIONS = ("enterprise", "datacenter")
_UNSUPPORTED_VERSION_MSG = "SCA dependency risks require SonarQube Server 2025.4 or later, or SonarQube Cloud"
_UNSUPPORTED_EDITION_MSG = "SCA dependency risks require Enterprise Edition or Data Center Edition"

_DEFAULT_PAGE_SIZE = 500
_CLOSED_STATUSES = ("FIXED", "SAFE")

CSV_FIELDS = (
    "key",
    "projectKey",
    "projectName",
    "type",
    "quality",
    "severity",
    "status",
    "headline",
    "CVE",
    "cvssScore",
    "packageName",
    "packageVersion",
    "packageManager",
    "transitivity",
    "scope",
    "newlyIntroduced",
    "assignee",
    "branch",
    "pullRequest",
    "createdAt",
)

_API_FILTER_PARAMS = (
    "packageManagers",
    "types",
    "qualities",
    "severities",
    "statuses",
    "packageName",
    "vulnerabilityId",
    "newlyIntroduced",
    "direct",
    "productionScope",
    "assignees",
    "assigned",
    "onlyShowConfirmedReachable",
    "sort",
)


def _check_supported(endpoint: Platform) -> None:
    """Raises UnsupportedOperation if the platform does not support SCA dependency risks"""
    if endpoint.is_sonarcloud():
        return
    vers = endpoint.version()
    if vers > (10, 8, 0) and vers[0] < _CB_VERSION_OFFSET:
        vers = (vers[0] + _CB_VERSION_OFFSET, vers[1], vers[2])
    if vers < _MIN_SQ_VERSION:
        raise exceptions.UnsupportedOperation(_UNSUPPORTED_VERSION_MSG)
    if endpoint.edition() not in _SUPPORTED_EDITIONS:
        raise exceptions.UnsupportedOperation(_UNSUPPORTED_EDITION_MSG)


def sca_enabled(endpoint: Platform) -> bool:
    """Returns whether the SCA add-on (SonarQube Advanced Security) is enabled on the platform"""
    try:
        _check_supported(endpoint)
        api, _, _, _ = endpoint.api.get_details(DependencyRisk, Oper.SELF_TEST)
        resp = endpoint.get(api)
    except (exceptions.SonarException, exceptions.UnsupportedOperation):
        return False
    else:
        return resp.ok


def sca_feature_enabled(endpoint: Platform) -> bool:
    """Returns True if SCA is available on the given endpoint via api/v2/sca/feature-enabled."""
    try:
        api, _, _, _ = endpoint.api.get_details(DependencyRisk, Oper.FEATURE_ENABLED)
        resp = endpoint.get(api, mute=(HTTPStatus.NOT_FOUND, HTTPStatus.FORBIDDEN))
        if not resp.ok:
            return False
        data = json.loads(resp.text)
    except (exceptions.SonarException, exceptions.UnsupportedOperation, exceptions.ObjectNotFound):
        return False
    else:
        return data.get("enabled", False)


class DependencyRisk(SqObject):
    """Abstraction of a SonarQube SCA dependency risk (an issue paired with a package release)"""

    CACHE = cache.Cache()

    def __init__(
        self,
        endpoint: Platform,
        data: ApiPayload,
        project_key: Optional[str] = None,
        project_name: Optional[str] = None,
        branch: Optional[str] = None,
        pull_request: Optional[str] = None,
    ) -> None:
        """Builds a DependencyRisk from a single issuesReleases entry."""
        self.id: str = data["id"]
        self.key: str = data.get("key", data["id"])
        super().__init__(endpoint, data)

        self.severity: Optional[str] = data.get("severity")
        api_type: str = data.get("type", "")
        self.type: str = idefs.SCA_API_TYPE_MAPPING.get(api_type, api_type)
        self.quality: Optional[str] = data.get("quality")
        self.status: Optional[str] = data.get("status")
        self.created_at: Optional[str] = data.get("createdAt")
        self.vulnerability_id: Optional[str] = data.get("vulnerabilityId")
        self.cvss_score: Optional[str] = data.get("cvssScore")
        self.spdx_license_id: Optional[str] = data.get("spdxLicenseId")

        assignee = data.get("assignee") or {}
        self.assignee: Optional[str] = assignee.get("login") if isinstance(assignee, dict) else assignee

        release = data.get("release") or {}
        self.package_name: Optional[str] = release.get("packageName") or data.get("packageName")
        self.package_version: Optional[str] = release.get("version") or data.get("version")
        package_manager = release.get("packageManager")
        self.package_manager: Optional[str] = package_manager.lower() if package_manager else None
        self.package_url: Optional[str] = release.get("packageUrl")
        self.license_expression: Optional[str] = release.get("licenseExpression")
        self.transitivity: str = "DIRECT" if release.get("directSummary") else "TRANSITIVE"
        self.scope: str = "PRODUCTION" if release.get("productionScopeSummary") else "TEST"
        self.newly_introduced: bool = bool(release.get("newlyIntroduced", False))

        # Sync-related state
        self.transitions: list[str] = data.get("transitions", [])
        self.actions: list[str] = data.get("actions", [])
        self._changelog: Optional[dict[str, DependencyRiskChangelog]] = None
        self._comments: Optional[dict[str, dict[str, Any]]] = None
        self._sync_source_url: str = ""

        self.project_key: Optional[str] = project_key or data.get("projectKey")
        self.project_name: Optional[str] = project_name
        self.branch: Optional[str] = branch or data.get("branchKey")
        self.pull_request: Optional[str] = pull_request or data.get("pullRequestKey")

        self.headline: str = self._compute_headline()
        self.__class__.CACHE.put(self)

    def _compute_headline(self) -> str:
        """Returns a short human-readable description of the risk."""
        pkg = self.package_name or "?"
        version = self.package_version or "?"
        if self.type == idefs.SCA_TYPE_PROHIBITED_LICENCE:
            license_id = self.spdx_license_id or "unknown license"
            return f"Prohibited license {license_id} in {pkg} {version}"
        if self.type == idefs.SCA_TYPE_MALWARE:
            return f"Malware {self.vulnerability_id or ''} in {pkg} {version}".strip()
        return f"{self.vulnerability_id or 'Vulnerability'} in {pkg} {version}"

    def __str__(self) -> str:
        return f"dependency risk '{self.key}' ({self.type})"

    def url(self) -> str:
        """Returns the permalink to the dependency risk in the SonarQube UI."""
        base = self.endpoint.local_url
        params = [f"id={self.id}", f"projectKey={self.project_key}"]
        if self.pull_request:
            params.append(f"pullRequest={self.pull_request}")
        elif self.branch:
            params.append(f"branch={self.branch}")
        return f"{base}/dependency-risks/issue?{'&'.join(params)}"

    def to_json(self, without_time: bool = False) -> ObjectJsonRepr:
        """Returns the dependency risk as a JSON-serializable dict."""
        del without_time  # accepted for protocol parity with Finding.to_json
        data = {
            "key": self.key,
            "type": self.type,
            "quality": self.quality,
            "severity": self.severity,
            "status": self.status,
            "headline": self.headline,
            "CVE": self.vulnerability_id,
            "cvssScore": self.cvss_score,
            "spdxLicenseId": self.spdx_license_id,
            "packageName": self.package_name,
            "packageVersion": self.package_version,
            "packageManager": self.package_manager,
            "packageUrl": self.package_url,
            "transitivity": self.transitivity,
            "scope": self.scope,
            "newlyIntroduced": self.newly_introduced,
            "assignee": self.assignee,
            "projectKey": self.project_key,
            "projectName": self.project_name,
            "branch": self.branch,
            "pullRequest": self.pull_request,
            "createdAt": self.created_at,
            "url": self.url(),
        }
        return {k: v for k, v in data.items() if v is not None and v != ""}

    def to_csv(self, without_time: bool = False) -> list[str]:
        """Returns the dependency risk as a CSV row matching csv_header()."""
        del without_time
        data = self.to_json()
        return [str(data.get(field, "")) for field in CSV_FIELDS]

    @classmethod
    def csv_header(cls) -> list[str]:
        """Returns the CSV header row for dependency risk export."""
        return list(CSV_FIELDS)

    def to_sarif(self, full: bool = True) -> dict[str, Any]:
        """Returns the dependency risk in SARIF format."""
        rule_id = self.vulnerability_id or self.spdx_license_id or self.key
        level = "error" if self.severity in ("BLOCKER", "CRITICAL", "HIGH") else "warning"
        sarif: dict[str, Any] = {
            "level": level,
            "ruleId": rule_id,
            "message": {"text": self.headline},
            "properties": {"url": self.url()},
            "locations": [{"logicalLocations": [{"name": self.package_name or "", "kind": "package"}]}],
        }
        if full:
            props = self.to_json()
            for redundant in ("url",):
                props.pop(redundant, None)
            sarif["properties"].update(props)
        return sarif

    @classmethod
    def search(
        cls, endpoint: Platform, project_key: str, branch: Optional[str] = None, pull_request: Optional[str] = None, **search_params: Any
    ) -> dict[str, DependencyRisk]:
        """Searches dependency risks for a project, optionally on a branch or pull request.

        Pages through `api/v2/sca/issues-releases` and returns a dict keyed by risk key.

        :raises UnsupportedOperation: if the platform does not support SCA dependency risks
        """
        _check_supported(endpoint)
        log.info("Searching dependency risks for project '%s' branch=%s pr=%s", project_key, branch, pull_request)

        api_params: dict[str, Any] = {"projectKey": project_key}
        if branch:
            api_params["branchKey"] = branch
        if pull_request:
            api_params["pullRequestKey"] = pull_request
        for param in _API_FILTER_PARAMS:
            if param in search_params and search_params[param] is not None:
                api_params[param] = search_params[param]

        api, _, _, ret = endpoint.api.get_details(cls, Oper.SEARCH)
        results: dict[str, DependencyRisk] = {}
        page_index = 1
        while True:
            page_params = dict(api_params)
            page_params["pageIndex"] = page_index
            page_params["pageSize"] = _DEFAULT_PAGE_SIZE
            payload = json.loads(endpoint.get(api, params=page_params).text)
            project_name = cls._lookup_project_name(payload, project_key)
            for entry in payload.get(ret, []):
                risk = cls(endpoint, entry, project_key=project_key, project_name=project_name, branch=branch, pull_request=pull_request)
                results[risk.key] = risk
            page_info = payload.get("page", {})
            total = int(page_info.get("total", 0))
            page_size = int(page_info.get("pageSize", _DEFAULT_PAGE_SIZE)) or _DEFAULT_PAGE_SIZE
            if page_index * page_size >= total:
                break
            page_index += 1
        log.info("Found %d dependency risks for project '%s'", len(results), project_key)
        return results

    @staticmethod
    def _lookup_project_name(payload: ApiPayload, project_key: str) -> Optional[str]:
        """Extracts the project display name from the issues-releases response 'branches' array."""
        for br in payload.get("branches", []) or []:
            if br.get("projectKey") == project_key and br.get("projectName"):
                return br.get("projectName")
        return None

    # ---------------------------------------------------------------------
    # Sync-related API: changelog, comments, transitions, assignment
    # ---------------------------------------------------------------------

    def changelog(self, after: Optional[datetime] = None) -> dict[str, DependencyRiskChangelog]:
        """Returns the changelog of a dependency risk, optionally filtered to entries after a date."""
        if self._changelog is None:
            self._load_changelog_and_comments()
        if after is not None:
            return {k: v for k, v in self._changelog.items() if v.date_time() > after}
        return self._changelog

    def comments(self, after: Optional[datetime] = None) -> dict[str, dict[str, Any]]:
        """Returns comments extracted from the changelog."""
        if self._comments is None:
            self._load_changelog_and_comments()
        if after is not None:
            return {k: v for k, v in self._comments.items() if v["date"] and v["date"] > after}
        return self._comments

    def _load_changelog_and_comments(self) -> None:
        """Loads both changelog and comments from the API in a single call."""
        api, _, _, ret = self.endpoint.api.get_details(self, Oper.GET_CHANGELOG, key=self.key)
        data = json.loads(self.get(api).text)
        self._changelog = {}
        self._comments = {}
        seq = 1
        for payload in data.get(ret, []):
            entry = DependencyRiskChangelog(payload)
            seq += 1
            if entry.is_comment():
                self._comments[f"{entry.date_str()}_{seq:03d}"] = {
                    "date": entry.date_time(),
                    "event": "comment",
                    "value": entry.comment_text(),
                    "user": entry.author(),
                    "commentKey": payload.get("key"),
                }
            elif not entry.is_technical_change():
                self._changelog[f"{entry.date_str()}_{seq:03d}"] = entry

    def add_comment(self, comment: str) -> bool:
        """Adds a comment to a dependency risk."""
        log.debug("Adding comment to %s", str(self))
        try:
            api, _, params, _ = self.endpoint.api.get_details(self, Oper.ADD_COMMENT, issueReleaseKey=self.key, comment=comment)
            self.post(api, params=params)
        except exceptions.SonarException:
            return False
        else:
            self._comments = None
            return True

    def delete_comment(self, comment_key: str) -> bool:
        """Deletes a comment from a dependency risk."""
        log.debug("Deleting comment %s from %s", comment_key, str(self))
        try:
            api, _, params, _ = self.endpoint.api.get_details(self, Oper.DELETE_COMMENT, key=self.key, issueReleaseChangeKey=comment_key)
            self.endpoint.delete(api, params=params)
        except exceptions.SonarException:
            return False
        else:
            self._comments = None
            return True

    def get_tags(self) -> list[str]:
        """Returns tags - not applicable for dependency risks."""
        raise exceptions.UnsupportedOperation("DependencyRisk does not support tags")

    def set_tags(self, tags: list[str]) -> bool:  # noqa: ARG002
        """Sets tags - not applicable for dependency risks."""
        raise exceptions.UnsupportedOperation("DependencyRisk does not support tags")

    def is_closed(self) -> bool:
        """Returns whether the dependency risk is in a closed status"""
        return self.status in _CLOSED_STATUSES

    def has_changelog(self, after: Optional[datetime] = None, manual_only: Optional[bool] = True) -> bool:  # noqa: ARG002
        """Returns whether the dependency risk has a changelog"""
        return len(self.changelog(after=after)) > 0

    def has_comments(self, after: Optional[datetime] = None) -> bool:
        """Returns whether the dependency risk has comments"""
        return len(self.comments(after=after)) > 0

    def last_changelog_date(self) -> Optional[datetime]:
        """Returns the date of the last changelog entry"""
        ch = self.changelog()
        return list(ch.values())[-1].date_time() if len(ch) > 0 else None

    def last_comment_date(self) -> Optional[datetime]:
        """Returns the date of the last comment"""
        ch = self.comments()
        return list(ch.values())[-1]["date"] if len(ch) > 0 else None

    def modifiers(self, after: Optional[datetime] = None) -> set[str]:
        """Returns the set of users that modified the dependency risk"""
        return {c.author() for c in self.changelog(after=after).values() if c.author()}

    def commenters(self) -> set[str]:
        """Returns the set of users that commented on the dependency risk"""
        return {v["user"] for v in self.comments().values() if v.get("user")}

    def strictly_identical_to(self, other: DependencyRisk, ignore_component: bool = False) -> bool:  # noqa: ARG002
        """Two dependency risks are identical if they share the same identity fields.

        For prohibited-license risks: match on package_url + license_expression + spdx_license_id.
        For other types: match on package_url + vulnerability_id.
        """
        if self.key == other.key:
            return True
        if self.type == idefs.SCA_TYPE_PROHIBITED_LICENCE:
            is_match = (
                self.type == other.type
                and self.package_url == other.package_url
                and self.license_expression == other.license_expression
                and self.spdx_license_id == other.spdx_license_id
            )
        else:
            is_match = self.type == other.type and self.package_url == other.package_url and self.vulnerability_id == other.vulnerability_id
        log.log(log.INFO if is_match else log.DEBUG, "Comparing %s and %s - Match = %s", str(self), str(other), is_match)
        return is_match

    def search_siblings(
        self, findings_list: list[DependencyRisk], ignore_component: bool = False
    ) -> tuple[list[DependencyRisk], list[DependencyRisk], list[DependencyRisk]]:
        """Finds matching dependency risks in a target list.

        Returns (exact_matches, approx_matches, modified_matches). Dependency risks don't have
        approximate matches, so that list is always empty.
        """
        exact_matches = []
        modified_matches = []
        last_change = self.last_changelog_date()

        for dr in findings_list:
            if dr is self:
                continue
            if self.strictly_identical_to(dr, ignore_component):
                if dr.last_changelog_date() is None or (last_change is not None and dr.last_changelog_date() < last_change):
                    exact_matches.append(dr)
                else:
                    modified_matches.append(dr)

        log.info(
            "%s: Found %d exact matches and %d modified matches in target list of size %d",
            self,
            len(exact_matches),
            len(modified_matches),
            len(findings_list),
        )
        return exact_matches, [], modified_matches

    def __apply_event(self, event: DependencyRiskChangelog, settings: ConfigSettings) -> bool:
        """Applies a single changelog event to this dependency risk."""
        from sonar import syncer, users

        (event_type, data) = event.changelog_type()
        log.debug("Applying SCA event type %s - %s to %s", event_type, data, str(self))

        if event_type == "STATUS" and data:
            return self._apply_status_change(data, source_url=self._sync_source_url)
        if event_type == "SEVERITY" and data:
            return self._apply_severity_change(data)
        if event_type == "ASSIGN" and data:
            return self._apply_assignment(data, settings, syncer, users)

        log.debug("SCA event %s not applied to %s", str(event), str(self))
        return False

    def _sca_patch(self, operation: Oper, **kwargs: Any) -> None:
        """Performs a PATCH call to an SCA API with the correct content type."""
        api, _, params, _ = self.endpoint.api.get_details(self, operation, **kwargs)
        ct = self.endpoint.api.content_type(self, operation)
        self.patch(api, params=params, content_type=ct)

    def _apply_status_change(self, status: str, source_url: str = "") -> bool:
        """Applies a status transition."""
        transition = status.upper()
        comment = f"Automatically synchronized from [this original dependency risk]({source_url})"
        if not source_url:
            comment = "sonar-findings-sync automatic transition"
        try:
            self._sca_patch(Oper.CHANGE_STATUS, issueReleaseKey=self.key, transitionKey=transition, comment=comment)
        except exceptions.SonarException as e:
            log.warning("Failed to change status of %s to %s: %s", str(self), status, e.message)
            return False
        else:
            return True

    def _apply_severity_change(self, severity: str) -> bool:
        """Applies a severity change."""
        try:
            self._sca_patch(Oper.UPDATE, id=self.key, issueReleaseKey=self.key, severity=severity)
        except exceptions.SonarException as e:
            log.warning("Failed to change severity of %s to %s: %s", str(self), severity, e.message)
            return False
        else:
            return True

    def _apply_assignment(self, assignee_name: str, settings: ConfigSettings, syncer: Any, users: Any) -> bool:
        """Applies an assignee change."""
        if not settings.get(syncer.SYNC_ASSIGN, True):
            return False
        login = users.get_login_from_name(endpoint=self.endpoint, name=assignee_name)
        if not login:
            return False
        try:
            self._sca_patch(Oper.UPDATE_ASSIGNEE, issueReleaseKey=self.key, assigneeLogin=login)
        except exceptions.SonarException as e:
            log.warning("Failed to assign %s to %s: %s", str(self), login, e.message)
            return False
        else:
            return True

    def apply_changelog(self, source: DependencyRisk, settings: ConfigSettings) -> int:
        """Applies changelog and comments from a source dependency risk.

        :param source: The source dependency risk to take changes from
        :return: Number of changes applied
        """
        counter = 0
        self._sync_source_url = source.url()
        last_target_change = self.last_changelog_date()
        events = source.changelog(after=last_target_change)
        if len(events) == 0:
            log.info("Source %s has no changelog after target %s last change (%s)", source, self, last_target_change)
        else:
            log.info("Applying %d changelogs of %s to %s", len(events), source, self)
            for key in sorted(events.keys()):
                self.__apply_event(events[key], settings)
                counter += 1

        last_target_comment = self.last_comment_date()
        comment_events = source.comments(after=last_target_comment)
        if len(comment_events) == 0:
            log.info("Source %s has no comments after target %s last comment (%s)", source, self, last_target_comment)
        else:
            log.info("Applying %d comments of %s to %s", len(comment_events), source, self)
            for key in sorted(comment_events.keys()):
                self.add_comment(comment_events[key]["value"])
                counter += 1
        return counter

    def project(self) -> Any:
        """Returns the project object (needed by syncer for ignore_components check)."""
        from sonar.projects import Project

        return Project.get_object(self.endpoint, self.project_key)


def get_changelogs(dr_list: list[DependencyRisk], added_after: Optional[datetime] = None, threads: int = 8) -> None:  # noqa: ARG001
    """Mass-collects changelogs for dependency risks."""
    for dr in dr_list:
        try:
            dr.has_changelog(after=added_after)
            dr.has_comments(after=added_after)
        except Exception:  # noqa: BLE001, PERF203
            log.error("Error collecting changelog for %s", str(dr))
