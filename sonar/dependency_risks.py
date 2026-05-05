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

"""Abstraction of the SonarQube SCA dependency risk concept"""

from __future__ import annotations
from typing import Optional, Any, TYPE_CHECKING

import json
from http import HTTPStatus

from sonar.sqobject import SqObject
from sonar.dependency_risk_changelog import DependencyRiskChangelog
import sonar.logging as log
import sonar.utilities as sutil
from sonar.api.manager import ApiOperation as Oper
from sonar import exceptions

if TYPE_CHECKING:
    from datetime import datetime
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload, ConfigSettings

_CLOSED_STATUSES = ("FIXED", "SAFE")


class DependencyRisk(SqObject):
    """Abstraction of a SonarQube SCA dependency risk (issue-release)."""

    def __init__(self, endpoint: Platform, data: ApiPayload) -> None:
        """Constructor"""
        self.key = data["key"]
        super().__init__(endpoint, data)
        self.vulnerabilityId: Optional[str] = data.get("vulnerabilityId")
        self.packageName: Optional[str] = data.get("packageName")
        self.version: Optional[str] = data.get("version")
        self.status: Optional[str] = data.get("status")
        self.severity: Optional[str] = data.get("severity")
        self.type: Optional[str] = data.get("type")
        self.spdxLicenseId: Optional[str] = data.get("spdxLicenseId")
        release = data.get("release", {})
        self.packageUrl: Optional[str] = release.get("packageUrl")
        self.licenseExpression: Optional[str] = release.get("licenseExpression")
        self.assignee: Optional[str] = data.get("assignee")
        self.transitions: list[str] = data.get("transitions", [])
        self.actions: list[str] = data.get("actions", [])
        self.projectKey: Optional[str] = data.get("projectKey")
        self.branch: Optional[str] = data.get("branchKey")
        self.pull_request: Optional[str] = data.get("pullRequestKey")
        self._changelog: Optional[dict[str, DependencyRiskChangelog]] = None
        self._comments: Optional[dict[str, dict[str, Any]]] = None
        self._sync_source_url: str = ""

    def __str__(self) -> str:
        """String representation"""
        if self.type == "PROHIBITED_LICENSE":
            return f"DependencyRisk '{self.packageUrl}' {self.type} '{self.spdxLicenseId}'"
        return f"DependencyRisk '{self.packageUrl}' {self.type} '{self.vulnerabilityId}'"

    @classmethod
    def search(
        cls,
        endpoint: Platform,
        project: str,
        branch: Optional[str] = None,
        pull_request: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, DependencyRisk]:
        """Searches dependency risks for a project/branch.

        :return: Dictionary of DependencyRisk keyed by key
        """
        params: dict[str, Any] = {"projectKey": project}
        if branch:
            params["branchKey"] = branch
        if pull_request:
            params["pullRequestKey"] = pull_request
        params.update(kwargs)

        api, _, api_params, ret = endpoint.api.get_details(cls, Oper.SEARCH, **params)
        max_ps = endpoint.api.max_page_size(cls, Oper.SEARCH)
        page_field = endpoint.api.page_field(cls, Oper.SEARCH)
        api_params["pageSize"] = max_ps

        data = json.loads(endpoint.get(api, api_params).text)
        results: dict[str, DependencyRisk] = {}
        for item in data.get(ret, []):
            item["projectKey"] = project
            if branch:
                item["branchKey"] = branch
            if pull_request:
                item["pullRequestKey"] = pull_request
            dr = cls(endpoint, item)
            results[dr.key] = dr

        nb_pages = sutil.nbr_pages(data)
        for page in range(2, nb_pages + 1):
            page_params = {**api_params, page_field: page}
            page_data = json.loads(endpoint.get(api, page_params).text)
            for item in page_data.get(ret, []):
                item["projectKey"] = project
                if branch:
                    item["branchKey"] = branch
                if pull_request:
                    item["pullRequestKey"] = pull_request
                dr = cls(endpoint, item)
                results[dr.key] = dr

        log.info("Found %d dependency risks for project '%s' branch '%s' PR '%s'", len(results), project, branch, pull_request)
        return results

    def changelog(self, after: Optional[datetime] = None) -> dict[str, DependencyRiskChangelog]:
        """Returns the changelog of a dependency risk.

        :param after: If set, only changes after that date are returned
        :return: The changelog
        """
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
            api, _, params, _ = self.endpoint.api.get_details(
                self, Oper.DELETE_COMMENT, key=self.key, issueReleaseChangeKey=comment_key
            )
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

    def url(self) -> str:
        """Returns a permalink URL to the dependency risk in the SonarQube UI."""
        branch_param = ""
        if self.branch:
            branch_param = f"&branch={self.branch}"
        elif self.pull_request:
            branch_param = f"&pullRequest={self.pull_request}"
        return f"{self.base_url(local=False)}/dependency-risks/{self.key}/what?id={self.projectKey}{branch_param}"

    def strictly_identical_to(self, other: DependencyRisk, ignore_component: bool = False) -> bool:  # noqa: ARG002
        """Two dependency risks are identical if they share the same identity fields.

        For PROHIBITED_LICENSE risks: match on packageUrl + licenseExpression + spdxLicenseId.
        For VULNERABILITY risks: match on packageUrl + vulnerabilityId.
        """
        if self.key == other.key:
            return True
        if self.type == "PROHIBITED_LICENSE":
            is_match = (
                self.type == other.type
                and self.packageUrl == other.packageUrl
                and self.licenseExpression == other.licenseExpression
                and self.spdxLicenseId == other.spdxLicenseId
            )
        else:
            is_match = self.type == other.type and self.packageUrl == other.packageUrl and self.vulnerabilityId == other.vulnerabilityId
        log.log(log.INFO if is_match else log.DEBUG, "Comparing %s and %s - Match = %s", str(self), str(other), is_match)
        return is_match

    def search_siblings(
        self, findings_list: list[DependencyRisk], ignore_component: bool = False
    ) -> tuple[list[DependencyRisk], list[DependencyRisk], list[DependencyRisk]]:
        """Finds matching dependency risks in a target list.

        Returns (exact_matches, approx_matches, modified_matches).
        Dependency risks don't have approximate matches, so that list is always empty.
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

        return Project.get_object(self.endpoint, self.projectKey)


def sca_feature_enabled(endpoint: Platform) -> bool:
    """Returns True if SCA is available on the given endpoint."""
    try:
        api = endpoint.api.api(DependencyRisk, Oper.FEATURE_ENABLED)
        resp = endpoint.get(api, mute=(HTTPStatus.NOT_FOUND, HTTPStatus.FORBIDDEN))
        if not resp.ok:
            return False
        data = json.loads(resp.text)
        return data.get("enabled", False)
    except (exceptions.UnsupportedOperation, exceptions.ObjectNotFound):
        return False
    except Exception:  # noqa: BLE001
        log.debug("SCA feature check failed")
        return False


def get_changelogs(dr_list: list[DependencyRisk], added_after: Optional[datetime] = None, threads: int = 8) -> None:  # noqa: ARG001
    """Mass-collects changelogs for dependency risks."""
    for dr in dr_list:
        try:
            dr.has_changelog(after=added_after)
            dr.has_comments(after=added_after)
        except Exception:  # noqa: BLE001, PERF203
            log.error("Error collecting changelog for %s", str(dr))
