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

from collections.abc import Generator
import csv
from unittest.mock import patch
import utilities as util
from cli import rules_cli
import cli.options as opt
from sonar import rules, exceptions, errcodes
import sonar.util.constants as c

CMD = "rules_cli.py"
OPTS = f"{CMD} {util.SQS_OPTS}"


def test_rules(csv_file: Generator[str]) -> None:
    """test_rules"""
    util.run_success_cmd(rules_cli.main, f"{OPTS} --{opt.REPORT_FILE} {csv_file}")


def test_rules_json_format(json_file: Generator[str]) -> None:
    """test_rules_json_format"""
    util.run_success_cmd(rules_cli.main, f"{OPTS} --{opt.REPORT_FILE} {json_file}")


def test_rules_filter_language(csv_file: Generator[str]) -> None:
    """Tests that you can export rules for a single or a few languages"""
    langs = ("py", "cs") if util.SQ.edition() == c.CE else ("py", "apex")
    cmd = f"{OPTS} --{opt.REPORT_FILE} {csv_file} --{opt.LANGUAGES} {','.join(langs)}"
    util.run_success_cmd(rules_cli.main, cmd)
    with open(file=csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        (col,) = util.get_cols(line := next(csvreader), "language")
        assert line[0].startswith("# ")
        line[0] = line[0][2:]
        assert line == (rules.CSV_EXPORT_FIELDS if util.SQ.version() >= c.MQR_INTRO_VERSION else rules.LEGACY_CSV_EXPORT_FIELDS)
        for line in csvreader:
            assert line[col] in langs


def test_rules_misspelled_language_1(csv_file: Generator[str]) -> None:
    """Tests that you can export rules for a single or a few languages, misspelled"""
    cmd = f"{OPTS} --{opt.REPORT_FILE} {csv_file} --{opt.LANGUAGES} Python,TypeScript"
    util.run_success_cmd(rules_cli.main, cmd)
    with open(csv_file, mode="r", encoding="utf-8") as fh:
        csvreader = csv.reader(fh)
        (col,) = util.get_cols(line := next(csvreader), "language")
        assert line[0].startswith("# ")
        line[0] = line[0][2:]
        if util.SQ.version() >= c.MQR_INTRO_VERSION:
            assert line == rules.CSV_EXPORT_FIELDS
        else:
            assert line == rules.LEGACY_CSV_EXPORT_FIELDS
        for line in csvreader:
            assert line[col] in ("py", "ts")


def test_rules_misspelled_language_2(csv_file: Generator[str]) -> None:
    """test_rules_misspelled_language_2"""
    cmd = f'{OPTS} --{opt.REPORT_FILE} {csv_file} --{opt.LANGUAGES} "Python ,gosu,  aPex"'
    util.run_failed_cmd(rules_cli.main, cmd, errcodes.NO_SUCH_KEY)


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
    if util.SQ.edition() in (c.DE, c.EE, c.DCE):
        langs += ["c", "cpp", "objc", "swift", "abap"]
    if util.SQ.edition() in (c.EE, c.DCE):
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
    if util.SQ.version() < (10, 0, 0) and util.SQ.edition() == c.CE:
        assert len(rule_list.get("standard", {})) > 2800
    else:
        assert len(rule_list.get("standard", {})) > 3000


def test_new_taxo() -> None:
    """test_new_taxo"""
    my_rule = rules.get_object(endpoint=util.SQ, key="java:S127")
    if util.SQ.version() >= c.MQR_INTRO_VERSION:
        for qual, sev in my_rule.impacts().items():
            assert qual in rules.QUALITIES
            assert sev in rules.SEVERITIES
        attr = my_rule.clean_code_attribute()
        assert "attribute" in attr
        assert "attribute_category" in attr
    else:
        assert my_rule.severity in rules.LEGACY_SEVERITIES
        assert my_rule.type in rules.LEGACY_TYPES


def test_non_existing_qp() -> None:
    util.run_failed_cmd(rules_cli.main, f"{OPTS} --{opt.QP} non-existing --{opt.LANGUAGES} java", errcodes.NO_SUCH_KEY)


def test_non_existing_language() -> None:
    util.run_failed_cmd(rules_cli.main, f"{OPTS} --{opt.LANGUAGES} assembly-lang", errcodes.NO_SUCH_KEY)


def test_qp_non_existing_language() -> None:
    util.run_failed_cmd(rules_cli.main, f'{OPTS} --{opt.QP} "Sonar way" --{opt.LANGUAGES} javac', errcodes.NO_SUCH_KEY)


def test_qp_multiple_languages() -> None:
    util.run_failed_cmd(rules_cli.main, f'{OPTS} --{opt.QP} "Sonar way" --{opt.LANGUAGES} java,c', errcodes.ARGS_ERROR)


def test_os_error() -> None:
    util.run_failed_cmd(rules_cli.main, f"{OPTS} --{opt.LANGUAGES} java,c -f /rules.csv", errcodes.OS_ERROR)


def test_third_party() -> None:
    third_party_rules = rules.third_party(util.SQ)
    assert len(third_party_rules) > 0
    assert sum(1 for r in third_party_rules if r.key.startswith("creedengo")) > 0
