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

"""License profiles tests"""

import json
import os
from unittest.mock import patch, MagicMock
import pytest

import utilities as tutil
from sonar import license_profiles as lp, exceptions
from sonar.util import constants as c

TEMP_LP_NAME = f"TEMP-license-profile-{os.getpid()}"
_UNSUPPORTED_MSG = "License profiles require SonarQube Server 2025.4+ Enterprise or Data Center Edition, or SonarQube Cloud with SCA enabled"


# ---------------------------------------------------------------------------
# Helpers for integration tests (require running SonarQube instance)
# ---------------------------------------------------------------------------


def _sca_available() -> bool:
    """Checks if SCA is available on the test platform"""
    return lp.sca_enabled(tutil.SQ)


def _skip_if_unsupported() -> None:
    """Skips the test if the platform does not support license profiles"""
    if not _sca_available():
        pytest.skip(_UNSUPPORTED_MSG)


def _get_existing_profile_data() -> dict:
    """Returns exported JSON data from an existing profile that has categories/licenses"""
    profiles = lp.LicenseProfile.search(endpoint=tutil.SQ)
    for profile in profiles.values():
        data = profile.to_json(export_settings={"FULL_EXPORT": True})
        if data.get("categories") or data.get("licenses"):
            return data
    # Fallback: return first profile data even without categories/licenses
    return next(iter(profiles.values())).to_json(export_settings={"FULL_EXPORT": True})


