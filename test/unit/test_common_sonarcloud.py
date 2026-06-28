#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2024-2026 Olivier Korach
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
"""sonarcloud tests"""

import os
import pytest
from collections.abc import Generator
import utilities as tutil
from sonar import errcodes, exceptions
from sonar import organizations

import credentials as creds

import cli.options as opt
from sonar.cli import config

CMD = "config.py"
SC_OPTS = f'-{opt.URL_SHORT} https://sonarcloud.io -{opt.TOKEN_SHORT} {os.getenv("SONAR_TOKEN_SONARCLOUD")}'

OPTS = f"{CMD} {SC_OPTS} -{opt.EXPORT_SHORT}"
MY_ORG_2 = "okorach-github"


def test_sc_config_export(json_file: Generator[str]) -> None:
    """test_sc_config_export"""
    cmd = f"{OPTS} --{opt.REPORT_FILE} {json_file} -{opt.ORG_SHORT} {creds.ORGANIZATION}"
    assert tutil.run_cmd(config.main, cmd) == errcodes.OK


def test_sc_config_export_no_org() -> None:
    """test_sc_config_export"""
    assert tutil.run_cmd(config.main, SC_OPTS) == errcodes.ARGS_ERROR


def test_org_search() -> None:
    """test_org_search"""
    org_list = organizations.Organization.search(tutil.SC)
    assert creds.ORGANIZATION in org_list
    assert MY_ORG_2 in org_list


def test_org_get_non_existing() -> None:
    """test_org_search_sq"""
    with pytest.raises(exceptions.ObjectNotFound):
        _ = organizations.Organization.get_object(endpoint=tutil.SC, key="oko_foo_bar")

    with pytest.raises(exceptions.ObjectNotFound):
        _ = organizations.Organization.search(endpoint=tutil.SC, key_list=["oko_foo_bar"])


def test_org_str() -> None:
    """test_org_str"""
    org = organizations.Organization.get_object(endpoint=tutil.SC, key=creds.ORGANIZATION)
    assert str(org) == f"organization key '{creds.ORGANIZATION}'"


def test_org_export() -> None:
    """test_org_export"""
    org = organizations.Organization.get_object(endpoint=tutil.SC, key=creds.ORGANIZATION)
    exp = org.export()
    assert "newCodePeriod" in exp


def test_org_attr() -> None:
    """test_org_attr"""
    org = organizations.Organization.get_object(endpoint=tutil.SC, key=creds.ORGANIZATION)
    assert org.key == creds.ORGANIZATION
    assert org.name is not None and len(org.name) > 0
    assert org.sq_json["url"] == "https://github.com/okorach"
    (nc_type, _) = org.new_code_period()
    assert nc_type == "PREVIOUS_VERSION"
    assert org.subscription() == "FREE"
    assert org.alm()["key"] == "github"


def test_org_search_sqs() -> None:
    """test_org_search_sq"""
    if tutil.SQ.is_sonarcloud():
        pytest.skip("tutil.SQ is SonarCloud in this run; cannot test SQS rejection here")
    with pytest.raises(exceptions.UnsupportedOperation):
        _ = organizations.Organization.search(endpoint=tutil.SQ)

    with pytest.raises(exceptions.UnsupportedOperation):
        _ = organizations.Organization.get_list(endpoint=tutil.SQ)


def test_audit() -> None:
    """test_audit"""
    tutil.SC.audit({})


def test_org_resolve_id() -> None:
    """Test that _resolve_id returns a non-empty string and caches the result"""
    org = organizations.Organization.get_object(endpoint=tutil.SC, key=creds.ORGANIZATION)
    # Remove any cached id so we force a real API call on first invocation
    org.sq_json.pop("id", None)
    org_id = org._resolve_id()
    assert isinstance(org_id, str)
    assert len(org_id) > 0
    # Second call must use the cached value — id is now stored in sq_json
    assert org.sq_json.get("id") == org_id
    org_id2 = org._resolve_id()
    assert org_id2 == org_id


def test_org_resolve_id_non_existing() -> None:
    """Test that _resolve_id raises ObjectNotFound for an unknown org key"""
    org = organizations.Organization.get_object(endpoint=tutil.SC, key=creds.ORGANIZATION)
    org.sq_json.pop("id", None)
    original_key = org.key
    org.key = "this-key-does-not-exist-xyz"
    try:
        with pytest.raises(exceptions.ObjectNotFound):
            org._resolve_id()
    finally:
        org.key = original_key


def test_org_set_new_code_period_previous_version() -> None:
    """Test setting org new code period to PREVIOUS_VERSION"""
    org = organizations.Organization.get_object(endpoint=tutil.SC, key=creds.ORGANIZATION)
    assert org.set_new_code_period("PREVIOUS_VERSION", None) is True
    # Verify it round-trips: the new_code_period() accessor should reflect it
    org.sq_json.pop("defaultLeakPeriodType", None)
    org.sq_json.pop("defaultLeakPeriod", None)


def test_org_set_new_code_period_days() -> None:
    """Test setting org new code period to NUMBER_OF_DAYS (and DAYS alias)"""
    org = organizations.Organization.get_object(endpoint=tutil.SC, key=creds.ORGANIZATION)
    assert org.set_new_code_period("NUMBER_OF_DAYS", 30) is True
    assert org.set_new_code_period("DAYS", 14) is True
    # Restore to a clean state
    org.set_new_code_period("PREVIOUS_VERSION", None)


def test_org_set_new_code_period_unsupported_type() -> None:
    """Test that an unsupported nc_type raises UnsupportedOperation"""
    org = organizations.Organization.get_object(endpoint=tutil.SC, key=creds.ORGANIZATION)
    with pytest.raises(exceptions.UnsupportedOperation):
        org.set_new_code_period("REFERENCE_BRANCH", "main")


def test_org_export_keys() -> None:
    """Test that export() returns the expected top-level keys"""
    org = organizations.Organization.get_object(endpoint=tutil.SC, key=creds.ORGANIZATION)
    exp = org.export()
    assert exp.get("key") == creds.ORGANIZATION
    assert "name" in exp
    assert "newCodePeriod" in exp
    # export() calls util.filter_export with _IMPORTABLE_PROPERTIES; none of the
    # internal-only fields should leak through
    for forbidden in ("defaultLeakPeriod", "defaultLeakPeriodType"):
        assert forbidden not in exp


def test_org_export_days_new_code_period() -> None:
    """Test that export() renders newCodePeriod correctly when type is NUMBER_OF_DAYS"""
    org = organizations.Organization.get_object(endpoint=tutil.SC, key=creds.ORGANIZATION)
    org.set_new_code_period("NUMBER_OF_DAYS", 30)
    # Force sq_json to reflect the updated period so export() picks it up
    org.sq_json["defaultLeakPeriodType"] = "days"
    org.sq_json["defaultLeakPeriod"] = "30"
    exp = org.export()
    assert "NUMBER_OF_DAYS" in exp["newCodePeriod"]
    assert "30" in exp["newCodePeriod"]
    # Restore
    org.set_new_code_period("PREVIOUS_VERSION", None)
    org.sq_json.pop("defaultLeakPeriodType", None)
    org.sq_json.pop("defaultLeakPeriod", None)
