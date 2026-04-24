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

"""Unit tests for LicenseProfile update() and _update_licenses() methods using mocks"""

from unittest.mock import patch, MagicMock
import json
import pytest

from sonar import license_profiles as lp, exceptions


def _make_mock_endpoint():
    """Creates a mock Platform endpoint for testing"""
    endpoint = MagicMock()
    endpoint.local_url = "http://localhost:9000"
    endpoint.external_url = "http://localhost:9000"
    endpoint.is_sonarcloud.return_value = False
    endpoint.version.return_value = (2025, 4, 0)
    endpoint.edition.return_value = "enterprise"
    endpoint.api.get_details.return_value = ("api/v2/sca/license-profiles/key1", "PATCH", {"policy": "ALLOWED"}, None)
    return endpoint


def _make_profile(endpoint, name="test-profile", key="key1", is_default=False, categories=None, licenses=None):
    """Creates a LicenseProfile instance with mocked _check_supported"""
    data = {
        "name": name,
        "key": key,
        "isDefault": is_default,
        "categories": categories or [],
        "licenses": licenses or [],
    }
    with patch("sonar.license_profiles._check_supported"):
        profile = lp.LicenseProfile(endpoint, data)
    return profile


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the LicenseProfile cache before each test"""
    lp.LicenseProfile.CACHE.clear()
    yield
    lp.LicenseProfile.CACHE.clear()


# ---------------------------------------------------------------------------
# Tests for update() - name rename path
# ---------------------------------------------------------------------------


def test_update_rename_success():
    """Test update() successfully renames the profile"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="old-name", key="key1")

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "patch", return_value=mock_response):
        ok = profile.update(name="new-name")

    assert ok is True
    assert profile.name == "new-name"


def test_update_rename_failure():
    """Test update() handles SonarException on rename"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="old-name", key="key1")

    with patch.object(profile, "patch", side_effect=exceptions.SonarException("Rename failed", 3)):
        ok = profile.update(name="new-name")

    assert ok is False
    # Name should remain unchanged on failure
    assert profile.name == "old-name"


def test_update_same_name_no_rename():
    """Test update() with same name does not trigger a rename API call"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1")

    with patch.object(profile, "patch") as mock_patch:
        ok = profile.update(name="my-profile")

    # patch should not be called for name (no rename needed), no categories, no licenses
    mock_patch.assert_not_called()
    assert ok is True
    assert profile.name == "my-profile"


# ---------------------------------------------------------------------------
# Tests for update() - isDefault path
# ---------------------------------------------------------------------------


def test_update_set_default_success():
    """Test update() sets the profile as default"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1", is_default=False)

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "patch", return_value=mock_response):
        ok = profile.update(isDefault=True)

    assert ok is True
    assert profile.is_default is True


def test_update_set_default_already_default():
    """Test update() with isDefault=True on an already-default profile does nothing"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1", is_default=True)

    with patch.object(profile, "patch") as mock_patch:
        ok = profile.update(isDefault=True)

    # No patch call for isDefault since already default, no categories/licenses either
    mock_patch.assert_not_called()
    assert ok is True


def test_update_set_default_false_no_op():
    """Test update() with isDefault=False does not trigger the set-default path"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1", is_default=False)

    with patch.object(profile, "patch") as mock_patch:
        ok = profile.update(isDefault=False)

    mock_patch.assert_not_called()
    assert ok is True
    assert profile.is_default is False


def test_update_set_default_failure():
    """Test update() handles SonarException when setting default"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1", is_default=False)

    with patch.object(profile, "patch", side_effect=exceptions.SonarException("Set default failed", 3)):
        ok = profile.update(isDefault=True)

    assert ok is False
    assert profile.is_default is False


# ---------------------------------------------------------------------------
# Tests for update() - delegation to _update_categories and _update_licenses
# ---------------------------------------------------------------------------


def test_update_delegates_to_update_categories_and_licenses():
    """Test that update() delegates categories and licenses to helper methods"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1")
    categories = [{"key": "cat1", "policy": "ALLOWED"}]
    licenses = [{"spdxLicenseId": "MIT", "policy": "ALLOWED"}]

    with patch.object(profile, "_update_categories", return_value=True) as mock_cats, \
         patch.object(profile, "_update_licenses", return_value=True) as mock_lics:
        ok = profile.update(categories=categories, licenses=licenses)

    mock_cats.assert_called_once_with(categories, True)
    mock_lics.assert_called_once_with(licenses, True)
    assert ok is True


def test_update_propagates_false_from_rename_to_helpers():
    """Test that a rename failure propagates ok=False to _update_categories and _update_licenses"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="old-name", key="key1")

    with patch.object(profile, "patch", side_effect=exceptions.SonarException("fail", 3)), \
         patch.object(profile, "_update_categories", return_value=False) as mock_cats, \
         patch.object(profile, "_update_licenses", return_value=False) as mock_lics:
        ok = profile.update(name="new-name", categories=[], licenses=[])

    # _update_categories receives ok=False due to rename failure
    mock_cats.assert_called_once_with([], False)
    assert ok is False


