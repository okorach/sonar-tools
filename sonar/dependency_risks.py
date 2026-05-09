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

from sonar.sqobject import SqObject
import sonar.logging as log
from sonar.util import cache
from sonar import exceptions
import sonar.util.issue_defs as idefs
from sonar.api.manager import ApiOperation as Oper

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload, ObjectJsonRepr

_MIN_SQ_VERSION = (2025, 4, 0)
_CB_VERSION_OFFSET = 2000
_SUPPORTED_EDITIONS = ("enterprise", "datacenter")
_UNSUPPORTED_VERSION_MSG = "SCA dependency risks require SonarQube Server 2025.4 or later, or SonarQube Cloud"
_UNSUPPORTED_EDITION_MSG = "SCA dependency risks require Enterprise Edition or Data Center Edition"

_DEFAULT_PAGE_SIZE = 500

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


class DependencyRisk(SqObject):
    """Abstraction of a SonarQube SCA dependency risk (an issue paired with a package release)"""

    CACHE = cache.Cache()

    def __init__(
        self,
        endpoint: Platform,
        data: ApiPayload,
        project_key: str,
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
        self.assignee: Optional[str] = assignee.get("login") if isinstance(assignee, dict) else None

        release = data.get("release") or {}
        self.package_name: Optional[str] = release.get("packageName")
        self.package_version: Optional[str] = release.get("version")
        package_manager = release.get("packageManager")
        self.package_manager: Optional[str] = package_manager.lower() if package_manager else None
        self.package_url: Optional[str] = release.get("packageUrl")
        self.transitivity: str = "DIRECT" if release.get("directSummary") else "TRANSITIVE"
        self.scope: str = "PRODUCTION" if release.get("productionScopeSummary") else "TEST"
        self.newly_introduced: bool = bool(release.get("newlyIntroduced", False))

        self.project_key: str = project_key
        self.project_name: Optional[str] = project_name
        self.branch: Optional[str] = branch
        self.pull_request: Optional[str] = pull_request

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
