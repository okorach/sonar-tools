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

"""Project audit tests"""

import utilities as tutil
from sonar import projects
from sonar.audit import rules


def test_audit_proj_key_pattern() -> None:
    """test_audit_cmd_line_settings"""
    settings = {"audit.projects": True, "audit.projects.keyPattern": None}
    pbs = projects.audit(tutil.SQ, settings, key_list="BANKING.*")
    assert all(pb.rule_id != rules.RuleId.PROJ_NON_COMPLIANT_KEY_PATTERN for pb in pbs)

    settings = {"audit.projects": True, "audit.projects.keyPattern": ".+"}
    pbs = projects.audit(tutil.SQ, settings, key_list="BANKING.*")
    assert all(pb.rule_id != rules.RuleId.PROJ_NON_COMPLIANT_KEY_PATTERN for pb in pbs)

    settings = {"audit.projects": True, "audit.projects.keyPattern": "BANKING.+"}
    pbs = projects.audit(tutil.SQ, settings, key_list="(BANKING|INSURANCE).+")
    assert any(pb.rule_id == rules.RuleId.PROJ_NON_COMPLIANT_KEY_PATTERN for pb in pbs)

    settings = {"audit.projects": True, "audit.projects.keyPattern": "(BANK|INSU|demo:).+"}
    pbs = projects.audit(tutil.SQ, settings, key_list="(BANKING|INSURANCE|demo:).+")
    assert all(pb.rule_id != rules.RuleId.PROJ_NON_COMPLIANT_KEY_PATTERN for pb in pbs)