# ---------------------------------------------------------------------------
# Helpers for unit tests (mocked, no SonarQube instance needed)
# ---------------------------------------------------------------------------


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
        return lp.LicenseProfile(endpoint, data)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the LicenseProfile cache before and after each test"""
    lp.LicenseProfile.CACHE.clear()
    yield
    lp.LicenseProfile.CACHE.clear()


# ===========================================================================
# Integration tests (require running SonarQube instance with SCA)
# ===========================================================================


def test_check_supported_unsupported_edition() -> None:
    """Test _check_supported raises on Community Build"""
    if tutil.SQ.edition() in ("enterprise", "datacenter") or tutil.SQ.is_sonarcloud():
        pytest.skip("Test only applies to CE/DE editions")
    with pytest.raises(exceptions.UnsupportedOperation):
        lp._check_supported(tutil.SQ)


def test_sca_enabled() -> None:
    """Test sca_enabled returns a bool"""
    result = lp.sca_enabled(tutil.SQ)
    assert isinstance(result, bool)


def test_search() -> None:
    """Test searching for license profiles"""
    _skip_if_unsupported()
    profiles = lp.LicenseProfile.search(endpoint=tutil.SQ)
    assert isinstance(profiles, dict)
    # At least one default profile should exist
    assert len(profiles) >= 1
    for name, profile in profiles.items():
        assert isinstance(name, str)
        assert isinstance(profile, lp.LicenseProfile)
        assert profile.name == name


def test_search_with_cache() -> None:
    """Test that search with use_cache=True returns cached results"""
    _skip_if_unsupported()
    # First search populates the cache
    profiles1 = lp.LicenseProfile.search(endpoint=tutil.SQ)
    # Second search with use_cache=True should return from cache
    profiles2 = lp.LicenseProfile.search(endpoint=tutil.SQ, use_cache=True)
    assert len(profiles1) == len(profiles2)
    for name in profiles1:
        assert name in profiles2


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    _skip_if_unsupported()
    profiles = lp.LicenseProfile.search(endpoint=tutil.SQ)
    assert len(profiles) >= 1
    first_name = next(iter(profiles))
    obj = lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=first_name)
    assert obj.name == first_name
    assert str(obj) == f"license profile '{first_name}'"
    # Second call should return the same cached object
    obj2 = lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=first_name)
    assert obj2 is obj


def test_get_object_use_cache_false() -> None:
    """Test get_object with use_cache=False bypasses cache"""
    _skip_if_unsupported()
    profiles = lp.LicenseProfile.search(endpoint=tutil.SQ)
    first_name = next(iter(profiles))
    # Ensure it's in cache first
    lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=first_name)
    # With use_cache=False, should re-fetch from API
    obj2 = lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=first_name, use_cache=False)
    assert obj2.name == first_name


def test_get_object_not_found() -> None:
    """Test get_object raises ObjectNotFound for non-existing profile"""
    _skip_if_unsupported()
    with pytest.raises(exceptions.ObjectNotFound) as e:
        lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=tutil.NON_EXISTING_KEY)
    assert tutil.NON_EXISTING_KEY in str(e.value)


def test_exists() -> None:
    """Test exists method"""
    _skip_if_unsupported()
    profiles = lp.LicenseProfile.search(endpoint=tutil.SQ)
    first_name = next(iter(profiles))
    assert lp.LicenseProfile.exists(endpoint=tutil.SQ, name=first_name)
    assert not lp.LicenseProfile.exists(endpoint=tutil.SQ, name=tutil.NON_EXISTING_KEY)


def test_str() -> None:
    """Test __str__ representation"""
    _skip_if_unsupported()
    profiles = lp.LicenseProfile.search(endpoint=tutil.SQ)
    first_name = next(iter(profiles))
    obj = lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=first_name)
    assert str(obj) == f"license profile '{first_name}'"


def test_url() -> None:
    """Test url generation"""
    _skip_if_unsupported()
    profiles = lp.LicenseProfile.search(endpoint=tutil.SQ)
    first_name = next(iter(profiles))
    obj = lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=first_name)
    url = obj.url()
    assert "/sca/license-profiles/" in url
    assert obj.key in url


def test_hash_payload() -> None:
    """Test hash_payload returns name tuple"""
    data = {"name": "test-profile", "key": "k1"}
    assert lp.LicenseProfile.hash_payload(data) == ("test-profile",)


def test_hash_object() -> None:
    """Test hash_object returns name tuple"""
    _skip_if_unsupported()
    profiles = lp.LicenseProfile.search(endpoint=tutil.SQ)
    first_name = next(iter(profiles))
    obj = lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=first_name)
    assert obj.hash_object() == (first_name,)


def test_to_json() -> None:
    """Test JSON export of a license profile"""
    _skip_if_unsupported()
    profiles = lp.LicenseProfile.search(endpoint=tutil.SQ)
    first_name = next(iter(profiles))
    obj = lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=first_name)
    json_data = obj.to_json(export_settings={})
    assert "name" in json_data
    assert json_data["name"] == first_name


def test_to_json_full_export() -> None:
    """Test JSON export with FULL_EXPORT setting"""
    _skip_if_unsupported()
    profiles = lp.LicenseProfile.search(endpoint=tutil.SQ)
    first_name = next(iter(profiles))
    obj = lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=first_name)
    json_data = obj.to_json(export_settings={"FULL_EXPORT": True})
    assert "name" in json_data
    assert "isDefault" in json_data


def test_export() -> None:
    """Test export function"""
    _skip_if_unsupported()
    result = lp.export(endpoint=tutil.SQ, export_settings={})
    assert isinstance(result, list)
    if len(result) > 0:
        assert "name" in result[0]


def test_export_sca_disabled() -> None:
    """Test export when SCA is not available returns empty list"""
    if _sca_available():
        pytest.skip("Test only applies when SCA is disabled")
    result = lp.export(endpoint=tutil.SQ, export_settings={})
    assert result == []


def test_import_config_no_key() -> None:
    """Test import_config with no license profiles key in config"""
    result = lp.import_config(endpoint=tutil.SQ, config_data={})
    assert result is True


def test_import_config_sca_disabled() -> None:
    """Test import_config when SCA is not available returns True"""
    if _sca_available():
        pytest.skip("Test only applies when SCA is disabled")
    config = {c.CONFIG_KEY_LICENSE_PROFILES: [{"name": "test"}]}
    result = lp.import_config(endpoint=tutil.SQ, config_data=config)
    assert result is True


def test_create_and_delete() -> None:
    """Test create and delete of a license profile"""
    _skip_if_unsupported()
    # Create
    obj = lp.LicenseProfile.create(endpoint=tutil.SQ, name=TEMP_LP_NAME)
    assert obj.name == TEMP_LP_NAME
    assert lp.LicenseProfile.exists(endpoint=tutil.SQ, name=TEMP_LP_NAME)
    # Delete
    assert obj.delete()
    lp.LicenseProfile.CACHE.clear()
    assert not lp.LicenseProfile.exists(endpoint=tutil.SQ, name=TEMP_LP_NAME)


def test_create_update_delete() -> None:
    """Test create, update, and delete lifecycle"""
    _skip_if_unsupported()
    name = f"{TEMP_LP_NAME}-update"
    obj = lp.LicenseProfile.create(endpoint=tutil.SQ, name=name)
    assert obj.name == name

    # Update name
    new_name = f"{name}-renamed"
    ok = obj.update(name=new_name)
    assert ok
    assert obj.name == new_name

    # Clean up
    obj.delete()
    lp.LicenseProfile.CACHE.clear()
    assert not lp.LicenseProfile.exists(endpoint=tutil.SQ, name=new_name)


def test_reload() -> None:
    """Test reload updates object data"""
    _skip_if_unsupported()
    profiles = lp.LicenseProfile.search(endpoint=tutil.SQ)
    first_name = next(iter(profiles))
    obj = lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=first_name)
    json_data = obj.to_json(export_settings={"FULL_EXPORT": True})
    result = obj.reload(json_data)
    assert result is obj
    assert result.is_default == json_data.get("isDefault", False)


def test_import_config_create_and_update() -> None:
    """Test import_config creates new profiles and updates existing ones"""
    _skip_if_unsupported()
    name = f"{TEMP_LP_NAME}-import"
    config = {c.CONFIG_KEY_LICENSE_PROFILES: [{"name": name}]}
    ok = lp.import_config(endpoint=tutil.SQ, config_data=config)
    assert ok
    assert lp.LicenseProfile.exists(endpoint=tutil.SQ, name=name)

    # Import again (update path)
    ok = lp.import_config(endpoint=tutil.SQ, config_data=config)
    assert ok

    # Clean up
    obj = lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=name)
    obj.delete()
    lp.LicenseProfile.CACHE.clear()


def test_update_categories() -> None:
    """Test update with categories exercises _update_categories"""
    _skip_if_unsupported()
    ref_data = _get_existing_profile_data()
    categories = ref_data.get("categories", [])
    if not categories:
        pytest.skip("No categories found on existing profiles to test with")

    name = f"{TEMP_LP_NAME}-cat"
    obj = lp.LicenseProfile.create(endpoint=tutil.SQ, name=name)
    try:
        ok = obj.update(categories=categories)
        assert isinstance(ok, bool)
    finally:
        obj.delete()
        lp.LicenseProfile.CACHE.clear()


def test_update_licenses() -> None:
    """Test update with licenses exercises _update_licenses and _get_current_license_policies"""
    _skip_if_unsupported()
    ref_data = _get_existing_profile_data()
    licenses = ref_data.get("licenses", [])
    if not licenses:
        pytest.skip("No licenses found on existing profiles to test with")

    name = f"{TEMP_LP_NAME}-lic"
    obj = lp.LicenseProfile.create(endpoint=tutil.SQ, name=name)
    try:
        # First update: applies license policies (exercises _update_licenses + _get_current_license_policies)
        ok = obj.update(licenses=licenses[:3])
        assert isinstance(ok, bool)
        # Second update with same data: exercises the no-op skip path in _update_licenses
        ok = obj.update(licenses=licenses[:3])
        assert isinstance(ok, bool)
    finally:
        obj.delete()
        lp.LicenseProfile.CACHE.clear()


def test_update_set_default() -> None:
    """Test update with isDefault=True exercises the set-default path"""
    _skip_if_unsupported()
    name = f"{TEMP_LP_NAME}-default"
    obj = lp.LicenseProfile.create(endpoint=tutil.SQ, name=name)
    try:
        assert not obj.is_default
        ok = obj.update(isDefault=True)
        assert isinstance(ok, bool)
        if ok:
            assert obj.is_default
    finally:
        # Restore a different profile as default before cleanup
        profiles = lp.LicenseProfile.search(endpoint=tutil.SQ, use_cache=False)
        for profile in profiles.values():
            if profile.name != name and not profile.is_default:
                profile.update(isDefault=True)
                break
        obj.delete()
        lp.LicenseProfile.CACHE.clear()


def test_update_no_op_same_name() -> None:
    """Test update with same name does not trigger rename"""
    _skip_if_unsupported()
    name = f"{TEMP_LP_NAME}-noop"
    obj = lp.LicenseProfile.create(endpoint=tutil.SQ, name=name)
    try:
        ok = obj.update(name=name)
        assert ok
        assert obj.name == name
    finally:
        obj.delete()
        lp.LicenseProfile.CACHE.clear()


def test_update_empty_categories_and_licenses() -> None:
    """Test update with empty categories and licenses lists"""
    _skip_if_unsupported()
    name = f"{TEMP_LP_NAME}-empty"
    obj = lp.LicenseProfile.create(endpoint=tutil.SQ, name=name)
    try:
        ok = obj.update(categories=[], licenses=[])
        assert ok
    finally:
        obj.delete()
        lp.LicenseProfile.CACHE.clear()


def test_update_all_fields() -> None:
    """Test update with name, categories, and licenses together"""
    _skip_if_unsupported()
    ref_data = _get_existing_profile_data()
    categories = ref_data.get("categories", [])
    licenses = ref_data.get("licenses", [])

    name = f"{TEMP_LP_NAME}-all"
    new_name = f"{name}-renamed"
    obj = lp.LicenseProfile.create(endpoint=tutil.SQ, name=name)
    try:
        ok = obj.update(name=new_name, categories=categories[:2], licenses=licenses[:2])
        assert isinstance(ok, bool)
        assert obj.name == new_name
    finally:
        obj.delete()
        lp.LicenseProfile.CACHE.clear()


def test_import_config_with_categories_and_licenses() -> None:
    """Test import_config with full profile data including categories and licenses"""
    _skip_if_unsupported()
    ref_data = _get_existing_profile_data()
    categories = ref_data.get("categories", [])[:2]
    licenses = ref_data.get("licenses", [])[:2]

    name = f"{TEMP_LP_NAME}-full-import"
    config_entry = {"name": name}
    if categories:
        config_entry["categories"] = categories
    if licenses:
        config_entry["licenses"] = licenses
    config = {c.CONFIG_KEY_LICENSE_PROFILES: [config_entry]}

    ok = lp.import_config(endpoint=tutil.SQ, config_data=config)
    assert ok
    assert lp.LicenseProfile.exists(endpoint=tutil.SQ, name=name)

    # Clean up
    obj = lp.LicenseProfile.get_object(endpoint=tutil.SQ, name=name)
    obj.delete()
    lp.LicenseProfile.CACHE.clear()


def test_get_full_profile_with_complete_data() -> None:
    """Test _get_full_profile returns data as-is when already complete"""
    data = {"name": "test", "key": "k1", "categories": [{"key": "cat1", "policy": "ALLOWED"}], "licenses": []}
    result = lp._get_full_profile(tutil.SQ, data)
    assert result is data


def test_get_full_profile_no_key() -> None:
    """Test _get_full_profile returns data as-is when no key present"""
    data = {"name": "test"}
    result = lp._get_full_profile(tutil.SQ, data)
    assert result is data


# ===========================================================================
# Unit tests for update() and _update_licenses() using mocks
# ===========================================================================


# ---------------------------------------------------------------------------
# Tests for update() - name rename path
# ---------------------------------------------------------------------------


def test_mock_update_rename_success():
    """Test update() successfully renames the profile"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="old-name", key="key1")

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "patch", return_value=mock_response):
        ok = profile.update(name="new-name")

    assert ok is True
    assert profile.name == "new-name"


