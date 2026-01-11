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

"""Project audit tests"""

import pytest

import utilities as tutil
from sonar import projects
from sonar.audit import rules


def test_audit_proj_good_key_pattern() -> None:
    """test_audit_cmd_line_settings"""
    if tutil.SQ.is_sonarcloud():
        map_patterns = {"": None, "okorach_.+": None}
    else:
        map_patterns = {"": "BANKING.+", ".+": "BANKING.+", "(BANK|INSU|demo:).+": "(BANKING|INSURANCE|demo:).+"}

    for pattern, key_list in map_patterns.items():
        if pattern == "":
            pattern = None
        settings = {"audit.projects": True, "audit.projects.keyPattern": pattern}
        pbs = projects.audit(tutil.SQ, settings, key_list=key_list)
        assert all(pb.rule_id != rules.RuleId.PROJ_NON_COMPLIANT_KEY_PATTERN for pb in pbs)


def test_audit_proj_bad_key_pattern() -> None:
    """test_audit_proj_bad_key_pattern"""
    if tutil.SQ.is_sonarcloud():
        pattern = "okorach_BANKING.+"
        key_list = ".+"
    else:
        pattern = "BANKING.+"
        key_list = "(BANK|INSU|demo:).+"

    settings = {"audit.projects": True, "audit.projects.keyPattern": pattern}
    pbs = projects.audit(tutil.SQ, settings, key_list=key_list)
    assert any(pb.rule_id == rules.RuleId.PROJ_NON_COMPLIANT_KEY_PATTERN for pb in pbs)


def test_audit_platform_logs() -> None:
    """test_audit_platform_logs"""
    if tutil.SQ.is_sonarcloud():
        pytest.skip("Logs audit not available with SonarQube Cloud, skipping logs audit...")
    assert len(tutil.SQ.audit_logs({"audit.logs": False})) == 0
    if tutil.SQ.is_sonarcloud():
        assert len(tutil.SQ.audit_logs({"audit.logs": True})) == 0

    pbs = tutil.SQ.audit_logs({"audit.logs": True})
    assert any(pb.rule_id == rules.RuleId.WARNING_IN_LOGS for pb in pbs)
