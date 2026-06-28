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

"""portfolio tests"""

import pytest

import utilities as tutil
from sonar import organizations as orgs, exceptions
import sonar.util.constants as c
import credentials as creds


SUPPORTED_EDITIONS = c.SC


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        with pytest.raises(exceptions.UnsupportedOperation) as e:
            _ = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
        return
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    assert org.key == creds.ORGANIZATION
    assert str(org) == f"organization key '{creds.ORGANIZATION}'"
    assert org.url() == f"{tutil.SQ.external_url}/organizations/{creds.ORGANIZATION}"
    org2 = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    assert org2 is org


def test_get_object_non_existing() -> None:
    """Test exception raised when providing non existing organization key"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = orgs.Organization.get_object(endpoint=tutil.SQ, key=tutil.NON_EXISTING_KEY)
    assert str(e.value).endswith(f"Organization '{tutil.NON_EXISTING_KEY}' not found")


def test_exists() -> None:
    """Test exist"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    assert orgs.exists(endpoint=tutil.SQ, org_key=creds.ORGANIZATION)
    assert not orgs.exists(endpoint=tutil.SQ, org_key=tutil.NON_EXISTING_KEY)


def test_attributes() -> None:
    """Test attributes"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    assert org.search_params() == {"organization": creds.ORGANIZATION}
    assert org.new_code_period() == ("PREVIOUS_VERSION", None)
    assert org.subscription() != "UNKNOWN"
    assert len(org.alm()) > 3
    assert str(org) == f"organization key '{creds.ORGANIZATION}'"


def test_subscription() -> None:
    """Test that subscription() returns a known non-UNKNOWN value"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    sub = org.subscription()
    assert isinstance(sub, str)
    assert sub != "UNKNOWN"


def test_alm() -> None:
    """Test that alm() returns a non-empty dict containing at least a 'key' field"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    alm = org.alm()
    assert isinstance(alm, dict)
    assert len(alm) > 0
    assert "key" in alm


def test_export() -> None:
    """Test the export of an organization"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    exp = org.export()
    # Importable properties are exported as-is
    assert exp["key"] == creds.ORGANIZATION
    assert exp["name"] == org.name
    assert "newCodePeriod" in exp
    # Non-importable properties are prefixed with _ by filter_export(full=True)
    assert "_subscription" in exp
    assert "_alm" in exp
    # Internal leak/period fields must not appear at all
    assert "defaultLeakPeriod" not in exp
    assert "defaultLeakPeriodType" not in exp


def test_resolve_id() -> None:
    """Test that _resolve_id() returns a non-empty string and caches it in sq_json"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    org.sq_json.pop("id", None)
    org_id = org._resolve_id()
    assert isinstance(org_id, str) and len(org_id) > 0
    assert org.sq_json.get("id") == org_id
    # Second call must return the cached value
    assert org._resolve_id() == org_id


def test_resolve_id_non_existing() -> None:
    """Test that _resolve_id() raises ObjectNotFound for an unknown org key"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    org.sq_json.pop("id", None)
    original_key = org.key
    org.key = tutil.NON_EXISTING_KEY
    try:
        with pytest.raises(exceptions.ObjectNotFound):
            org._resolve_id()
    finally:
        org.key = original_key


def test_set_new_code_period_previous_version() -> None:
    """Test setting the org new code period to PREVIOUS_VERSION"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    assert org.set_new_code_period("PREVIOUS_VERSION", None) is True


def test_set_new_code_period_days() -> None:
    """Test setting the org new code period to NUMBER_OF_DAYS and its DAYS alias"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    assert org.set_new_code_period("NUMBER_OF_DAYS", 30) is True
    assert org.set_new_code_period("DAYS", 14) is True
    # Restore to PREVIOUS_VERSION
    org.set_new_code_period("PREVIOUS_VERSION", None)


def test_set_new_code_period_unsupported() -> None:
    """Test that an unsupported nc_type raises UnsupportedOperation"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    with pytest.raises(exceptions.UnsupportedOperation):
        org.set_new_code_period("REFERENCE_BRANCH", "main")


def test_search() -> None:
    """Test search"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org_list = orgs.Organization.search(tutil.SQ)
    assert len(org_list) >= 2
    assert creds.ORGANIZATION in org_list
    org = org_list[creds.ORGANIZATION]
    assert isinstance(org, orgs.Organization)
    assert org.key == creds.ORGANIZATION
