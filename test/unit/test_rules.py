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
import pytest
import utilities as tutil
from cli import rules_cli
import cli.options as opt
from sonar import rules, exceptions, errcodes as e
from sonar.util import constants as c, issue_defs as idefs
import sonar.utilities as sutil

CMD = "rules_cli.py"
OPTS = f"{CMD} {tutil.SQS_OPTS}"


def test_rules(csv_file: Generator[str]) -> None:
    """test_rules"""
    assert tutil.run_cmd(rules_cli.main, f"{OPTS} --{opt.REPORT_FILE} {csv_file}") == e.OK
    assert tutil.csv_cols_present(csv_file, "key", "language", "repo", "name", "ruleType")


def test_rules_json_format(json_file: Generator[str]) -> None:
    """test_rules_json_format"""
    assert tutil.run_cmd(rules_cli.main, f"{OPTS} --{opt.REPORT_FILE} {json_file}") == e.OK
    assert tutil.json_fields_present(json_file, "key", "lang", "repo", "name", "isTemplate")


def test_rules_filter_language(csv_file: Generator[str]) -> None:
    """Tests that you can export rules for a single or a few languages"""
    langs = ("py", "cs") if tutil.SQ.edition() == c.CE else ("py", "apex")
    cmd = f"{OPTS} --{opt.REPORT_FILE} {csv_file} --{opt.LANGUAGES} {','.join(langs)}"
    assert tutil.run_cmd(rules_cli.main, cmd) == e.OK
    assert tutil.csv_col_is_value(csv_file, "language", *langs)


def test_rules_misspelled_language_1(csv_file: Generator[str]) -> None:
    """Tests that you can export rules for a single or a few languages, misspelled"""
    cmd = f"{OPTS} --{opt.REPORT_FILE} {csv_file} --{opt.LANGUAGES} Python,TypeScript"
    assert tutil.run_cmd(rules_cli.main, cmd) == e.OK
    assert tutil.csv_col_is_value(csv_file, "language", "py", "ts")


def test_rules_misspelled_language_2(csv_file: Generator[str]) -> None:
    """test_rules_misspelled_language_2"""
    cmd = f'{OPTS} --{opt.REPORT_FILE} {csv_file} --{opt.LANGUAGES} "Python ,gosu,  aPex"'
    assert tutil.run_cmd(rules_cli.main, cmd) == e.NO_SUCH_KEY


def test_get_rule() -> None:
    """test_get_rule"""
    myrule = rules.Rule.get_object(endpoint=tutil.SQ, key="java:S127")
    assert str(myrule) == "rule key 'java:S127'"
    myrule = rules.Rule.load(endpoint=tutil.SQ, key="java:S127", data={})
    assert str(myrule) == "rule key 'java:S127'"


def test_set_tags() -> None:
    """test_set_tags"""
    my_rule = rules.Rule.get_object(endpoint=tutil.SQ, key="java:S127")
    assert my_rule.set_tags(tutil.TAGS)
    assert my_rule.tags == sorted(tutil.TAGS)
    assert my_rule.reset_tags()
    assert my_rule.tags is None


def test_set_desc() -> None:
    """test_set_tags"""
    my_rule = rules.Rule.get_object(endpoint=tutil.SQ, key="java:S127")
    assert my_rule.set_description("Blah blah")
    assert my_rule.custom_desc == "Blah blah"
    assert my_rule.reset_description()
    assert my_rule.custom_desc is None


def test_facets() -> None:
    """test_facets"""
    facets = rules.get_facet(endpoint=tutil.SQ, facet="languages")
    langs = ["py", "java", "cs", "js", "web", "php", "ruby", "go", "scala", "vbnet"]
    if tutil.SQ.edition() in (c.DE, c.EE, c.DCE):
        langs += ["c", "cpp", "objc", "swift", "abap"]
    if tutil.SQ.edition() in (c.EE, c.DCE):
        langs += ["plsql", "rpg", "cobol", "vb", "pli"]
    assert len(facets) >= len(langs)
    for lang in langs:
        assert lang in facets


def test_get_rule_cache() -> None:
    """test_get_rule_cache"""
    my_rule = rules.Rule.get_object(endpoint=tutil.SQ, key="java:S127")
    assert str(my_rule) == "rule key 'java:S127'"
    new_rule = rules.Rule.get_object(endpoint=tutil.SQ, key="java:S127")
    assert my_rule is new_rule


def test_export_not_full() -> None:
    """test_export_not_full"""
    rule_list = rules.export(endpoint=tutil.SQ, export_settings={"FULL_EXPORT": False})
    assert len(rule_list["extended"]) > 0
    rule_list = rules.export(endpoint=tutil.SQ, export_settings={"FULL_EXPORT": True})
    assert len(rule_list["extended"]) > 0


