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

from typing import Any, Generator, Optional
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from sonar import dependency_risks as dr, exceptions
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


# ---------------------------------------------------------------------------
# Changelog / comments: _load_changelog_and_comments, comments property,
# has_changelog, has_comments, last_changelog_date, last_comment_date,
# modifiers, commenters
# ---------------------------------------------------------------------------


def _severity_entry(date_iso: str, old: str = "LOW", new: str = "HIGH", key_suffix: str = "") -> DependencyRiskChangelog:
    return DependencyRiskChangelog(
        {
            "key": f"chg-{key_suffix or date_iso}",
            "createdAt": date_iso,
            "changeData": [{"fieldName": "severity", "oldValue": old, "newValue": new}],
            "user": {"login": "alice", "name": "Alice"},
        }
    )


def _status_fixed_entry(date_iso: str) -> DependencyRiskChangelog:
    """Entry that is_technical_change() == True (status → FIXED)."""
    return DependencyRiskChangelog(
        {
            "key": f"chg-{date_iso}",
            "createdAt": date_iso,
            "changeData": [{"fieldName": "status", "oldValue": "OPEN", "newValue": "FIXED"}],
        }
    )


def _comment_payload(date_iso: str, text: str, author_login: str = "bob") -> dict:
    return {
        "key": f"comment-{date_iso}",
        "createdAt": date_iso,
        "markdownComment": text,
        "user": {"login": author_login},
    }


def _risk_with_changelog(changelog: dict, comments: dict) -> DependencyRisk:
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    risk.changelog = changelog
    risk.comments = comments
    return risk


def test_load_changelog_and_comments_splits_correctly() -> None:
    """_load_changelog_and_comments populates both _changelog and _comments from the API response."""
    endpoint = _mock_endpoint()
    risk = DependencyRisk(endpoint, _payload(), project_key="p")
    risk._changelog = None
    risk._comments = None

    api_response = {
        "changelog": [
            {
                "key": "chg-1",
                "createdAt": "2026-01-01T10:00:00+0000",
                "changeData": [{"fieldName": "severity", "oldValue": "LOW", "newValue": "HIGH"}],
                "user": {"login": "alice"},
            },
            _comment_payload("2026-01-02T10:00:00+0000", "looks risky"),
        ]
    }
    endpoint.api.get_details.return_value = ("api/v2/sca/changelog", "GET", {}, "changelog")
    endpoint.get.return_value = MagicMock(text=__import__("json").dumps(api_response))

    risk._load_changelog_and_comments()

    assert len(risk._changelog) == 1
    assert len(risk._comments) == 1
    comment = list(risk._comments.values())[0]
    assert comment["value"] == "looks risky"
    assert comment["event"] == "comment"


def test_load_changelog_skips_technical_changes() -> None:
    """Technical status changes (FIXED) must not land in _changelog."""
    endpoint = _mock_endpoint()
    risk = DependencyRisk(endpoint, _payload(), project_key="p")
    risk._changelog = None
    risk._comments = None

    api_response = {
        "changelog": [
            {
                "key": "chg-fixed",
                "createdAt": "2026-03-01T10:00:00+0000",
                "changeData": [{"fieldName": "status", "oldValue": "OPEN", "newValue": "FIXED"}],
            }
        ]
    }
    endpoint.api.get_details.return_value = ("api/v2/sca/changelog", "GET", {}, "changelog")
    endpoint.get.return_value = MagicMock(text=__import__("json").dumps(api_response))

    risk._load_changelog_and_comments()

    assert risk._changelog == {}