def test_mock_update_rename_failure():
    """Test update() handles SonarException on rename"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="old-name", key="key1")

    with patch.object(profile, "patch", side_effect=exceptions.SonarException("Rename failed", 3)):
        ok = profile.update(name="new-name")

    assert ok is False
    # Name should remain unchanged on failure
    assert profile.name == "old-name"


def test_mock_update_same_name_no_rename():
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


def test_mock_update_set_default_success():
    """Test update() sets the profile as default"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1", is_default=False)

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "patch", return_value=mock_response):
        ok = profile.update(isDefault=True)

    assert ok is True
    assert profile.is_default is True


def test_mock_update_set_default_already_default():
    """Test update() with isDefault=True on an already-default profile does nothing"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1", is_default=True)

    with patch.object(profile, "patch") as mock_patch:
        ok = profile.update(isDefault=True)

    # No patch call for isDefault since already default, no categories/licenses either
    mock_patch.assert_not_called()
    assert ok is True


def test_mock_update_set_default_false_no_op():
    """Test update() with isDefault=False does not trigger the set-default path"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1", is_default=False)

    with patch.object(profile, "patch") as mock_patch:
        ok = profile.update(isDefault=False)

    mock_patch.assert_not_called()
    assert ok is True
    assert profile.is_default is False


