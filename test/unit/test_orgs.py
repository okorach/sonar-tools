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

from collections.abc import Generator
import time
import json
import pytest

import utilities as tutil
from sonar import organizations as orgs, exceptions
import sonar.util.constants as c

MY_ORG = "okorach"


SUPPORTED_EDITIONS = c.SC


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        with pytest.raises(exceptions.UnsupportedOperation) as e:
            _ = orgs.Organization.get_object(endpoint=tutil.SQ, key=MY_ORG)
            assert str(e.value) == orgs._NOT_SUPPORTED
        return
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=MY_ORG)
    assert org.key == MY_ORG
    assert str(org) == f"organization '{MY_ORG}'"
    assert org.url() == f"{tutil.SQ.external_url}/organizations/{MY_ORG}"
    org2 = orgs.Organization.get_object(endpoint=tutil.SQ, key=MY_ORG)
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
    assert orgs.exists(endpoint=tutil.SQ, org_key=MY_ORG)
    assert not orgs.exists(endpoint=tutil.SQ, org_key=tutil.NON_EXISTING_KEY)


def test_attributes() -> None:
    """Test attributes"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=MY_ORG)
    assert org.search_params() == {"organization": MY_ORG}
    assert org.new_code_period() == ("PREVIOUS_VERSION", None)
    assert org.subscription() != "UNKNOWN"
    assert len(org.alm()) > 3
    assert str(org) == f"organization '{MY_ORG}'"


def test_export() -> None:
    """Test attributes"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org = orgs.Organization.get_object(endpoint=tutil.SQ, key=MY_ORG)
    exp = org.export()
    assert exp["key"] == MY_ORG
    assert exp["name"] == org.name
    assert "newCodePeriod" in exp
    assert "subscription" in exp
    assert "alm" in exp


def test_get_list() -> None:
    """Test Org get_list"""
    if tutil.SQ.edition() not in SUPPORTED_EDITIONS:
        pytest.skip("Organizations not supported")
    org_list = orgs.Organization.search(tutil.SQ)
    assert len(org_list) >= 2
    assert MY_ORG in org_list
    org = org_list[MY_ORG]
    assert isinstance(org, orgs.Organization)
    assert org.key == MY_ORG