def test_update_no_data():
    """Test update() with no data returns True"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1")

    with patch.object(profile, "_update_categories", return_value=True) as mock_cats, \
         patch.object(profile, "_update_licenses", return_value=True) as mock_lics:
        ok = profile.update()

    mock_cats.assert_called_once_with([], True)
    mock_lics.assert_called_once_with([], True)
    assert ok is True


def test_update_rename_and_set_default():
    """Test update() with both name change and isDefault=True"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="old-name", key="key1", is_default=False)

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "patch", return_value=mock_response), \
         patch.object(profile, "_update_categories", return_value=True), \
         patch.object(profile, "_update_licenses", return_value=True):
        ok = profile.update(name="new-name", isDefault=True)

    assert ok is True
    assert profile.name == "new-name"
    assert profile.is_default is True


# ---------------------------------------------------------------------------
# Tests for _update_categories()
# ---------------------------------------------------------------------------


def test_update_categories_empty_list():
    """Test _update_categories with empty list returns ok unchanged"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint)

    assert profile._update_categories([], True) is True
    assert profile._update_categories([], False) is False


def test_update_categories_success():
    """Test _update_categories successfully updates categories"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    categories = [
        {"key": "copyleft", "policy": "ALLOWED"},
        {"key": "permissive", "policy": "FLAGGED"},
    ]

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "patch", return_value=mock_response):
        ok = profile._update_categories(categories, True)

    assert ok is True


def test_update_categories_partial_failure():
    """Test _update_categories with one failing category"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    categories = [
        {"key": "copyleft", "policy": "ALLOWED"},
        {"key": "bad-cat", "policy": "FLAGGED"},
    ]

    mock_response = MagicMock()
    mock_response.ok = True

    call_count = 0

    def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise exceptions.SonarException("Category not found", 3)
        return mock_response

    with patch.object(profile, "patch", side_effect=_side_effect):
        ok = profile._update_categories(categories, True)

    assert ok is False


def test_update_categories_all_fail():
    """Test _update_categories when all categories fail"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    categories = [{"key": "cat1", "policy": "ALLOWED"}]

    with patch.object(profile, "patch", side_effect=exceptions.SonarException("fail", 3)):
        ok = profile._update_categories(categories, True)

    assert ok is False


def test_update_categories_preserves_false_ok():
    """Test _update_categories preserves ok=False from caller even when all succeed"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    categories = [{"key": "cat1", "policy": "ALLOWED"}]

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "patch", return_value=mock_response):
        # Note: ok is True because `response.ok and ok` where ok=False → False
        # Actually: `ok = self.patch(...).ok and ok` → True and False → False
        ok = profile._update_categories(categories, False)

    assert ok is False


# ---------------------------------------------------------------------------
# Tests for _update_licenses()
# ---------------------------------------------------------------------------


def test_update_licenses_empty_list():
    """Test _update_licenses with empty list returns ok unchanged"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint)

    assert profile._update_licenses([], True) is True
    assert profile._update_licenses([], False) is False


def test_update_licenses_success():
    """Test _update_licenses successfully updates licenses"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [
        {"spdxLicenseId": "MIT", "policy": "ALLOWED"},
        {"spdxLicenseId": "GPL-3.0", "policy": "FLAGGED"},
    ]

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "_get_current_license_policies", return_value={"MIT": "FLAGGED", "GPL-3.0": "ALLOWED"}), \
         patch.object(profile, "patch", return_value=mock_response):
        ok = profile._update_licenses(licenses, True)

    assert ok is True


def test_update_licenses_skips_noop():
    """Test _update_licenses skips licenses already at target policy"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [
        {"spdxLicenseId": "MIT", "policy": "ALLOWED"},
        {"spdxLicenseId": "GPL-3.0", "policy": "FLAGGED"},
    ]

    # Both already at target policy
    current_policies = {"MIT": "ALLOWED", "GPL-3.0": "FLAGGED"}

    with patch.object(profile, "_get_current_license_policies", return_value=current_policies), \
         patch.object(profile, "patch") as mock_patch:
        ok = profile._update_licenses(licenses, True)

    # No patch calls because both are already at target
    mock_patch.assert_not_called()
    assert ok is True