def test_comments_property_lazy_loads() -> None:
    """The comments property triggers _load_changelog_and_comments when _comments is None."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")

    def fake_load() -> None:
        risk.changelog = {}
        risk.comments = {"c1": {"date": datetime(2026, 1, 1, tzinfo=timezone.utc), "event": "comment", "value": "hi", "user": "alice"}}

    with patch.object(risk, "_load_changelog_and_comments", side_effect=fake_load) as load:
        result = risk.comments

    load.assert_called_once()
    assert "c1" in result


def test_has_changelog_no_cutoff() -> None:
    """has_changelog() without a cutoff returns True when any entry exists."""
    risk = _risk_with_changelog({"a": _severity_entry("2026-01-01T10:00:00+0000")}, {})
    assert risk.has_changelog() is True


def test_has_changelog_with_after_cutoff() -> None:
    """has_changelog(after=...) returns True only if an entry is strictly after the cutoff."""
    risk = _risk_with_changelog(
        {
            "a": _severity_entry("2026-01-01T10:00:00+0000"),
            "b": _severity_entry("2026-03-01T10:00:00+0000", key_suffix="b"),
        },
        {},
    )
    cutoff = datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert risk.has_changelog(after=cutoff) is True
    cutoff_future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert risk.has_changelog(after=cutoff_future) is False


def test_has_changelog_empty() -> None:
    """has_changelog() returns False when the changelog is empty."""
    risk = _risk_with_changelog({}, {})
    assert risk.has_changelog() is False


def test_has_comments_no_cutoff() -> None:
    """has_comments() without a cutoff returns True when any comment exists."""
    risk = _risk_with_changelog(
        {},
        {"c1": {"date": datetime(2026, 1, 1, tzinfo=timezone.utc), "event": "comment", "value": "x", "user": "alice"}},
    )
    assert risk.has_comments() is True


def test_has_comments_with_cutoff() -> None:
    """has_comments(after=...) returns True only for comments strictly after the cutoff."""
    risk = _risk_with_changelog(
        {},
        {
            "c1": {"date": datetime(2026, 1, 1, tzinfo=timezone.utc), "event": "comment", "value": "old", "user": "alice"},
            "c2": {"date": datetime(2026, 3, 1, tzinfo=timezone.utc), "event": "comment", "value": "new", "user": "bob"},
        },
    )
    cutoff = datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert risk.has_comments(after=cutoff) is True
    cutoff_future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert risk.has_comments(after=cutoff_future) is False


def test_has_comments_empty() -> None:
    """has_comments() returns False when the comments dict is empty."""
    risk = _risk_with_changelog({}, {})
    assert risk.has_comments() is False


def test_last_changelog_date_returns_last_entry() -> None:
    """last_changelog_date() returns the date of the chronologically last entry."""
    e1 = _severity_entry("2026-01-01T10:00:00+0000", key_suffix="e1")
    e2 = _severity_entry("2026-06-01T10:00:00+0000", key_suffix="e2")
    risk = _risk_with_changelog({"a": e1, "b": e2}, {})
    assert risk.last_changelog_date() == e2.date_time()


def test_last_changelog_date_none_when_empty() -> None:
    """last_changelog_date() returns None when changelog is empty."""
    risk = _risk_with_changelog({}, {})
    assert risk.last_changelog_date() is None


def test_last_comment_date_returns_last_comment() -> None:
    """last_comment_date() returns the date of the last comment."""
    d1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d2 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    risk = _risk_with_changelog(
        {},
        {
            "c1": {"date": d1, "event": "comment", "value": "first", "user": "alice"},
            "c2": {"date": d2, "event": "comment", "value": "last", "user": "bob"},
        },
    )
    assert risk.last_comment_date() == d2


def test_last_comment_date_none_when_empty() -> None:
    """last_comment_date() returns None when there are no comments."""
    risk = _risk_with_changelog({}, {})
    assert risk.last_comment_date() is None


def test_modifiers_collects_authors() -> None:
    """modifiers() returns the set of author logins from changelog entries."""
    e1 = DependencyRiskChangelog(
        {"key": "c1", "createdAt": "2026-01-01T10:00:00+0000", "changeData": [{"fieldName": "severity", "newValue": "HIGH"}], "user": {"login": "alice"}}
    )
    e2 = DependencyRiskChangelog(
        {"key": "c2", "createdAt": "2026-02-01T10:00:00+0000", "changeData": [{"fieldName": "severity", "newValue": "LOW"}], "user": {"login": "bob"}}
    )
    risk = _risk_with_changelog({"a": e1, "b": e2}, {})
    assert risk.modifiers() == {"alice", "bob"}


def test_modifiers_with_after_cutoff() -> None:
    """modifiers(after=...) only returns authors of entries after the cutoff."""
    e_old = DependencyRiskChangelog(
        {"key": "c1", "createdAt": "2026-01-01T10:00:00+0000", "changeData": [{"fieldName": "severity", "newValue": "HIGH"}], "user": {"login": "alice"}}
    )
    e_new = DependencyRiskChangelog(
        {"key": "c2", "createdAt": "2026-06-01T10:00:00+0000", "changeData": [{"fieldName": "severity", "newValue": "LOW"}], "user": {"login": "bob"}}
    )
    risk = _risk_with_changelog({"a": e_old, "b": e_new}, {})
    cutoff = datetime(2026, 2, 1, tzinfo=timezone.utc)
    assert risk.modifiers(after=cutoff) == {"bob"}


def test_commenters_collects_comment_authors() -> None:
    """commenters() returns the set of user logins from all comments."""
    risk = _risk_with_changelog(
        {},
        {
            "c1": {"date": datetime(2026, 1, 1, tzinfo=timezone.utc), "event": "comment", "value": "hi", "user": "alice"},
            "c2": {"date": datetime(2026, 2, 1, tzinfo=timezone.utc), "event": "comment", "value": "ok", "user": "bob"},
            "c3": {"date": datetime(2026, 3, 1, tzinfo=timezone.utc), "event": "comment", "value": "again", "user": "alice"},
        },
    )
    assert risk.commenters() == {"alice", "bob"}


def test_commenters_empty_when_no_comments() -> None:
    """commenters() returns an empty set when there are no comments."""
    risk = _risk_with_changelog({}, {})
    assert risk.commenters() == set()


# ---------------------------------------------------------------------------
# add_comment / delete_comment
# ---------------------------------------------------------------------------


def test_add_comment_returns_true_and_invalidates_cache() -> None:
    """add_comment() must POST, return True, and clear the cached comments."""
    endpoint = _mock_endpoint()
    risk = DependencyRisk(endpoint, _payload(), project_key="p")
    risk._comments = {}
    endpoint.api.get_details.return_value = ("api/v2/sca/comment", "POST", {"comment": "hello"}, "")

    with patch.object(risk, "post") as mock_post:
        ok = risk.add_comment("hello")

    assert ok is True
    mock_post.assert_called_once()
    assert risk._comments is None


def test_add_comment_returns_false_on_exception() -> None:
    """add_comment() returns False when the API call raises SonarException."""
    from sonar import exceptions

    endpoint = _mock_endpoint()
    risk = DependencyRisk(endpoint, _payload(), project_key="p")
    endpoint.api.get_details.return_value = ("api/v2/sca/comment", "POST", {}, "")

    with patch.object(risk, "post", side_effect=exceptions.SonarException("boom", 1)):
        ok = risk.add_comment("hello")

    assert ok is False


def test_delete_comment_returns_true_and_invalidates_cache() -> None:
    """delete_comment() must call DELETE, return True, and clear cached comments."""
    endpoint = _mock_endpoint()
    risk = DependencyRisk(endpoint, _payload(), project_key="p")
    risk._comments = {}
    endpoint.api.get_details.return_value = ("api/v2/sca/comment/ck-1", "DELETE", {}, "")

    with patch.object(endpoint, "delete") as mock_delete:
        ok = risk.delete_comment("ck-1")

    assert ok is True
    mock_delete.assert_called_once()
    assert risk._comments is None


def test_delete_comment_returns_false_on_exception() -> None:
    """delete_comment() returns False when the API call raises SonarException."""
    from sonar import exceptions

    endpoint = _mock_endpoint()
    risk = DependencyRisk(endpoint, _payload(), project_key="p")
    endpoint.api.get_details.return_value = ("api/v2/sca/comment/ck-1", "DELETE", {}, "")
    endpoint.delete.side_effect = exceptions.SonarException("boom", 1)

    ok = risk.delete_comment("ck-1")
    assert ok is False


# ---------------------------------------------------------------------------
# get_tags / set_tags
# ---------------------------------------------------------------------------


def test_get_tags_raises_unsupported_operation() -> None:
    """get_tags() must raise UnsupportedOperation — DependencyRisk has no tags."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    with pytest.raises(exceptions.UnsupportedOperation):
        risk.get_tags()