def test_mock_update_set_default_failure():
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


def test_mock_update_delegates_to_update_categories_and_licenses():
    """Test that update() delegates categories and licenses to helper methods"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1")
    categories = [{"key": "cat1", "policy": "ALLOWED"}]
    licenses = [{"spdxLicenseId": "MIT", "policy": "ALLOWED"}]

    with (
        patch.object(profile, "_update_categories", return_value=True) as mock_cats,
        patch.object(profile, "_update_licenses", return_value=True) as mock_lics,
    ):
        ok = profile.update(categories=categories, licenses=licenses)

    mock_cats.assert_called_once_with(categories, True)
    mock_lics.assert_called_once_with(licenses, True)
    assert ok is True


def test_mock_update_propagates_false_from_rename_to_helpers():
    """Test that a rename failure propagates ok=False to _update_categories and _update_licenses"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="old-name", key="key1")

    with (
        patch.object(profile, "patch", side_effect=exceptions.SonarException("fail", 3)),
        patch.object(profile, "_update_categories", return_value=False) as mock_cats,
        patch.object(profile, "_update_licenses", return_value=False) as mock_lics,
    ):
        ok = profile.update(name="new-name", categories=[], licenses=[])

    # _update_categories receives ok=False due to rename failure
    mock_cats.assert_called_once_with([], False)
    assert ok is False