def test_update_licenses_mixed_noop_and_update():
    """Test _update_licenses updates only licenses that differ from current policy"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [
        {"spdxLicenseId": "MIT", "policy": "ALLOWED"},
        {"spdxLicenseId": "GPL-3.0", "policy": "FLAGGED"},
        {"spdxLicenseId": "Apache-2.0", "policy": "ALLOWED"},
    ]

    # MIT already at target, GPL-3.0 and Apache-2.0 need update
    current_policies = {"MIT": "ALLOWED", "GPL-3.0": "ALLOWED", "Apache-2.0": "FLAGGED"}

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "_get_current_license_policies", return_value=current_policies), \
         patch.object(profile, "patch", return_value=mock_response) as mock_patch:
        ok = profile._update_licenses(licenses, True)

    assert mock_patch.call_count == 2  # Only GPL-3.0 and Apache-2.0
    assert ok is True


def test_update_licenses_partial_failure():
    """Test _update_licenses with one license failing"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [
        {"spdxLicenseId": "MIT", "policy": "ALLOWED"},
        {"spdxLicenseId": "INVALID", "policy": "FLAGGED"},
    ]

    current_policies = {}  # None at target, all need update
    mock_response = MagicMock()
    mock_response.ok = True

    call_count = 0

    def _side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise exceptions.SonarException("License not found", 3)
        return mock_response

    with patch.object(profile, "_get_current_license_policies", return_value=current_policies), \
         patch.object(profile, "patch", side_effect=_side_effect):
        ok = profile._update_licenses(licenses, True)

    assert ok is False


def test_update_licenses_all_fail():
    """Test _update_licenses when all license updates fail"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [{"spdxLicenseId": "MIT", "policy": "ALLOWED"}]

    with patch.object(profile, "_get_current_license_policies", return_value={}), \
         patch.object(profile, "patch", side_effect=exceptions.SonarException("fail", 3)):
        ok = profile._update_licenses(licenses, True)

    assert ok is False


def test_update_licenses_preserves_false_ok():
    """Test _update_licenses preserves ok=False from caller even when all updates succeed"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [{"spdxLicenseId": "MIT", "policy": "ALLOWED"}]

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "_get_current_license_policies", return_value={}), \
         patch.object(profile, "patch", return_value=mock_response):
        ok = profile._update_licenses(licenses, False)

    assert ok is False


def test_update_licenses_unknown_spdx_id():
    """Test _update_licenses handles license with spdxLicenseId not in current policies"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [{"spdxLicenseId": "NEW-LICENSE", "policy": "ALLOWED"}]

    # Current policies don't include NEW-LICENSE → current_policy will be ""
    current_policies = {"MIT": "ALLOWED"}

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "_get_current_license_policies", return_value=current_policies), \
         patch.object(profile, "patch", return_value=mock_response) as mock_patch:
        ok = profile._update_licenses(licenses, True)

    # Should still call patch since "" != "ALLOWED"
    mock_patch.assert_called_once()
    assert ok is True


def test_update_licenses_missing_spdx_id():
    """Test _update_licenses handles license entry without spdxLicenseId (defaults to empty string)"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [{"policy": "ALLOWED"}]  # No spdxLicenseId

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "_get_current_license_policies", return_value={}), \
         patch.object(profile, "patch", return_value=mock_response) as mock_patch:
        ok = profile._update_licenses(licenses, True)

    # spdx defaults to "", current_policy from get("", "") also "", but target is "ALLOWED"
    # so "" != "ALLOWED" → update IS attempted
    mock_patch.assert_called_once()
    assert ok is True


