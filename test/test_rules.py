#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2024 Olivier Korach
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


"""
    sonar-rules tests
"""

import sys
from unittest.mock import patch
import utilities as testutil
from tools import rules_cli
from sonar import rules

CMD = "rules_cli.py"
CSV_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.CSV_FILE]
JSON_OPTS = [CMD] + testutil.STD_OPTS + ["-f", testutil.JSON_FILE]


def test_rules() -> None:
    """test_rules"""
    testutil.clean(testutil.CSV_FILE)
    with patch.object(sys, "argv", CSV_OPTS):
        try:
            rules_cli.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.CSV_FILE)
    testutil.clean(testutil.CSV_FILE)


def test_rules_json_format() -> None:
    """test_rules_json_format"""
    testutil.clean(testutil.JSON_FILE)
    with patch.object(sys, "argv", JSON_OPTS + ["--format", "json"]):
        try:
            rules_cli.main()
        except SystemExit as e:
            assert int(str(e)) == 0
    assert testutil.file_not_empty(testutil.JSON_FILE)
    testutil.clean(testutil.JSON_FILE)


def test_get_rule() -> None:
    """test_get_rule"""
    myrule = rules.get_object(endpoint=testutil.SONARQUBE, key="java:S127")
    assert str(myrule) == "rule key 'java:S127'"
    myrule = rules.Rule.load(endpoint=testutil.SONARQUBE, key="java:S127", data={})
    assert str(myrule) == "rule key 'java:S127'"


def test_get_nonexisting_rule() -> None:
    """test_get_nonexisting_rule"""
    myrule = rules.Rule.get_object(endpoint=testutil.SONARQUBE, key="badlang:S127")
    assert myrule is None


def test_export_all() -> None:
    """test_export_all"""
    rule_list = rules.export_all(endpoint=testutil.SONARQUBE, full=True)
    assert len(rule_list.get("standard", {})) > 3000
