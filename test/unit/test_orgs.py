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
    assert str(org) == f"organization '{creds.ORGANIZATION}'"
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
    assert str(org) == f"organization '{creds.ORGANIZATION}'"


def test_export() -> None:
    """Test attributes"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=creds.ORGANIZATION)
    exp = org.export()
    assert exp["key"] == creds.ORGANIZATION
    assert exp["name"] == org.name
    assert "newCodePeriod" in exp
    assert "subscription" in exp
    assert "alm" in exp


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
