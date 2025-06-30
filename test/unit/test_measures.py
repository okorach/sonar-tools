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

""" sonar-measures-export tests """

import csv
from collections.abc import Generator
from unittest.mock import patch

import utilities as util
from sonar import errcodes as e, utilities
import sonar.util.constants as c

from cli import measures_export
import cli.options as opt

CMD = "sonar-measures-export.py"
CMD = f"{CMD} {util.SQS_OPTS}"
_RATING_LETTER = r"^[A-E]?$"
_RATING_NUMBER = r"^[1-5]?$"


def test_measures_export(csv_file: Generator[str]) -> None:
    """test_measures_export"""
    assert util.run_cmd(measures_export.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --withTags") == e.OK
    assert util.csv_col_sorted(csv_file, "key")
    assert util.csv_col_match(csv_file, "reliability_rating", _RATING_LETTER)
    assert util.csv_col_match(csv_file, "security_rating", _RATING_LETTER)
    assert util.csv_col_float_pct(csv_file, "duplicated_lines_density", True)
    assert util.csv_col_float_pct(csv_file, "sqale_debt_ratio", True)
    assert not util.csv_cols_present(csv_file, "statements", "ncloc_language_distribution")
    col_list = ("false_positive_issues",)
    if util.SQ.version() >= c.MQR_INTRO_VERSION:
        col_list += ("accepted_issues", "prioritized_rule_issues")
    assert util.csv_cols_present(csv_file, *col_list)
    for col in col_list:
        assert util.csv_col_int(csv_file, col)


def test_measures_conversion(csv_file: Generator[str]) -> None:
    """test_measures_conversion"""
    assert util.run_cmd(measures_export.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -r -p --withTags") == e.OK
    assert util.csv_col_match(csv_file, "reliability_rating", _RATING_NUMBER)
    assert util.csv_col_match(csv_file, "security_rating", _RATING_NUMBER)
    assert util.csv_col_pct(csv_file, "duplicated_lines_density", True)
    assert util.csv_col_pct(csv_file, "sqale_debt_ratio", True)


def test_measures_export_with_url(csv_file: Generator[str]) -> None:
    """test_measures_export_with_url"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.BRANCH_REGEXP_SHORT} .+ -{opt.METRIC_KEYS_SHORT} _main --{opt.WITH_URL}"
    if util.SQ.edition() == c.CE:
        assert util.run_cmd(measures_export.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.csv_col_url(csv_file, "url")


def test_measures_export_json(json_file: Generator[str]) -> None:
    """test_measures_export_json"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {json_file} -{opt.BRANCH_REGEXP_SHORT} .+ -{opt.METRIC_KEYS_SHORT} _main"
    if util.SQ.edition() == c.CE:
        assert util.run_cmd(measures_export.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.json_field_sorted(json_file, "key")
    assert util.json_field_match(json_file, "reliability_rating", _RATING_LETTER, allow_null=True)
    assert util.json_field_match(json_file, "security_rating", _RATING_LETTER, allow_null=True)
    assert util.json_field_float(json_file, "duplicated_lines_density")
    assert util.json_field_float(json_file, "sqale_debt_ratio")
    assert util.json_fields_absent(json_file, "statements", "ncloc_language_distribution")
    col_list = col_list = ("false_positive_issues",)
    if util.SQ.version() >= c.MQR_INTRO_VERSION:
        col_list += ("accepted_issues", "prioritized_rule_issues")
    assert util.json_fields_present(json_file, *col_list)
    for col in col_list:
        assert util.json_field_int(json_file, col)


def test_measures_export_all(csv_file: Generator[str]) -> None:
    """test_measures_export_all"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.METRIC_KEYS_SHORT} _all"
    if util.SQ.edition() != c.CE:
        cmd += f" -{opt.BRANCH_REGEXP_SHORT} .+"
    assert util.run_cmd(measures_export.main, cmd) == e.OK


def test_measures_export_json_all(json_file: Generator[str]) -> None:
    """test_measures_export_json_all"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {json_file} --{opt.METRIC_KEYS} _all"
    if util.SQ.edition() != c.CE:
        cmd += f" -{opt.BRANCH_REGEXP_SHORT} .+"
    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.json_field_int(json_file, "statements")
    assert util.json_fields_present(json_file, "ncloc_language_distribution")


def test_measures_export_history(csv_file: Generator[str]) -> None:
    """test_measures_export_history"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --{opt.METRIC_KEYS} _all"
    assert util.run_cmd(measures_export.main, cmd) == e.OK


def test_measures_export_history_as_table(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable"
    assert util.run_cmd(measures_export.main, cmd) == e.OK


def test_measures_export_history_as_table_no_time(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table_no_time"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable -d"
    assert util.run_cmd(measures_export.main, cmd) == e.OK


def test_measures_export_history_as_table_with_url(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table_with_url"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable --{opt.WITH_URL}"
    assert util.run_cmd(measures_export.main, cmd) == e.OK


def test_measures_export_history_as_table_with_branch(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table_with_branch"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable"
    if util.SQ.edition() != c.CE:
        cmd += f" -{opt.BRANCH_REGEXP_SHORT} .+"
    assert util.run_cmd(measures_export.main, cmd) == e.OK


def test_measures_export_dateonly(csv_file: Generator[str]) -> None:
    """test_measures_export_dateonly"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -d"
    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.csv_col_date(csv_file, "lastAnalysis")


def test_measures_export_json_dateonly(json_file: Generator[str]) -> None:
    """test_measures_export_json_dateonly"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {json_file} -d"
    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.json_field_date(json_file, "lastAnalysis")


def test_specific_measure(csv_file: Generator[str]) -> None:
    """test_specific_measure"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.METRIC_KEYS_SHORT} sqale_index,coverage"
    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.csv_col_int(csv_file, "sqale_index")
    assert util.csv_col_float_pct(csv_file, "coverage")
    assert not util.csv_cols_present(csv_file, "code_smells", "bugs", "security_rating")


def test_non_existing_measure(csv_file: Generator[str]) -> None:
    """test_non_existing_measure"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.METRIC_KEYS_SHORT} ncloc,sqale_index,bad_measure"
    assert util.run_cmd(measures_export.main, cmd) == e.NO_SUCH_KEY


def test_non_existing_project(csv_file: Generator[str]) -> None:
    """test_non_existing_project"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.KEY_REGEXP_SHORT} bad_project"
    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.csv_nbr_lines(csv_file) == 0


def test_specific_project_keys(csv_file: Generator[str]) -> None:
    """test_non_existing_project"""
    projects = ["okorach_sonar-tools", "project1", "project4"]
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.KEY_REGEXP_SHORT} {utilities.list_to_regexp(projects)}"
    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.csv_nbr_lines(csv_file) == len(projects)
    assert util.csv_col_is_value(csv_file, "key", *projects)


def test_apps_measures(csv_file: Generator[str]) -> None:
    """test_apps_measures"""
    existing_key = "APP_TEST"
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --{opt.APPS} -m ncloc"
    if util.SQ.edition() == c.CE:
        assert util.run_cmd(measures_export.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.csv_nbr_cols(csv_file, 5)
    assert util.csv_col_has_values(csv_file, "key", existing_key)


def test_portfolios_measures(csv_file: Generator[str]) -> None:
    """test_portfolios_measures"""
    existing_key = "PORTFOLIO_ALL"
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --{opt.PORTFOLIOS} -m ncloc"
    if util.SQ.edition() in (c.CE, c.DE):
        assert util.run_cmd(measures_export.main, cmd) == e.UNSUPPORTED_OPERATION
        return

    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.csv_nbr_cols(csv_file, 5)
    assert util.csv_col_has_values(csv_file, "key", existing_key)


def test_portfolios_with_tags(csv_file: Generator[str]) -> None:
    """test_portfolios_with_tags"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --{opt.PORTFOLIOS} --{opt.WITH_TAGS} -m ncloc"
    assert util.run_cmd(measures_export.main, cmd) == e.ARGS_ERROR


def test_basic(csv_file: Generator[str]) -> None:
    """Tests that basic invocation against a CE and DE works"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file}"
    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.csv_col_is_value(csv_file, "type", "PROJECT")


def test_option_apps(csv_file: Generator[str]) -> None:
    """Tests that using the --apps option works in the correct editions (DE and higher)"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.APPS}"
    if util.SQ.edition() == c.CE:
        assert util.run_cmd(measures_export.main, cmd) == e.UNSUPPORTED_OPERATION
        return

    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.csv_col_is_value(csv_file, "type", "APPLICATION")


def test_option_portfolios(csv_file: Generator[str]) -> None:
    """Tests that using the --portfolios option works in the correct editions (EE and higher)"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.PORTFOLIOS}"
    if util.SQ.edition() in (c.CE, c.DE):
        assert util.run_cmd(measures_export.main, cmd) == e.UNSUPPORTED_OPERATION
        return

    assert util.run_cmd(measures_export.main, cmd) == e.OK
    assert util.csv_col_is_value(csv_file, "type", "PORTFOLIO")