def test_set_tags_raises_unsupported_operation() -> None:
    """set_tags() must raise UnsupportedOperation — DependencyRisk has no tags."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    with pytest.raises(exceptions.UnsupportedOperation):
        risk.set_tags(["tag1"])


# ---------------------------------------------------------------------------
# strictly_identical_to
# ---------------------------------------------------------------------------


def test_strictly_identical_to_same_key() -> None:
    """Two risks with the same key are always identical."""
    ep = _mock_endpoint()
    r1 = DependencyRisk(ep, _payload(key="same"), project_key="p")
    r2 = DependencyRisk(ep, _payload(key="same"), project_key="q")
    assert r1.strictly_identical_to(r2) is True


def test_strictly_identical_to_vulnerability_match() -> None:
    """Two vulnerability risks match when type + package_url + vulnerability_id agree."""
    ep = _mock_endpoint()
    r1 = DependencyRisk(ep, _payload(key="a", vulnerabilityId="CVE-X"), project_key="p")
    r2 = DependencyRisk(ep, _payload(key="b", vulnerabilityId="CVE-X"), project_key="p")
    assert r1.strictly_identical_to(r2) is True


def test_strictly_identical_to_different_cve() -> None:
    """Two vulnerability risks with different CVEs are not identical."""
    ep = _mock_endpoint()
    r1 = DependencyRisk(ep, _payload(key="a", vulnerabilityId="CVE-1"), project_key="p")
    r2 = DependencyRisk(ep, _payload(key="b", vulnerabilityId="CVE-2"), project_key="p")
    assert r1.strictly_identical_to(r2) is False


def test_strictly_identical_to_prohibited_licence() -> None:
    """Prohibited-license risks match on type + package_url + license_expression + spdx_license_id."""
    ep = _mock_endpoint()
    base = _payload(key="a", type="PROHIBITED_LICENSE", spdxLicenseId="GPL-3.0")
    base["release"]["licenseExpression"] = "GPL-3.0-or-later"
    r1 = DependencyRisk(ep, base, project_key="p")
    base2 = _payload(key="b", type="PROHIBITED_LICENSE", spdxLicenseId="GPL-3.0")
    base2["release"]["licenseExpression"] = "GPL-3.0-or-later"
    r2 = DependencyRisk(ep, base2, project_key="q")
    assert r1.strictly_identical_to(r2) is True


def test_strictly_identical_to_prohibited_licence_different_license() -> None:
    """Prohibited-license risks with different spdxLicenseId are not identical."""
    ep = _mock_endpoint()
    r1 = DependencyRisk(ep, _payload(key="a", type="PROHIBITED_LICENSE", spdxLicenseId="GPL-3.0"), project_key="p")
    r2 = DependencyRisk(ep, _payload(key="b", type="PROHIBITED_LICENSE", spdxLicenseId="MIT"), project_key="p")
    assert r1.strictly_identical_to(r2) is False


# ---------------------------------------------------------------------------
# search_siblings
# ---------------------------------------------------------------------------


def _make_risk(key: str, cve: str = "CVE-X", *, changelog: Optional[dict] = None) -> DependencyRisk:
    risk = DependencyRisk(_mock_endpoint(), _payload(key=key, vulnerabilityId=cve), project_key="p")
    risk.changelog = changelog or {}
    risk.comments = {}
    return risk


def test_search_siblings_finds_exact_match() -> None:
    """search_siblings returns an exact match when CVE and package_url agree."""
    source = _make_risk("source", "CVE-X")
    target = _make_risk("target", "CVE-X")
    exact, approx, modified = source.search_siblings([source, target])
    assert target in exact
    assert approx == []


def test_search_siblings_approx_always_empty() -> None:
    """DependencyRisk.search_siblings always returns an empty approx list."""
    source = _make_risk("s", "CVE-X")
    target = _make_risk("t", "CVE-X")
    _, approx, _ = source.search_siblings([source, target])
    assert approx == []


def test_search_siblings_modified_when_target_changelog_newer() -> None:
    """If target has a changelog entry *after* the source, it goes to modified_matches."""
    old_entry = _severity_entry("2026-01-01T10:00:00+0000", key_suffix="old")
    new_entry = _severity_entry("2026-06-01T10:00:00+0000", key_suffix="new")
    source = _make_risk("s", "CVE-X", changelog={"a": old_entry})
    target = _make_risk("t", "CVE-X", changelog={"b": new_entry})
    exact, _, modified = source.search_siblings([source, target])
    assert exact == []
    assert target in modified


def test_search_siblings_skips_self() -> None:
    """search_siblings should never include self in any list."""
    source = _make_risk("s", "CVE-X")
    exact, _, modified = source.search_siblings([source])
    assert source not in exact
    assert source not in modified


def test_search_siblings_no_match_on_different_cve() -> None:
    """A target with a different CVE produces no matches."""
    source = _make_risk("s", "CVE-1")
    target = _make_risk("t", "CVE-2")
    exact, approx, modified = source.search_siblings([source, target])
    assert exact == [] and approx == [] and modified == []


# ---------------------------------------------------------------------------
# _apply_event / _sca_patch / _apply_status_change / _apply_severity_change
# ---------------------------------------------------------------------------


def test_apply_event_delegates_status_change() -> None:
    """_apply_event with a STATUS entry calls _apply_status_change."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    event = DependencyRiskChangelog(
        {"key": "e1", "createdAt": "2026-01-01T10:00:00+0000", "changeData": [{"fieldName": "status", "newValue": "ACCEPTED"}]}
    )
    with patch.object(risk, "_apply_status_change", return_value=True) as mock_apply:
        # __apply_event is name-mangled
        result = risk._DependencyRisk__apply_event(event, {})
    mock_apply.assert_called_once_with("ACCEPTED", source_url="")
    assert result is True


