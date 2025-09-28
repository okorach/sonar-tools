#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2024-2025 Olivier Korach
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

""" users tests """

from collections.abc import Generator
import pytest

import utilities as tutil
from sonar import exceptions
from sonar import webhooks as wh
from sonar.audit import rules as audit_rules

WEBHOOK = "Jenkins"


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    webhook = wh.get_object(endpoint=tutil.SQ, name=WEBHOOK)
    assert webhook.name == WEBHOOK
    assert str(webhook) == f"webhook '{WEBHOOK}'"
    assert webhook.url() == f"{tutil.SQ.external_url}/admin/webhooks"
    webhook2 = wh.get_object(endpoint=tutil.SQ, name=WEBHOOK)
    assert webhook2 is webhook
    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = wh.get_object(endpoint=tutil.SQ, name=tutil.NON_EXISTING_KEY)
    assert str(e.value).endswith(f"Webhook '{tutil.NON_EXISTING_KEY}' not found")


def test_audit() -> None:
    """test_audit"""
    webhook = wh.get_object(endpoint=tutil.SQ, name=WEBHOOK)
    pbs = webhook.audit()
    assert len(pbs) == 1
    assert pbs[0].rule_id == audit_rules.RuleId.FAILED_WEBHOOK
    pbs = wh.audit(tutil.SQ, {"audit.webhooks": True})
    assert len(pbs) == 1
    assert pbs[0].rule_id == audit_rules.RuleId.FAILED_WEBHOOK


def test_update() -> None:
    """test_update"""
    webhook = wh.get_object(endpoint=tutil.SQ, name=WEBHOOK)
    old_url = webhook.webhook_url
    new_url = "http://my.jenkins.server/sonar-webhook/"
    webhook.update(url=new_url)
    webhook = wh.get_object(endpoint=tutil.SQ, name=WEBHOOK)
    assert webhook.webhook_url == new_url
    webhook.update(url_target=old_url)
    webhook = wh.get_object(endpoint=tutil.SQ, name=WEBHOOK)
    assert webhook.webhook_url == old_url


def test_export() -> None:
    """test_export"""
    exp = wh.export(tutil.SQ)
    assert len(exp) == 1
    first = list(exp.key())[0]
    assert exp[first]["url"].startswith("https://")