def test_mock_update_no_data():
    """Test update() with no data returns True"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1")

    with (
        patch.object(profile, "_update_categories", return_value=True) as mock_cats,
        patch.object(profile, "_update_licenses", return_value=True) as mock_lics,
    ):
        ok = profile.update()

    mock_cats.assert_called_once_with([], True)
    mock_lics.assert_called_once_with([], True)
    assert ok is True


def test_mock_update_rename_and_set_default():
    """Test update() with both name change and isDefault=True"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="old-name", key="key1", is_default=False)

    mock_response = MagicMock()
    mock_response.ok = True
    with (
        patch.object(profile, "patch", return_value=mock_response),
        patch.object(profile, "_update_categories", return_value=True),
        patch.object(profile, "_update_licenses", return_value=True),
    ):
        ok = profile.update(name="new-name", isDefault=True)

    assert ok is True
    assert profile.name == "new-name"
    assert profile.is_default is True


# ---------------------------------------------------------------------------
# Tests for _update_categories()
# ---------------------------------------------------------------------------


def test_mock_update_categories_empty_list():
    """Test _update_categories with empty list returns ok unchanged"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint)

    assert profile._update_categories([], True) is True
    assert profile._update_categories([], False) is False


def test_mock_update_categories_success():
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


def test_mock_update_categories_partial_failure():
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


def test_mock_update_categories_all_fail():
    """Test _update_categories when all categories fail"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    categories = [{"key": "cat1", "policy": "ALLOWED"}]

    with patch.object(profile, "patch", side_effect=exceptions.SonarException("fail", 3)):
        ok = profile._update_categories(categories, True)

    assert ok is False


