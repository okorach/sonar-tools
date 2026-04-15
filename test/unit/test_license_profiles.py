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

import os
import pytest

import utilities as tutil
from sonar import license_profiles as lp, exceptions
from sonar.util import constants as c

TEMP_LP_NAME = f"TEMP-license-profile-{os.getpid()}"
_UNSUPPORTED_MSG = "License profiles require SonarQube Server 2025.4+ Enterprise or Data Center Edition, or SonarQube Cloud with SCA enabled"


def _sca_available() -> bool:
    """Checks if SCA is available on the test platform"""
    return lp.sca_enabled(tutil.SQ)


def _skip_if_unsupported() -> None:
    """Skips the test if the platform does not support license profiles"""
    if not _sca_available():
        pytest.skip(_UNSUPPORTED_MSG)


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
