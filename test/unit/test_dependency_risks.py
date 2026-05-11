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

from typing import Any, Generator
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from sonar import dependency_risks as dr
from sonar.dependency_risks import DependencyRisk, CSV_FIELDS
from sonar.dependency_risk_changelog import DependencyRiskChangelog
import sonar.util.issue_defs as idefs


def _mock_endpoint() -> MagicMock:
    endpoint = MagicMock()
    endpoint.local_url = "http://localhost:9000"
    endpoint.external_url = "http://localhost:9000"
    endpoint.is_sonarcloud.return_value = False
    endpoint.version.return_value = (2025, 4, 0)
    endpoint.edition.return_value = "enterprise"
    return endpoint


def _payload(**overrides: Any) -> dict[str, Any]:
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
def _clear_cache() -> Generator[None, None, None]:
    DependencyRisk.CACHE.clear()
    yield
    DependencyRisk.CACHE.clear()


def test_field_mapping_vulnerability() -> None:
    """Test that a DependencyRisk correctly maps fields from the API payload, including nested ones, and constructs a headline."""
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
    """When release summary flags are false, transitivity falls back to TRANSITIVE and scope to TEST."""
    payload = _payload()
    payload["release"]["directSummary"] = False
    payload["release"]["productionScopeSummary"] = False
    risk = DependencyRisk(_mock_endpoint(), payload, project_key="p")
    assert risk.transitivity == "TRANSITIVE"
    assert risk.scope == "TEST"


def test_assignee_none_when_unassigned() -> None:
    """An absent assignee in the payload should surface as None on the risk."""
    risk = DependencyRisk(_mock_endpoint(), _payload(assignee=None), project_key="p")
    assert risk.assignee is None


def test_to_json_excludes_none_and_empty() -> None:
    """to_json() should drop None/empty fields, omit internal id, and emit a usable risk URL."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p", branch="main")
    data = risk.to_json()
    assert "id" not in data
    assert "key" in data
    assert "CVE" in data
    assert "spdxLicenseId" not in data  # was None in payload
    assert "pullRequest" not in data  # not provided
    assert data["url"].startswith("http://localhost:9000/dependency-risks/issue?")


def test_to_csv_matches_csv_header() -> None:
    """to_csv() rows must align column-by-column with CSV_FIELDS and the public CSV header."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    row = risk.to_csv()
    header = DependencyRisk.csv_header()
    assert len(row) == len(header) == len(CSV_FIELDS)
    assert "id" not in CSV_FIELDS
    # Spot-check that fields land in their correct columns
    assert row[CSV_FIELDS.index("key")] == "risk-1-key"
    assert row[CSV_FIELDS.index("type")] == idefs.SCA_TYPE_VULNERABLE_DEPENDENCY
    assert row[CSV_FIELDS.index("packageName")] == "lodash"
    assert row[CSV_FIELDS.index("transitivity")] == "DIRECT"
    assert row[CSV_FIELDS.index("scope")] == "PRODUCTION"


def test_to_sarif_severity_promotes_to_error() -> None:
    """BLOCKER severity should map to SARIF level 'error' and carry the CVE as ruleId."""
    risk = DependencyRisk(_mock_endpoint(), _payload(severity="BLOCKER"), project_key="p")
    sarif = risk.to_sarif()
    assert sarif["level"] == "error"
    assert sarif["ruleId"] == "CVE-2026-12345"
    assert sarif["message"]["text"] == risk.headline


def test_to_sarif_minor_severity_is_warning() -> None:
    """LOW severity should map to SARIF level 'warning' rather than 'error'."""
    risk = DependencyRisk(_mock_endpoint(), _payload(severity="LOW"), project_key="p")
    assert risk.to_sarif()["level"] == "warning"


def test_url_encodes_branch_and_pull_request() -> None:
    """url() should include exactly one of pullRequest or branch — never both — based on context."""
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
    """sca_enabled() should return False on SonarQube versions that predate SCA support."""
    endpoint = _mock_endpoint()
    endpoint.version.return_value = (10, 0, 0)
    assert dr.sca_enabled(endpoint) is False


def test_project_returns_project_for_risks_project_key() -> None:
    """project() should resolve the risk's project_key via Project.get_object."""
    endpoint = _mock_endpoint()
    risk = DependencyRisk(endpoint, _payload(), project_key="my-proj", project_name="My Project", branch="main")

    sentinel_project = MagicMock(name="Project(my-proj)")
    with patch("sonar.projects.Project.get_object", return_value=sentinel_project) as get_object:
        result = risk.project()

    assert result is sentinel_project
    get_object.assert_called_once_with(endpoint, "my-proj")