def test_mock_update_categories_preserves_false_ok():
    """Test _update_categories preserves ok=False from caller even when all succeed"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    categories = [{"key": "cat1", "policy": "ALLOWED"}]

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "patch", return_value=mock_response):
        # ok = self.patch(...).ok and ok → True and False → False
        ok = profile._update_categories(categories, False)

    assert ok is False


# ---------------------------------------------------------------------------
# Tests for _update_licenses()
# ---------------------------------------------------------------------------


def test_mock_update_licenses_empty_list():
    """Test _update_licenses with empty list returns ok unchanged"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint)

    assert profile._update_licenses([], True) is True
    assert profile._update_licenses([], False) is False


def test_mock_update_licenses_success():
    """Test _update_licenses successfully updates licenses"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [
        {"spdxLicenseId": "MIT", "policy": "ALLOWED"},
        {"spdxLicenseId": "GPL-3.0", "policy": "FLAGGED"},
    ]

    mock_response = MagicMock()
    mock_response.ok = True
    with (
        patch.object(profile, "_get_current_license_policies", return_value={"MIT": "FLAGGED", "GPL-3.0": "ALLOWED"}),
        patch.object(profile, "patch", return_value=mock_response),
    ):
        ok = profile._update_licenses(licenses, True)

    assert ok is True


def test_mock_update_licenses_skips_noop():
    """Test _update_licenses skips licenses already at target policy"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [
        {"spdxLicenseId": "MIT", "policy": "ALLOWED"},
        {"spdxLicenseId": "GPL-3.0", "policy": "FLAGGED"},
    ]

    # Both already at target policy
    current_policies = {"MIT": "ALLOWED", "GPL-3.0": "FLAGGED"}

    with patch.object(profile, "_get_current_license_policies", return_value=current_policies), patch.object(profile, "patch") as mock_patch:
        ok = profile._update_licenses(licenses, True)

    # No patch calls because both are already at target
    mock_patch.assert_not_called()
    assert ok is True


def test_mock_update_licenses_mixed_noop_and_update():
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
    with (
        patch.object(profile, "_get_current_license_policies", return_value=current_policies),
        patch.object(profile, "patch", return_value=mock_response) as mock_patch,
    ):
        ok = profile._update_licenses(licenses, True)

    assert mock_patch.call_count == 2  # Only GPL-3.0 and Apache-2.0
    assert ok is True


def test_mock_update_licenses_partial_failure():
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

    with (
        patch.object(profile, "_get_current_license_policies", return_value=current_policies),
        patch.object(profile, "patch", side_effect=_side_effect),
    ):
        ok = profile._update_licenses(licenses, True)

    assert ok is False


def test_mock_update_licenses_all_fail():
    """Test _update_licenses when all license updates fail"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [{"spdxLicenseId": "MIT", "policy": "ALLOWED"}]

    with (
        patch.object(profile, "_get_current_license_policies", return_value={}),
        patch.object(profile, "patch", side_effect=exceptions.SonarException("fail", 3)),
    ):
        ok = profile._update_licenses(licenses, True)

    assert ok is False


def test_mock_update_licenses_preserves_false_ok():
    """Test _update_licenses preserves ok=False from caller even when all updates succeed"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [{"spdxLicenseId": "MIT", "policy": "ALLOWED"}]

    mock_response = MagicMock()
    mock_response.ok = True
    with patch.object(profile, "_get_current_license_policies", return_value={}), patch.object(profile, "patch", return_value=mock_response):
        ok = profile._update_licenses(licenses, False)

    assert ok is False


def test_mock_update_licenses_unknown_spdx_id():
    """Test _update_licenses handles license with spdxLicenseId not in current policies"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [{"spdxLicenseId": "NEW-LICENSE", "policy": "ALLOWED"}]

    # Current policies don't include NEW-LICENSE → current_policy will be ""
    current_policies = {"MIT": "ALLOWED"}

    mock_response = MagicMock()
    mock_response.ok = True
    with (
        patch.object(profile, "_get_current_license_policies", return_value=current_policies),
        patch.object(profile, "patch", return_value=mock_response) as mock_patch,
    ):
        ok = profile._update_licenses(licenses, True)

    # Should still call patch since "" != "ALLOWED"
    mock_patch.assert_called_once()
    assert ok is True


def test_mock_update_licenses_missing_spdx_id():
    """Test _update_licenses handles license entry without spdxLicenseId (defaults to empty string)"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [{"policy": "ALLOWED"}]  # No spdxLicenseId

    mock_response = MagicMock()
    mock_response.ok = True
    with (
        patch.object(profile, "_get_current_license_policies", return_value={}),
        patch.object(profile, "patch", return_value=mock_response) as mock_patch,
    ):
        ok = profile._update_licenses(licenses, True)

    # spdx defaults to "", current_policy from get("", "") also "", but target is "ALLOWED"
    # so "" != "ALLOWED" → update IS attempted
    mock_patch.assert_called_once()
    assert ok is True