def test_get_nonexisting_rule() -> None:
    """test_get_nonexisting_rule"""
    try:
        _ = rules.Rule.get_object(endpoint=tutil.SQ, key="badlang:S127")
        assert False
    except exceptions.ObjectNotFound as e:
        assert e.key == "badlang:S127"


def test_export_all() -> None:
    """test_export_all"""
    rule_list = rules.export(endpoint=tutil.SQ, export_settings={"FULL_EXPORT": True})
    if tutil.SQ.version() < (10, 0, 0) and tutil.SQ.edition() == c.CE:
        assert len(rule_list.get("standard", {})) > 2800
    else:
        assert len(rule_list.get("standard", {})) > 3000


def test_new_taxo() -> None:
    """test_new_taxo"""
    my_rule = rules.Rule.get_object(endpoint=tutil.SQ, key="java:S127")
    if tutil.SQ.version() >= c.MQR_INTRO_VERSION:
        for qual, sev in my_rule.impacts().items():
            assert qual in idefs.MQR_QUALITIES
            assert sev in idefs.MQR_SEVERITIES
        attr = my_rule.clean_code_attribute()
        assert "attribute" in attr
        assert "attribute_category" in attr
    else:
        assert my_rule.severity in idefs.STD_SEVERITIES
        assert my_rule.type in idefs.STD_TYPES


def test_non_existing_qp() -> None:
    assert tutil.run_cmd(rules_cli.main, f"{OPTS} --{opt.QP} non-existing --{opt.LANGUAGES} java") == e.NO_SUCH_KEY


def test_non_existing_language() -> None:
    assert tutil.run_cmd(rules_cli.main, f"{OPTS} --{opt.LANGUAGES} assembly-lang") == e.NO_SUCH_KEY


def test_qp_non_existing_language() -> None:
    assert tutil.run_cmd(rules_cli.main, f'{OPTS} --{opt.QP} "Sonar way" --{opt.LANGUAGES} javac') == e.NO_SUCH_KEY


def test_qp_multiple_languages() -> None:
    assert tutil.run_cmd(rules_cli.main, f'{OPTS} --{opt.QP} "Sonar way" --{opt.LANGUAGES} java,c') == e.ARGS_ERROR


def test_os_error() -> None:
    assert tutil.run_cmd(rules_cli.main, f"{OPTS} --{opt.LANGUAGES} java,c -f /rules.csv") == e.OS_ERROR


def test_third_party() -> None:
    third_party_rules = rules.third_party(tutil.SQ)
    assert len(third_party_rules) > 0
    assert sum(1 for r in third_party_rules if r.key.startswith("creedengo")) > 0


def test_export_fields() -> None:
    """test_export_fields"""
    rule_list = rules.export(endpoint=tutil.SQ, export_settings={})
    assert "standard" not in rule_list
    assert len(rule_list["extended"]) > 0
    for r in rule_list["extended"]:
        assert any(key in r for key in ("description", "tags", "params"))
    assert len(rule_list["instantiated"]) > 0
    for r in rule_list["instantiated"]:
        assert all(key in r for key in ("language", "params", "severity", "impacts", "templateKey"))


def test_instantiate() -> None:
    """test_create_rule"""
    params = {
        "severity": "major",
        "impacts": {"security": "medium", "maintainability": "medium"},
        "name": "Thou shalt not be rude",
        "description": "Behave yourself in your code",
        "params": [{"key": "message", "value": "Hey don't be rude!"}, {"key": "regularExpression", "value": "(f-word|s-word)"}],
    }
    if tutil.SQ.is_sonarcloud():
        with pytest.raises(exceptions.UnsupportedOperation):
            rules.Rule.instantiate(endpoint=tutil.SQ, key="java:rudeness_is_bad", template_key="java:S124", data=params)
        return
    new_rule = rules.Rule.instantiate(endpoint=tutil.SQ, key="java:rudeness_is_bad", template_key="java:S124", data=params)
    print("GOTTEN RULE: ", str(new_rule))
    assert new_rule.key == "java:rudeness_is_bad"
    assert new_rule.name == "Thou shalt not be rude"
    assert new_rule.custom_desc == "Behave yourself in your code"
    assert new_rule.language == "java"
    if tutil.SQ.is_mqr_mode():
        assert new_rule.impacts == {"SECURITY": "MEDIUM", "MAINTAINABILITY": "MEDIUM"}
    else:
        assert new_rule.severity == "MAJOR"
        assert new_rule.type == "CODE_SMELL"
    new_rule.delete()
    rules.Rule.clear_cache()
    assert not rules.Rule.exists(endpoint=tutil.SQ, key="java:rudeness_is_bad")