def test_project_resolves_per_risk_project_key() -> None:
    """Each risk should look up its own project_key, not share state across instances."""
    endpoint = _mock_endpoint()
    risk_a = DependencyRisk(endpoint, _payload(key="a"), project_key="proj-a")
    risk_b = DependencyRisk(endpoint, _payload(key="b"), project_key="proj-b")

    proj_a, proj_b = MagicMock(name="proj-a"), MagicMock(name="proj-b")
    with patch("sonar.projects.Project.get_object", side_effect=lambda _ep, key: {"proj-a": proj_a, "proj-b": proj_b}[key]) as get_object:
        assert risk_a.project() is proj_a
        assert risk_b.project() is proj_b

    assert get_object.call_count == 2
    assert [c.args[1] for c in get_object.call_args_list] == ["proj-a", "proj-b"]


def _assign_mocks(login: str = "alice") -> tuple[MagicMock, MagicMock]:
    """Build syncer/users module mocks suitable for DependencyRisk.assign()."""
    syncer = MagicMock()
    syncer.SYNC_ASSIGN = "sync_assignments"
    users = MagicMock()
    users.get_login_from_name.return_value = login
    return syncer, users


def test_assign_no_op_when_sync_assign_disabled() -> None:
    """assign() should be a no-op when settings disable assignment sync."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    syncer, users = _assign_mocks()
    settings = {"sync_assignments": False}

    with patch.object(risk, "_sca_patch") as patch_call:
        ok = risk.assign("Alice", settings, syncer, users)

    assert ok is False
    users.get_login_from_name.assert_not_called()
    patch_call.assert_not_called()


def test_assign_returns_false_when_login_unresolvable() -> None:
    """assign() returns False without patching when no login matches the name."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    syncer, users = _assign_mocks(login=None)

    with patch.object(risk, "_sca_patch") as patch_call:
        ok = risk.assign("Ghost User", {}, syncer, users)

    assert ok is False
    users.get_login_from_name.assert_called_once()
    patch_call.assert_not_called()


def test_assign_patches_with_resolved_login() -> None:
    """assign() should PATCH with the resolved login and return True."""
    endpoint = _mock_endpoint()
    risk = DependencyRisk(endpoint, _payload(key="r1"), project_key="p")
    syncer, users = _assign_mocks(login="alice-login")

    with patch.object(risk, "_sca_patch") as patch_call:
        ok = risk.assign("Alice", {}, syncer, users)

    assert ok is True
    users.get_login_from_name.assert_called_once_with(endpoint=endpoint, name="Alice")
    patch_call.assert_called_once()
    kwargs = patch_call.call_args.kwargs
    assert kwargs["issueReleaseKey"] == "r1"
    assert kwargs["assigneeLogin"] == "alice-login"


def test_assign_returns_false_on_sonar_exception() -> None:
    """A SonarException from the patch must be swallowed and surface as False."""
    from sonar import exceptions

    risk = DependencyRisk(_mock_endpoint(), _payload(key="r1"), project_key="p")
    syncer, users = _assign_mocks(login="alice-login")

    with patch.object(risk, "_sca_patch", side_effect=exceptions.SonarException("boom", 1)):
        ok = risk.assign("Alice", {}, syncer, users)

    assert ok is False


def _changelog_entry(date_iso: str, key_suffix: str = "") -> DependencyRiskChangelog:
    """Build a minimal DependencyRiskChangelog with a known createdAt."""
    return DependencyRiskChangelog(
        {
            "key": f"chg-{key_suffix or date_iso}",
            "createdAt": date_iso,
            "changeData": [{"fieldName": "severity", "oldValue": "LOW", "newValue": "HIGH"}],
        }
    )


def _filter_after(entries: dict, cutoff: datetime) -> dict:
    """Mirrors the caller-side date filter callers apply to the changelog property."""
    return {k: v for k, v in entries.items() if v.date_time() > cutoff}


def test_changelog_with_after_filters_older_entries() -> None:
    """Caller-side filtering of the changelog property keeps only entries strictly after the cutoff."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    older = _changelog_entry("2026-01-01T10:00:00+0000", "older")
    newer = _changelog_entry("2026-03-01T10:00:00+0000", "newer")
    risk.changelog = {"a": older, "b": newer}
    risk.comments = {}  # short-circuit the lazy loader

    cutoff = datetime(2026, 2, 1, tzinfo=timezone.utc)
    filtered = _filter_after(risk.changelog, cutoff)

    assert list(filtered.keys()) == ["b"]
    assert filtered["b"] is newer


def test_changelog_with_after_in_future_returns_empty() -> None:
    """A cutoff after every entry returns an empty dict, not the full changelog."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    risk.changelog = {"a": _changelog_entry("2026-01-01T10:00:00+0000")}
    risk.comments = {}

    cutoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert _filter_after(risk.changelog, cutoff) == {}


