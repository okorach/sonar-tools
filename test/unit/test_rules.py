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


"""
    sonar-rules tests
"""

import sys
import csv
from unittest.mock import patch
import pytest
import utilities as util
from cli import rules_cli
import cli.options as opt
from sonar import rules, exceptions, errcodes

CMD = "rules_cli.py"
CSV_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", util.CSV_FILE]
JSON_OPTS = [CMD] + util.STD_OPTS + [f"-{opt.REPORT_FILE_SHORT}", util.JSON_FILE]

LANGUAGE_COL = 1


def test_rules() -> None:
    """test_rules"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS):
            rules_cli.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    util.clean(util.CSV_FILE)


def test_rules_json_format() -> None:
    """test_rules_json_format"""
    util.clean(util.JSON_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", JSON_OPTS + [f"--{opt.FORMAT}", "json"]):
            rules_cli.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.JSON_FILE)
    util.clean(util.JSON_FILE)


def test_rules_filter_language() -> None:
    """Tests that you can export rules for a single or a few languages"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.LANGUAGES}", "py,jcl"]):
            rules_cli.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        line = next(csvreader)
        assert line[0].startswith("# ")
        line[0] = line[0][2:]
        if util.SQ.version() >= (10, 2, 0):
            assert line == rules.CSV_EXPORT_FIELDS
        else:
            assert line == rules.LEGACY_CSV_EXPORT_FIELDS
        for line in csvreader:
            assert line[LANGUAGE_COL] in ("py", "jcl")
    util.clean(util.CSV_FILE)


def test_rules_misspelled_language_1() -> None:
    """Tests that you can export rules for a single or a few languages, misspelled"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.LANGUAGES}", "Python,TypeScript"]):
            rules_cli.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        line = next(csvreader)
        assert line[0].startswith("# ")
        line[0] = line[0][2:]
        if util.SQ.version() >= (10, 2, 0):
            assert line == rules.CSV_EXPORT_FIELDS
        else:
            assert line == rules.LEGACY_CSV_EXPORT_FIELDS
        for line in csvreader:
            assert line[LANGUAGE_COL] in ("py", "ts")
    util.clean(util.CSV_FILE)


def test_rules_misspelled_language_2() -> None:
    """Tests that you can export rules for a single or a few languages, misspelled and not fixed"""
    util.clean(util.CSV_FILE)
    with pytest.raises(SystemExit) as e:
        with patch.object(sys, "argv", CSV_OPTS + [f"--{opt.LANGUAGES}", "Python,gosu , aPex"]):
            rules_cli.main()
    assert int(str(e.value)) == errcodes.OK
    assert util.file_not_empty(util.CSV_FILE)
    with open(file=util.CSV_FILE, mode="r", encoding="utf-8") as fh:
        fh.readline()  # Skip header
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


def test_set_tags() -> None:
    """test_set_tags"""
    my_rule = rules.get_object(endpoint=util.SQ, key="java:S127")
    assert my_rule.set_tags(util.TAGS)
    assert my_rule.tags == sorted(util.TAGS)
    assert my_rule.reset_tags()
    assert my_rule.tags is None


def test_set_desc() -> None:
    """test_set_tags"""
    my_rule = rules.get_object(endpoint=util.SQ, key="java:S127")
    assert my_rule.set_description("Blah blah")
    assert my_rule.custom_desc == "Blah blah"
    assert my_rule.reset_description()
    assert my_rule.custom_desc is None


def test_facets() -> None:
    """test_facets"""
    facets = rules.get_facet(endpoint=util.SQ, facet="languages")
    langs = ["py", "java", "cs", "js", "web", "php", "ruby", "go", "scala", "vbnet"]
    if util.SQ.edition() in ("developer", "enterprise", "datacenter"):
        langs += ["c", "cpp", "objc", "swift", "abap"]
    if util.SQ.edition() in ("enterprise", "datacenter"):
        langs += ["plsql", "rpg", "cobol", "vb", "pli"]
    assert len(facets) >= len(langs)
    for lang in langs:
        assert lang in facets


def test_get_rule_cache() -> None:
    """test_get_rule_cache"""
    my_rule = rules.get_object(endpoint=util.SQ, key="java:S127")
    assert str(my_rule) == "rule key 'java:S127'"
    new_rule = rules.Rule.get_object(endpoint=util.SQ, key="java:S127")
    assert my_rule is new_rule


def test_export_not_full() -> None:
    """test_export_not_full"""
    rule_list = rules.export(endpoint=util.SQ, export_settings={"FULL_EXPORT": False})
    assert len(rule_list["extended"]) > 0
    rule_list = rules.export(endpoint=util.SQ, export_settings={"FULL_EXPORT": True})
    assert len(rule_list["extended"]) > 0


def test_get_nonexisting_rule() -> None:
    """test_get_nonexisting_rule"""
    try:
        _ = rules.Rule.get_object(endpoint=util.SQ, key="badlang:S127")
        assert False
    except exceptions.ObjectNotFound as e:
        assert e.key == "badlang:S127"


def test_export_all() -> None:
    """test_export_all"""
    rule_list = rules.export(endpoint=util.SQ, export_settings={"FULL_EXPORT": True})
    if util.SQ.version() < (10, 0, 0) and util.SQ.edition() == "community":
        assert len(rule_list.get("standard", {})) > 2800
    else:
        assert len(rule_list.get("standard", {})) > 3000


def test_new_taxo() -> None:
    """test_new_taxo"""
    my_rule = rules.get_object(endpoint=util.SQ, key="java:S127")
    if util.SQ.version() >= (10, 2, 0):
        for qual, sev in my_rule.impacts().items():
            assert qual in rules.QUALITIES
            assert sev in rules.SEVERITIES
        attr = my_rule.clean_code_attribute()
        assert "attribute" in attr
        assert "attribute_category" in attr
    else:
        assert my_rule.severity in rules.LEGACY_SEVERITIES
        assert my_rule.type in rules.LEGACY_TYPES