def test_apply_event_delegates_severity_change() -> None:
    """_apply_event with a SEVERITY entry calls _apply_severity_change."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    event = DependencyRiskChangelog(
        {"key": "e2", "createdAt": "2026-01-01T10:00:00+0000", "changeData": [{"fieldName": "severity", "newValue": "BLOCKER"}]}
    )
    with patch.object(risk, "_apply_severity_change", return_value=True) as mock_apply:
        result = risk._DependencyRisk__apply_event(event, {})
    mock_apply.assert_called_once_with("BLOCKER")
    assert result is True


def test_apply_event_returns_false_for_unknown_type() -> None:
    """_apply_event with an unrecognised changeData field returns False without calling anything."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    event = DependencyRiskChangelog(
        {"key": "e3", "createdAt": "2026-01-01T10:00:00+0000", "changeData": [{"fieldName": "unknownField", "newValue": "x"}]}
    )
    with patch.object(risk, "_apply_status_change") as m1, patch.object(risk, "_apply_severity_change") as m2:
        result = risk._DependencyRisk__apply_event(event, {})
    assert result is False
    m1.assert_not_called()
    m2.assert_not_called()


def test_sca_patch_calls_patch_with_content_type() -> None:
    """_sca_patch must call self.patch with the API-specified content-type."""
    from sonar.api.manager import ApiOperation as Oper

    endpoint = _mock_endpoint()
    endpoint.api.get_details.return_value = ("api/v2/sca/issues-releases/r1/status", "PATCH", {"transitionKey": "ACCEPTED"}, "")
    endpoint.api.content_type.return_value = "application/json"

    risk = DependencyRisk(endpoint, _payload(key="r1"), project_key="p")

    with patch.object(risk, "patch") as mock_patch:
        risk._sca_patch(Oper.CHANGE_STATUS, issueReleaseKey="r1", transitionKey="ACCEPTED")

    mock_patch.assert_called_once()
    _, kwargs = mock_patch.call_args
    assert kwargs.get("content_type") == "application/json"