def test_changelog_after_excludes_entries_with_matching_timestamp() -> None:
    """The caller-side filter is strictly greater-than: entries equal to the cutoff are excluded."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    boundary = "2026-02-15T12:00:00+0000"
    risk.changelog = {
        "a": _changelog_entry(boundary, "exact"),
        "b": _changelog_entry("2026-02-15T12:00:01+0000", "after"),
    }
    risk.comments = {}

    cutoff = datetime(2026, 2, 15, 12, 0, 0, tzinfo=timezone.utc)
    filtered = _filter_after(risk.changelog, cutoff)

    assert list(filtered.keys()) == ["b"]


def test_changelog_property_lazy_loads_when_unloaded() -> None:
    """The changelog property must trigger _load_changelog_and_comments when _changelog is None."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")

    def fake_load() -> None:
        risk.changelog = {"a": _changelog_entry("2026-04-01T10:00:00+0000")}
        risk.comments = {}

    with patch.object(risk, "_load_changelog_and_comments", side_effect=fake_load) as load:
        result = risk.changelog

    load.assert_called_once()
    assert "a" in result


# ---------------------------------------------------------------------------
# cli.findings_export._expand_applications_to_components
#
# Lives in cli/, but only ever runs in the SCA + applications path, so the
# unit tests live here next to the rest of the SCA-flow coverage.
# ---------------------------------------------------------------------------


def _mock_branch(name: str) -> MagicMock:
    b = MagicMock()
    b.name = name
    return b


def _mock_project(key: str, branches: tuple[str, ...] = ("main",)) -> MagicMock:
    proj = MagicMock(name=f"Project({key})")
    proj.key = key
    proj.branches.return_value = {n: _mock_branch(n) for n in branches}
    return proj


def _mock_application(endpoint: MagicMock, projects_map: dict[str, str]) -> MagicMock:
    """Build a Mock that passes isinstance(app, Application) and exposes .projects() / .endpoint."""
    from sonar.applications import Application

    app = MagicMock(spec=Application)
    app.endpoint = endpoint
    app.projects.return_value = projects_map
    return app


def test_expand_applications_passes_through_non_application_items() -> None:
    """Items that aren't Application instances should be returned untouched."""
    from cli.findings_export import _expand_applications_to_components

    proj_a = _mock_project("a")
    proj_b = _mock_project("b")
    out = _expand_applications_to_components([proj_a, proj_b])
    assert out == [proj_a, proj_b]


def test_expand_applications_resolves_branch_when_set() -> None:
    """An app binding a non-main branch should expand to that branch object."""
    from cli.findings_export import _expand_applications_to_components

    endpoint = _mock_endpoint()
    proj = _mock_project("p", branches=("main", "develop"))
    app = _mock_application(endpoint, {"p": "develop"})

    with patch("sonar.projects.Project.get_object", return_value=proj):
        out = _expand_applications_to_components([app])

    assert len(out) == 1
    assert out[0] is proj.branches.return_value["develop"]


def test_expand_applications_falls_back_to_project_when_no_branch() -> None:
    """If the application binds the project without a branch, return the Project itself."""
    from cli.findings_export import _expand_applications_to_components

    endpoint = _mock_endpoint()
    proj = _mock_project("p")
    app = _mock_application(endpoint, {"p": ""})

    with patch("sonar.projects.Project.get_object", return_value=proj):
        out = _expand_applications_to_components([app])

    assert out == [proj]


def test_expand_applications_skips_missing_projects() -> None:
    """ObjectNotFound from Project.get_object should be logged and skipped, not raised."""
    from cli.findings_export import _expand_applications_to_components
    from sonar import exceptions

    endpoint = _mock_endpoint()
    survivor = _mock_project("survivor")
    app = _mock_application(endpoint, {"missing": "", "survivor": ""})

    def fake_get(_ep, key):
        if key == "missing":
            raise exceptions.ObjectNotFound(key, "not found")
        return survivor

    with patch("sonar.projects.Project.get_object", side_effect=fake_get):
        out = _expand_applications_to_components([app])

    assert out == [survivor]


def test_expand_applications_dedupes_repeated_components() -> None:
    """Two apps pointing at the same (project, branch) yield a single component."""
    from cli.findings_export import _expand_applications_to_components

    endpoint = _mock_endpoint()
    proj = _mock_project("p", branches=("main", "develop"))
    app1 = _mock_application(endpoint, {"p": "develop"})
    app2 = _mock_application(endpoint, {"p": "develop"})

    with patch("sonar.projects.Project.get_object", return_value=proj):
        out = _expand_applications_to_components([app1, app2])

    assert len(out) == 1


def test_expand_applications_keeps_distinct_branches_separate() -> None:
    """Same project bound on two different branches yields two distinct components."""
    from cli.findings_export import _expand_applications_to_components

    endpoint = _mock_endpoint()
    proj = _mock_project("p", branches=("main", "develop", "release"))
    app_dev = _mock_application(endpoint, {"p": "develop"})
    app_rel = _mock_application(endpoint, {"p": "release"})

    with patch("sonar.projects.Project.get_object", return_value=proj):
        out = _expand_applications_to_components([app_dev, app_rel])

    names = sorted(getattr(c, "name", None) for c in out)
    assert names == ["develop", "release"]
