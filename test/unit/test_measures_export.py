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

"""Unit tests for cli.measures_export default-metric-list selection (no live SonarQube required)."""

from unittest.mock import MagicMock, patch

from cli import measures_export
from sonar import metrics


def _mock_endpoint(version=(2025, 4, 0), edition="enterprise") -> MagicMock:
    endpoint = MagicMock()
    endpoint.local_url = "http://localhost:9000"
    endpoint.is_sonarcloud.return_value = False
    endpoint.version.return_value = version
    endpoint.edition.return_value = edition
    return endpoint


def _fake_metric(key: str, domain: str) -> MagicMock:
    m = MagicMock()
    m.key = key
    m.domain = domain
    return m


_SCA_KEYS = (
    "sca_count_any_issue",
    "sca_count_any_security",
    "sca_count_licensing",
    "sca_count_malware",
    "sca_count_vulnerability",
    "sca_rating_any_issue",
    "sca_rating_any_security",
    "sca_rating_licensing",
    "sca_rating_malware",
    "sca_rating_vulnerability",
    "new_sca_count_any_issue",
    "new_sca_count_any_security",
    "new_sca_count_licensing",
    "new_sca_count_malware",
    "new_sca_count_vulnerability",
    "new_sca_rating_any_issue",
    "new_sca_rating_any_security",
    "new_sca_rating_licensing",
    "new_sca_rating_malware",
    "new_sca_rating_vulnerability",
)


def _platform_metrics() -> dict[str, MagicMock]:
    """Mimics what Metric.search returns: a mix of regular + SCA metrics."""
    out = {k: _fake_metric(k, "DependencyRisks") for k in _SCA_KEYS}
    for k in ("ncloc", "violations", "bugs", "coverage"):
        out[k] = _fake_metric(k, "Size")
    out["contains_ai_code"] = _fake_metric("contains_ai_code", "General")
    out["quality_gate_details"] = _fake_metric("quality_gate_details", "General")
    return out


def test_main_includes_all_sca_metrics_when_sca_enabled() -> None:
    endpoint = _mock_endpoint()
    with (
        patch("cli.measures_export.dependency_risks.sca_enabled", return_value=True),
        patch("sonar.metrics.Metric.search", return_value=_platform_metrics()),
    ):
        wanted = measures_export._get_wanted_metrics(endpoint, {"_main"})
    for sca_key in _SCA_KEYS:
        assert sca_key in wanted, f"missing SCA metric {sca_key} in default _main export"


def test_main_excludes_sca_metrics_when_sca_disabled() -> None:
    endpoint = _mock_endpoint()
    with patch("cli.measures_export.dependency_risks.sca_enabled", return_value=False):
        wanted = measures_export._get_wanted_metrics(endpoint, {"_main"})
    assert not any(k.startswith(("sca_", "new_sca_")) for k in wanted)


def test_main_excludes_sca_on_old_server_without_sca() -> None:
    """EE 2025.3 without the SCA add-on must not request sca_* keys."""
    endpoint = _mock_endpoint(version=(2025, 3, 0), edition="enterprise")
    with patch("cli.measures_export.dependency_risks.sca_enabled", return_value=False):
        wanted = measures_export._get_wanted_metrics(endpoint, {"_main"})
    assert not any(k.startswith(("sca_", "new_sca_")) for k in wanted)
    assert "contains_ai_code" in wanted  # AI Code Assurance still in default for 2025.3 EE


def test_all_mode_with_sca_includes_sca_and_excludes_quality_gate_details() -> None:
    """With --metricKeys _all, SCA keys are present and quality_gate_details is pruned."""
    endpoint = _mock_endpoint()
    with (
        patch("cli.measures_export.dependency_risks.sca_enabled", return_value=True),
        patch("sonar.metrics.Metric.search", return_value=_platform_metrics()),
    ):
        wanted = measures_export._get_wanted_metrics(endpoint, {"_all"})
    for sca_key in _SCA_KEYS:
        assert sca_key in wanted
    assert "quality_gate_details" not in wanted
    # Each metric appears exactly once (dedupe via dict.fromkeys at end of helper)
    assert len(wanted) == len(set(wanted))


def test_sca_metrics_helper_filters_by_domain() -> None:
    endpoint = _mock_endpoint()
    with patch("sonar.metrics.Metric.search", return_value=_platform_metrics()):
        result = metrics.sca_metrics(endpoint)
    assert set(result) == set(_SCA_KEYS)