def test_apply_status_change_returns_true_on_success() -> None:
    """_apply_status_change returns True when _sca_patch succeeds."""
    risk = DependencyRisk(_mock_endpoint(), _payload(key="r1"), project_key="p")
    with patch.object(risk, "_sca_patch"):
        assert risk._apply_status_change("ACCEPTED") is True


def test_apply_status_change_returns_false_on_exception() -> None:
    """_apply_status_change returns False when _sca_patch raises SonarException."""
    from sonar import exceptions

    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    with patch.object(risk, "_sca_patch", side_effect=exceptions.SonarException("boom", 1)):
        assert risk._apply_status_change("ACCEPTED") is False


def test_apply_severity_change_returns_true_on_success() -> None:
    """_apply_severity_change returns True when _sca_patch succeeds."""
    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    with patch.object(risk, "_sca_patch"):
        assert risk._apply_severity_change("BLOCKER") is True


def test_apply_severity_change_returns_false_on_exception() -> None:
    """_apply_severity_change returns False when _sca_patch raises SonarException."""
    from sonar import exceptions

    risk = DependencyRisk(_mock_endpoint(), _payload(), project_key="p")
    with patch.object(risk, "_sca_patch", side_effect=exceptions.SonarException("boom", 1)):
        assert risk._apply_severity_change("BLOCKER") is False


