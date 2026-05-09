#!/usr/bin/env python3
#
# sonar-tools tests
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

"""Unit tests for SCA dependency risk export (no live SonarQube required)."""

from unittest.mock import MagicMock, patch
import pytest

from sonar import dependency_risks as dr
from sonar.dependency_risks import DependencyRisk, CSV_FIELDS
import sonar.util.issue_defs as idefs


def _mock_endpoint() -> MagicMock:
    endpoint = MagicMock()
    endpoint.local_url = "http://localhost:9000"
    endpoint.external_url = "http://localhost:9000"
    endpoint.is_sonarcloud.return_value = False
    endpoint.version.return_value = (2025, 4, 0)
    endpoint.edition.return_value = "enterprise"
    return endpoint


def _payload(**overrides) -> dict:
    base = {
        "id": "risk-1",
        "key": "risk-1-key",
        "severity": "HIGH",
        "originalSeverity": "HIGH",
        "type": "VULNERABILITY",
        "quality": "SECURITY",
        "status": "OPEN",
        "createdAt": "2026-01-15T10:00:00Z",
        "vulnerabilityId": "CVE-2026-12345",
        "cvssScore": "7.5",
        "spdxLicenseId": None,
        "assignee": {"login": "alice", "name": "Alice", "active": True},
        "release": {
            "packageName": "lodash",
            "version": "4.17.20",
            "packageManager": "npm",
            "packageUrl": "pkg:npm/lodash@4.17.20",
            "directSummary": True,
            "productionScopeSummary": True,
            "newlyIntroduced": False,
        },
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _clear_cache():
    DependencyRisk.CACHE.clear()
    yield
    DependencyRisk.CACHE.clear()


def test_field_mapping_vulnerability() -> None:
    risk = DependencyRisk(
        _mock_endpoint(),
        _payload(),
        project_key="proj1",
        project_name="Project One",
        branch="main",
    )
    assert risk.id == "risk-1"
    assert risk.key == "risk-1-key"
    assert risk.type == idefs.SCA_TYPE_VULNERABLE_DEPENDENCY
    assert risk.severity == "HIGH"
    assert risk.quality == "SECURITY"
    assert risk.status == "OPEN"
    assert risk.vulnerability_id == "CVE-2026-12345"
    assert risk.cvss_score == "7.5"
    assert risk.assignee == "alice"
    assert risk.package_name == "lodash"
    assert risk.package_version == "4.17.20"
    assert risk.package_manager == "npm"
    assert risk.transitivity == "DIRECT"
    assert risk.scope == "PRODUCTION"
    assert risk.newly_introduced is False
    assert risk.project_key == "proj1"
    assert risk.project_name == "Project One"
    assert risk.branch == "main"
    assert risk.pull_request is None
    assert "CVE-2026-12345" in risk.headline
    assert "lodash" in risk.headline


def test_api_type_mapping() -> None:
    """All three API type values should map to the issue's enum spelling."""
    cases = {
        "VULNERABILITY": idefs.SCA_TYPE_VULNERABLE_DEPENDENCY,
        "PROHIBITED_LICENSE": idefs.SCA_TYPE_PROHIBITED_LICENCE,
        "MALWARE": idefs.SCA_TYPE_MALWARE,
    }
    for api_type, expected in cases.items():
        risk = DependencyRisk(_mock_endpoint(), _payload(type=api_type, key=f"k-{api_type}"), project_key="p")
        assert risk.type == expected


def test_transitivity_and_scope_defaults_when_release_missing_flags() -> None:
    payload = _payload()
    payload["release"]["directSummary"] = False
    payload["release"]["productionScopeSummary"] = False
    risk = DependencyRisk(_mock_endpoint(), payload, project_key="p")
    assert risk.transitivity == "TRANSITIVE"
    assert risk.scope == "TEST"


def test_assignee_none_when_unassigned() -> None:
    risk = DependencyRisk(_mock_endpoint(), _payload(assignee=None), project_key="p")
    assert risk.assignee is None


def test_to_json_excludes_none_and_empty() -> None:
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p", branch="main")
    data = risk.to_json()
    assert "id" in data
    assert "vulnerabilityId" in data
    assert "spdxLicenseId" not in data  # was None in payload
    assert "pullRequest" not in data  # not provided
    assert data["url"].startswith("http://localhost:9000/dependency-risks/issue?")


def test_to_csv_matches_csv_header() -> None:
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    row = risk.to_csv()
    header = DependencyRisk.csv_header()
    assert len(row) == len(header) == len(CSV_FIELDS)
    # Spot-check that fields land in their correct columns
    assert row[CSV_FIELDS.index("id")] == "risk-1"
    assert row[CSV_FIELDS.index("type")] == idefs.SCA_TYPE_VULNERABLE_DEPENDENCY
    assert row[CSV_FIELDS.index("packageName")] == "lodash"
    assert row[CSV_FIELDS.index("transitivity")] == "DIRECT"
    assert row[CSV_FIELDS.index("scope")] == "PRODUCTION"


def test_to_sarif_severity_promotes_to_error() -> None:
    risk = DependencyRisk(_mock_endpoint(), _payload(severity="BLOCKER"), project_key="p")
    sarif = risk.to_sarif()
    assert sarif["level"] == "error"
    assert sarif["ruleId"] == "CVE-2026-12345"
    assert sarif["message"]["text"] == risk.headline


def test_to_sarif_minor_severity_is_warning() -> None:
    risk = DependencyRisk(_mock_endpoint(), _payload(severity="LOW"), project_key="p")
    assert risk.to_sarif()["level"] == "warning"


def test_url_encodes_branch_and_pull_request() -> None:
    pr_risk = DependencyRisk(_mock_endpoint(), _payload(key="pr-risk"), project_key="p", pull_request="42")
    assert "pullRequest=42" in pr_risk.url()
    assert "branch=" not in pr_risk.url()
    br_risk = DependencyRisk(_mock_endpoint(), _payload(key="br-risk"), project_key="p", branch="develop")
    assert "branch=develop" in br_risk.url()
    assert "pullRequest=" not in br_risk.url()


def test_search_paginates_and_lookups_project_name() -> None:
    """search() should iterate pages and look up the project name from the 'branches' array."""
    endpoint = _mock_endpoint()

    page1 = {
        "issuesReleases": [_payload(key="r1"), _payload(key="r2")],
        "branches": [{"projectKey": "p", "projectName": "My Project"}],
        "page": {"pageIndex": 1, "pageSize": 2, "total": 3},
    }
    page2 = {
        "issuesReleases": [_payload(key="r3")],
        "branches": [{"projectKey": "p", "projectName": "My Project"}],
        "page": {"pageIndex": 2, "pageSize": 2, "total": 3},
    }

    responses = [MagicMock(text=__import__("json").dumps(page1)), MagicMock(text=__import__("json").dumps(page2))]
    endpoint.get.side_effect = responses
    endpoint.api.get_details.return_value = ("api/v2/sca/issues-releases", "GET", {}, "issuesReleases")

    with patch("sonar.dependency_risks._check_supported"):
        results = DependencyRisk.search(endpoint, project_key="p", branch="main")

    assert len(results) == 3
    assert {"r1", "r2", "r3"} == set(results.keys())
    for risk in results.values():
        assert risk.project_name == "My Project"
        assert risk.branch == "main"
    assert endpoint.get.call_count == 2


def test_sca_enabled_returns_false_on_unsupported() -> None:
    endpoint = _mock_endpoint()
    endpoint.version.return_value = (10, 0, 0)
    assert dr.sca_enabled(endpoint) is False
