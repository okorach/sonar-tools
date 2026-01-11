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

"""Webhooks tests"""

import pytest

import utilities as tutil
from sonar import exceptions
from sonar import webhooks as wh
from sonar.audit import rules as audit_rules

WEBHOOK = "Jenkins"


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    webhook = wh.WebHook.get_object(tutil.SQ, WEBHOOK)
    assert webhook.name == WEBHOOK
    assert str(webhook) == f"webhook '{WEBHOOK}'"
    assert webhook.url() == f"{tutil.SQ.external_url}/admin/webhooks"
    webhook2 = wh.WebHook.get_object(endpoint=tutil.SQ, name=WEBHOOK)
    assert webhook2 is webhook


def test_get_object_not_found() -> None:
    """Test get_object_not_found"""
    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = wh.WebHook.get_object(endpoint=tutil.SQ, name=tutil.NON_EXISTING_KEY)
    assert str(e.value).endswith(f"Webhook '{tutil.NON_EXISTING_KEY}' of project 'None' not found")
    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = wh.WebHook.get_object(endpoint=tutil.SQ, name=tutil.NON_EXISTING_KEY, project=tutil.LIVE_PROJECT)
    assert str(e.value).endswith(f"Webhook '{tutil.NON_EXISTING_KEY}' of project '{tutil.LIVE_PROJECT}' not found")
    with pytest.raises(exceptions.ObjectNotFound) as e:
        _ = wh.WebHook.get_object(endpoint=tutil.SQ, name=WEBHOOK, project=tutil.LIVE_PROJECT)
    assert str(e.value).endswith(f"Webhook '{WEBHOOK}' of project '{tutil.LIVE_PROJECT}' not found")


def test_audit() -> None:
    """test_audit"""
    webhook = wh.WebHook.get_object(tutil.SQ, WEBHOOK)
    pbs = webhook.audit()
    assert len(pbs) == 1
    assert pbs[0].rule_id == audit_rules.RuleId.FAILED_WEBHOOK
    pbs = wh.audit(tutil.SQ)
    assert len(pbs) == 1
    assert pbs[0].rule_id == audit_rules.RuleId.FAILED_WEBHOOK


def test_update() -> None:
    """test_update"""
    webhook = wh.WebHook.get_object(tutil.SQ, WEBHOOK)
    old_url = webhook.webhook_url
    new_url = "https://my.jenkins.server/sonar-webhook/"
    webhook.update(url=new_url)
    webhook = wh.WebHook.get_object(tutil.SQ, WEBHOOK)
    assert webhook.webhook_url == new_url
    webhook.update(url_target=old_url)
    webhook = wh.WebHook.get_object(tutil.SQ, WEBHOOK)
    assert webhook.webhook_url == old_url


def test_export() -> None:
    """test_export"""
    exp = wh.export(tutil.SQ)
    assert len(exp) == 1
    first = list(exp.keys())[0]
    assert exp[first]["url"].startswith("https://")


def test_create_delete() -> None:
    """test_create_delete"""
    if tutil.SQ.version() >= (10, 0, 0):
        with pytest.raises(exceptions.SonarException):
            # Secret too short
            wh.WebHook.create(tutil.SQ, tutil.TEMP_KEY, "http://google.com", "Shhht", tutil.PROJECT_1)
    hook = wh.WebHook.create(tutil.SQ, tutil.TEMP_KEY, "http://google.com", "Shhht012345678910", tutil.PROJECT_1)
    assert hook.name == tutil.TEMP_KEY
    assert hook.webhook_url == "http://google.com"
    assert hook.secret == "Shhht012345678910"
    assert hook.project == tutil.PROJECT_1

    hook.refresh()
    hook.delete()
    if tutil.SQ.version() >= (10, 0, 0):
        with pytest.raises(exceptions.ObjectNotFound):
            hook.refresh()