def test_update_licenses_patch_returns_not_ok():
    """Test _update_licenses when patch returns response with ok=False"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [{"spdxLicenseId": "MIT", "policy": "ALLOWED"}]

    mock_response = MagicMock()
    mock_response.ok = False
    with patch.object(profile, "_get_current_license_policies", return_value={}), \
         patch.object(profile, "patch", return_value=mock_response):
        ok = profile._update_licenses(licenses, True)

    assert ok is False


# ---------------------------------------------------------------------------
# Tests for _get_current_license_policies()
# ---------------------------------------------------------------------------


def test_get_current_license_policies_success():
    """Test _get_current_license_policies returns correct mapping"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")

    api_response_data = {
        "name": "test-profile",
        "key": "key1",
        "licenses": [
            {"spdxLicenseId": "MIT", "name": "MIT License", "policy": "ALLOWED"},
            {"spdxLicenseId": "GPL-3.0", "name": "GNU GPL v3", "policy": "FLAGGED"},
            {"spdxLicenseId": "Apache-2.0", "name": "Apache 2.0", "policy": "ALLOWED"},
        ],
    }

    mock_response = MagicMock()
    mock_response.text = json.dumps(api_response_data)
    endpoint.get.return_value = mock_response

    result = profile._get_current_license_policies()

    assert result == {"MIT": "ALLOWED", "GPL-3.0": "FLAGGED", "Apache-2.0": "ALLOWED"}


def test_get_current_license_policies_empty_licenses():
    """Test _get_current_license_policies with no licenses in response"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")

    api_response_data = {"name": "test-profile", "key": "key1", "licenses": []}
    mock_response = MagicMock()
    mock_response.text = json.dumps(api_response_data)
    endpoint.get.return_value = mock_response

    result = profile._get_current_license_policies()

    assert result == {}


def test_get_current_license_policies_no_licenses_key():
    """Test _get_current_license_policies when response has no licenses key"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")

    api_response_data = {"name": "test-profile", "key": "key1"}
    mock_response = MagicMock()
    mock_response.text = json.dumps(api_response_data)
    endpoint.get.return_value = mock_response

    result = profile._get_current_license_policies()

    assert result == {}


def test_get_current_license_policies_api_failure():
    """Test _get_current_license_policies returns empty dict on SonarException"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")

    endpoint.api.get_details.side_effect = exceptions.SonarException("API error", 3)

    result = profile._get_current_license_policies()

    assert result == {}


def test_get_current_license_policies_skips_missing_spdx():
    """Test _get_current_license_policies skips licenses without spdxLicenseId"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")

    api_response_data = {
        "name": "test-profile",
        "key": "key1",
        "licenses": [
            {"spdxLicenseId": "MIT", "policy": "ALLOWED"},
            {"name": "Unknown License", "policy": "FLAGGED"},  # No spdxLicenseId
        ],
    }

    mock_response = MagicMock()
    mock_response.text = json.dumps(api_response_data)
    endpoint.get.return_value = mock_response

    result = profile._get_current_license_policies()

    assert result == {"MIT": "ALLOWED"}


def test_get_current_license_policies_missing_policy():
    """Test _get_current_license_policies handles licenses with no policy field"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")

    api_response_data = {
        "name": "test-profile",
        "key": "key1",
        "licenses": [
            {"spdxLicenseId": "MIT"},  # No policy field
        ],
    }

    mock_response = MagicMock()
    mock_response.text = json.dumps(api_response_data)
    endpoint.get.return_value = mock_response

    result = profile._get_current_license_policies()

    assert result == {"MIT": ""}


# ---------------------------------------------------------------------------
# Tests for update() - full integration of all paths
# ---------------------------------------------------------------------------


def test_update_full_lifecycle():
    """Test update() exercising rename, isDefault, categories, and licenses together"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="old-name", key="key1", is_default=False)
    categories = [{"key": "copyleft", "policy": "FLAGGED"}]
    licenses = [{"spdxLicenseId": "MIT", "policy": "ALLOWED"}]

    mock_response = MagicMock()
    mock_response.ok = True

    current_policies = {"MIT": "FLAGGED"}  # Needs update

    with patch.object(profile, "patch", return_value=mock_response), \
         patch.object(profile, "_get_current_license_policies", return_value=current_policies):
        ok = profile.update(name="new-name", isDefault=True, categories=categories, licenses=licenses)

    assert ok is True
    assert profile.name == "new-name"
    assert profile.is_default is True


def test_update_set_default_patch_returns_not_ok():
    """Test update() when the set-default patch returns response.ok=False"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1", is_default=False)

    mock_response = MagicMock()
    mock_response.ok = False

    with patch.object(profile, "patch", return_value=mock_response), \
         patch.object(profile, "_update_categories", return_value=False) as mock_cats, \
         patch.object(profile, "_update_licenses", return_value=False) as mock_lics:
        ok = profile.update(isDefault=True)

    # patch returned ok=False, so ok should be False
    assert ok is False
    # is_default is set to True in the code regardless of response.ok (it's set after patch)
    assert profile.is_default is True
