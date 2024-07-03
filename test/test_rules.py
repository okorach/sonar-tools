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
import pytest
import utilities as util
from cli import rules_cli
import cli.options as opt
from sonar import rules, exceptions

CMD = "rules_cli.py"
CSV_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.OUTPUTFILE_SHORT}", util.CSV_FILE]
JSON_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.OUTPUTFILE_SHORT}", util.JSON_FILE]


def test_rules() -> None:
    """test_rules"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS):
            rules_cli.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_rules_json_format() -> None:
    """test_rules_json_format"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + [f"--{opt.FORMAT}", "json"]):
            rules_cli.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_rules_filter_language() -> None:
    """Tests that you can export rules for a single or a few languages"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.LANGUAGES}", "py,jcl"]):
            rules_cli.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.CSV_FILE)
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in fh:
            (_, lang, _) = line.split(",", maxsplit=2)
            assert lang in ("py", "jcl")
    util.clean(util.CSV_FILE)


def test_rules_misspelled_language_1() -> None:
    """Tests that you can export rules for a single or a few languages, misspelled"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.LANGUAGES}", "Python,TypeScript"]):
            rules_cli.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.CSV_FILE)
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in fh:
            (_, lang, _) = line.split(",", maxsplit=2)
            assert lang in ("py", "ts")
    util.clean(util.CSV_FILE)


def test_rules_misspelled_language_2() -> None:
    """Tests that you can export rules for a single or a few languages, misspelled and not fixed"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.LANGUAGES}", "Python,gosu , aPex"]):
            rules_cli.main()
    assert int(str(e.value)) == 0
    assert util.file_not_empty(util.CSV_FILE)
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        for line in fh:
            (_, lang, _) = line.split(",", maxsplit=2)
            assert lang in ("py", "apex")
    util.clean(util.CSV_FILE)


def test_get_rule() -> None:
    """test_get_rule"""
    myrule = rules.get_object(endpoint=util.SQ, key="java:S127")
    assert str(myrule) == "rule key 'java:S127'"
    myrule = rules.Rule.load(endpoint=util.SQ, key="java:S127", data={})
    assert str(myrule) == "rule key 'java:S127'"


def test_get_nonexisting_rule() -> None:
    """test_get_nonexisting_rule"""
    try:
        _ = rules.Rule.get_object(endpoint=util.SQ, key="badlang:S127")
        assert False
    except exceptions.ObjectNotFound as e:
        assert e.key == "badlang:S127"


def test_export_all() -> None:
    """test_export_all"""
    rule_list = rules.export_all(endpoint=util.SQ, full=True)
    assert len(rule_list.get("standard", {})) > 3000