# ---------------------------------------------------------------------------
# apply_changelog
# ---------------------------------------------------------------------------


def test_apply_changelog_applies_events_and_comments() -> None:
    """apply_changelog copies new changelog entries and comments from source to target."""
    source = _make_risk("src", "CVE-X", changelog={"a": _severity_entry("2026-04-01T10:00:00+0000", key_suffix="a")})
    source.comments = {"c1": {"date": datetime(2026, 4, 2, tzinfo=timezone.utc), "event": "comment", "value": "hi", "user": "alice"}}

    target = _make_risk("tgt", "CVE-X")  # no changelog, no comments

    with patch.object(target, "_DependencyRisk__apply_event", return_value=True) as mock_event, patch.object(
        target, "add_comment", return_value=True
    ) as mock_comment:
        count = target.apply_changelog(source, {})

    assert count == 2
    mock_event.assert_called_once()
    mock_comment.assert_called_once_with("hi")


def test_apply_changelog_skips_events_already_applied() -> None:
    """apply_changelog skips changelog entries whose date is not after the target's last change."""
    old_entry = _severity_entry("2026-01-01T10:00:00+0000", key_suffix="old")
    target = _make_risk("tgt", "CVE-X", changelog={"x": _severity_entry("2026-05-01T10:00:00+0000", key_suffix="x")})
    target.comments = {}
    source = _make_risk("src", "CVE-X", changelog={"a": old_entry})
    source.comments = {}

    with patch.object(target, "_DependencyRisk__apply_event") as mock_event, patch.object(target, "add_comment") as mock_comment:
        count = target.apply_changelog(source, {})

    assert count == 0
    mock_event.assert_not_called()
    mock_comment.assert_not_called()


def test_apply_changelog_returns_zero_when_nothing_to_apply() -> None:
    """apply_changelog returns 0 when source has neither new events nor new comments."""
    source = _make_risk("src")
    source.comments = {}
    target = _make_risk("tgt")
    target.comments = {}
    assert target.apply_changelog(source, {}) == 0


# ---------------------------------------------------------------------------
# dependency_risk.get_changelogs (module-level)
# ---------------------------------------------------------------------------


def test_get_changelogs_loads_all_risks() -> None:
    """get_changelogs triggers has_changelog and has_comments on every risk in the list."""
    r1 = _make_risk("r1")
    r2 = _make_risk("r2")
    with patch.object(r1, "has_changelog", return_value=False) as hcl1, patch.object(r1, "has_comments", return_value=False) as hco1, patch.object(
        r2, "has_changelog", return_value=False
    ) as hcl2, patch.object(r2, "has_comments", return_value=False) as hco2:
        dr.get_changelogs([r1, r2])

    hcl1.assert_called_once()
    hco1.assert_called_once()
    hcl2.assert_called_once()
    hco2.assert_called_once()


def test_get_changelogs_survives_exception_on_one_risk() -> None:
    """get_changelogs must not propagate an exception from one risk — it logs and continues."""
    r1 = _make_risk("r1")
    r2 = _make_risk("r2")
    with patch.object(r1, "has_changelog", side_effect=RuntimeError("boom")), patch.object(r2, "has_changelog", return_value=False) as hcl2, patch.object(
        r2, "has_comments", return_value=False
    ) as hco2:
        dr.get_changelogs([r1, r2])  # must not raise

    hcl2.assert_called_once()
    hco2.assert_called_once()
