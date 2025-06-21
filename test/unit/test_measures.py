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
from sonar import errcodes, logging, utilities
import sonar.util.constants as c

from cli import measures_export
import cli.options as opt

CMD = "sonar-measures-export.py"
CMD = f"{CMD} {util.SQS_OPTS}"
_RATING_LETTER = r"^[A-E]?$"
_RATING_NUMBER = r"^[1-5]?$"


def test_measures_export(csv_file: Generator[str]) -> None:
    """test_measures_export"""
    util.run_success_cmd(measures_export.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --withTags")
    assert util.csv_col_sorted(csv_file, "key")
    assert util.csv_col_match(csv_file, "reliability_rating", _RATING_LETTER)
    assert util.csv_col_match(csv_file, "security_rating", _RATING_LETTER)
    assert util.csv_col_match(csv_file, "duplicated_lines_density", r"^(|[0-9.]+)$")
    assert util.csv_col_match(csv_file, "sqale_debt_ratio", r"^(|[0-9.]+)$")


def test_measures_conversion(csv_file: Generator[str]) -> None:
    """test_measures_conversion"""
    util.run_success_cmd(measures_export.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -r -p --withTags")
    assert util.csv_col_match(csv_file, "reliability_rating", _RATING_NUMBER)
    assert util.csv_col_match(csv_file, "security_rating", _RATING_NUMBER)
    assert util.csv_col_match(csv_file, "duplicated_lines_density", r"^(|.+%)$")
    assert util.csv_col_match(csv_file, "sqale_debt_ratio", r"^(|.+%)$")


def test_measures_export_with_url(csv_file: Generator[str]) -> None:
    """test_measures_export_with_url"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.BRANCH_REGEXP_SHORT} .+ -{opt.METRIC_KEYS_SHORT} _main --{opt.WITH_URL}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
    else:
        util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_json(json_file: Generator[str]) -> None:
    """test_measures_export_json"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {json_file} -{opt.BRANCH_REGEXP_SHORT} .+ -{opt.METRIC_KEYS_SHORT} _main"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return
    util.run_success_cmd(measures_export.main, cmd)
    assert util.json_field_sorted(json_file, "key")
    assert util.json_field_match(json_file, "reliability_rating", _RATING_LETTER, allow_null=True)
    assert util.json_field_match(json_file, "security_rating", _RATING_LETTER, allow_null=True)
    assert util.json_field_float(json_file, "duplicated_lines_density")
    assert util.json_field_float(json_file, "sqale_debt_ratio")


def test_measures_export_all(csv_file: Generator[str]) -> None:
    """test_measures_export_all"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.METRIC_KEYS_SHORT} _all"
    if util.SQ.edition() != c.CE:
        cmd += f" -{opt.BRANCH_REGEXP_SHORT} .+"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_json_all(json_file: Generator[str]) -> None:
    """test_measures_export_json_all"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {json_file} --{opt.METRIC_KEYS} _all"
    if util.SQ.edition() != c.CE:
        cmd += f" -{opt.BRANCH_REGEXP_SHORT} .+"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_history(csv_file: Generator[str]) -> None:
    """test_measures_export_history"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --{opt.METRIC_KEYS} _all"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_history_as_table(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_history_as_table_no_time(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table_no_time"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable -d"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_history_as_table_with_url(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table_with_url"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable --{opt.WITH_URL}"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_history_as_table_with_branch(csv_file: Generator[str]) -> None:
    """test_measures_export_history_as_table_with_branch"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --history --asTable"
    if util.SQ.edition() != c.CE:
        cmd += f" -{opt.BRANCH_REGEXP_SHORT} .+"
    util.run_success_cmd(measures_export.main, cmd)


def test_measures_export_dateonly(csv_file: Generator[str]) -> None:
    """test_measures_export_dateonly"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -d"
    util.run_success_cmd(measures_export.main, cmd)


def test_specific_measure(csv_file: Generator[str]) -> None:
    """test_specific_measure"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.METRIC_KEYS_SHORT} sqale_index,coverage"
    util.run_success_cmd(measures_export.main, cmd)
    assert util.csv_col_int(csv_file, "sqale_index")
    assert util.csv_col_float_pct(csv_file, "coverage")


def test_non_existing_measure(csv_file: Generator[str]) -> None:
    """test_non_existing_measure"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.METRIC_KEYS_SHORT} ncloc,sqale_index,bad_measure"
    util.run_failed_cmd(measures_export.main, cmd, errcodes.NO_SUCH_KEY)


def test_non_existing_project(csv_file: Generator[str]) -> None:
    """test_non_existing_project"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.KEY_REGEXP_SHORT} bad_project"
    util.run_success_cmd(measures_export.main, cmd)
    assert util.csv_nbr_lines(csv_file) == 0


def test_specific_project_keys(csv_file: Generator[str]) -> None:
    """test_non_existing_project"""
    projects = ["okorach_sonar-tools", "project1", "project4"]
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.KEY_REGEXP_SHORT} {utilities.list_to_regexp(projects)}"
    util.run_success_cmd(measures_export.main, cmd)
    assert util.csv_nbr_lines(csv_file) == len(projects)
    assert util.csv_col_is_value(csv_file, "key", *projects)


def test_apps_measures(csv_file: Generator[str]) -> None:
    """test_apps_measures"""
    existing_key = "APP_TEST"
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --{opt.APPS} -m ncloc"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return
    util.run_success_cmd(measures_export.main, cmd)
    assert util.csv_nbr_cols(csv_file, 4)
    assert util.csv_col_has_values(csv_file, "key", {existing_key})


def test_portfolios_measures(csv_file: Generator[str]) -> None:
    """test_portfolios_measures"""
    existing_key = "PORTFOLIO_ALL"
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --{opt.PORTFOLIOS} -m ncloc"
    if util.SQ.edition() in (c.CE, c.DE):
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(measures_export.main, cmd)
    assert util.csv_nbr_cols(csv_file, 4)
    assert util.csv_col_has_values(csv_file, "key", {existing_key})


def test_portfolios_with_tags(csv_file: Generator[str]) -> None:
    """test_portfolios_with_tags"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} --{opt.PORTFOLIOS} --{opt.WITH_TAGS} -m ncloc"
    util.run_failed_cmd(measures_export.main, cmd, errcodes.ARGS_ERROR)


def test_basic(csv_file: Generator[str]) -> None:
    """Tests that basic invocation against a CE and DE works"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file}"
    util.run_success_cmd(measures_export.main, cmd)
    assert util.csv_col_is_value(csv_file, "type", "PROJECT")


def test_option_apps(csv_file: Generator[str]) -> None:
    """Tests that using the --apps option works in the correct editions (DE and higher)"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.APPS}"
    if util.SQ.edition() == c.CE:
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(measures_export.main, cmd)
    assert util.csv_col_is_value(csv_file, "type", "APPLICATION")


def test_option_portfolios(csv_file: Generator[str]) -> None:
    """Tests that using the --portfolios option works in the correct editions (EE and higher)"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.PORTFOLIOS}"
    if util.SQ.edition() in (c.CE, c.DE):
        util.run_failed_cmd(measures_export.main, cmd, errcodes.UNSUPPORTED_OPERATION)
        return

    util.run_success_cmd(measures_export.main, cmd)
    assert util.csv_col_is_value(csv_file, "type", "PORTFOLIO")