def test_mock_update_licenses_patch_returns_not_ok():
    """Test _update_licenses when patch returns response with ok=False"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")
    licenses = [{"spdxLicenseId": "MIT", "policy": "ALLOWED"}]

    mock_response = MagicMock()
    mock_response.ok = False
    with patch.object(profile, "_get_current_license_policies", return_value={}), patch.object(profile, "patch", return_value=mock_response):
        ok = profile._update_licenses(licenses, True)

    assert ok is False


# ---------------------------------------------------------------------------
# Tests for _get_current_license_policies()
# ---------------------------------------------------------------------------


def test_mock_get_current_license_policies_success():
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


def test_mock_get_current_license_policies_empty_licenses():
    """Test _get_current_license_policies with no licenses in response"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")

    api_response_data = {"name": "test-profile", "key": "key1", "licenses": []}
    mock_response = MagicMock()
    mock_response.text = json.dumps(api_response_data)
    endpoint.get.return_value = mock_response

    result = profile._get_current_license_policies()

    assert result == {}


def test_mock_get_current_license_policies_no_licenses_key():
    """Test _get_current_license_policies when response has no licenses key"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")

    api_response_data = {"name": "test-profile", "key": "key1"}
    mock_response = MagicMock()
    mock_response.text = json.dumps(api_response_data)
    endpoint.get.return_value = mock_response

    result = profile._get_current_license_policies()

    assert result == {}


def test_mock_get_current_license_policies_api_failure():
    """Test _get_current_license_policies returns empty dict on SonarException"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, key="key1")

    endpoint.api.get_details.side_effect = exceptions.SonarException("API error", 3)

    result = profile._get_current_license_policies()

    assert result == {}


def test_mock_get_current_license_policies_skips_missing_spdx():
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


def test_mock_get_current_license_policies_missing_policy():
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
# Tests for update() - full integration of all mocked paths
# ---------------------------------------------------------------------------


def test_mock_update_full_lifecycle():
    """Test update() exercising rename, isDefault, categories, and licenses together"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="old-name", key="key1", is_default=False)
    categories = [{"key": "copyleft", "policy": "FLAGGED"}]
    licenses = [{"spdxLicenseId": "MIT", "policy": "ALLOWED"}]

    mock_response = MagicMock()
    mock_response.ok = True

    current_policies = {"MIT": "FLAGGED"}  # Needs update

    with (
        patch.object(profile, "patch", return_value=mock_response),
        patch.object(profile, "_get_current_license_policies", return_value=current_policies),
    ):
        ok = profile.update(name="new-name", isDefault=True, categories=categories, licenses=licenses)

    assert ok is True
    assert profile.name == "new-name"
    assert profile.is_default is True


def test_mock_update_set_default_patch_returns_not_ok():
    """Test update() when the set-default patch returns response.ok=False"""
    endpoint = _make_mock_endpoint()
    profile = _make_profile(endpoint, name="my-profile", key="key1", is_default=False)

    mock_response = MagicMock()
    mock_response.ok = False

    with (
        patch.object(profile, "patch", return_value=mock_response),
        patch.object(profile, "_update_categories", return_value=False) as mock_cats,
        patch.object(profile, "_update_licenses", return_value=False) as mock_lics,
    ):
        ok = profile.update(isDefault=True)

    # patch returned ok=False, so ok should be False
    assert ok is False
    # is_default is set to True in the code regardless of response.ok (it's set after patch)
    assert profile.is_default is True
