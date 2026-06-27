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

"""sonar-loc tests"""

from collections.abc import Generator
from datetime import datetime

import utilities as tutil
from sonar import errcodes as e
import sonar.util.constants as c

from cli import loc
import cli.options as opt

# ---------------------------------------------------------------------------
# Lightweight stubs for the sort-helper unit tests
# ---------------------------------------------------------------------------


class _Project:
    """Minimal project stub: no concerned_object (it IS the project)."""

    concerned_object = None

    def __init__(self, key: str, ncloc: int, last_analysis: datetime) -> None:
        self.key = key
        self._ncloc = ncloc
        self._la = last_analysis

    def loc(self) -> int:
        return self._ncloc

    def last_analysis(self) -> datetime:
        return self._la


class _Branch:
    """Minimal branch stub: has a concerned_object (its parent project)."""

    def __init__(self, project: _Project, ncloc: int, last_analysis: datetime) -> None:
        self.concerned_object = project
        self.key = f"{project.key}:branch"
        self._ncloc = ncloc
        self._la = last_analysis

    def loc(self) -> int:
        return self._ncloc

    def last_analysis(self) -> datetime:
        return self._la


# Module-level double-underscore names aren't importable by normal syntax;
# retrieve them from the module's __dict__ directly.
_project_key = loc.__dict__["__project_key"]
_object_ncloc = loc.__dict__["__object_ncloc"]
_latest = loc.__dict__["__latest"]
_aggregate_by_project = loc.__dict__["__aggregate_by_project"]
_sort_key = loc.__dict__["__sort_key"]
_sort_objects = loc.__dict__["__sort_objects"]

# Shared fixtures used across the sort tests
_P_ALPHA = _Project("alpha", 100, datetime(2024, 1, 1))
_P_BETA = _Project("beta", 50, datetime(2025, 6, 1))
_P_GAMMA = _Project("gamma", 200, None)  # never analysed

CLI = "sonar-loc.py"
CMD = f"{CLI} {tutil.SQS_OPTS}"
ALL_OPTIONS = f"-{opt.BRANCH_REGEXP_SHORT} .+ --{opt.WITH_LAST_ANALYSIS} --{opt.WITH_NAME} --{opt.WITH_URL}"


def test_loc(csv_file: Generator[str]) -> None:
    """test_loc"""
    assert tutil.run_cmd(loc.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file}") == e.OK
    assert tutil.csv_nbr_lines(csv_file) > 0
    assert tutil.csv_col_int(csv_file, "ncloc", False)
    assert tutil.csv_col_sorted(csv_file, "project key")


def test_loc_json(json_file: Generator[str]) -> None:
    """test_loc_json"""
    assert tutil.run_cmd(loc.main, f"{CMD} -{opt.REPORT_FILE_SHORT} {json_file}") == e.OK
    assert tutil.json_field_sorted(json_file, "project")
    assert tutil.json_field_int(json_file, "ncloc", False)


def test_loc_json_fmt(txt_file: Generator[str]) -> None:
    """test_loc_json_fmt"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {txt_file} --{opt.FORMAT} json"
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.json_field_sorted(txt_file, "project")


def test_loc_csv_fmt(txt_file: Generator[str]) -> None:
    """test_loc_csv_fmt"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {txt_file} --{opt.FORMAT} csv"
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    # Verify that the file is a valid CSV file
    assert tutil.csv_cols_present(txt_file, "project key", "ncloc")


def test_loc_project(csv_file: Generator[str]) -> None:
    """test_loc_project"""
    cmd = f"{CMD} -{opt.REPORT_FILE_SHORT} {csv_file} -{opt.KEY_REGEXP_SHORT} {tutil.LIVE_PROJECT}"
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.csv_nbr_lines(csv_file) == 1
    assert tutil.csv_col_is_value(csv_file, "project key", tutil.LIVE_PROJECT)


def test_loc_project_with_all_options(csv_file: Generator[str]) -> None:
    """test_loc_project_with_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.KEY_REGEXP} {tutil.LIVE_PROJECT} --{opt.WITH_URL} -{opt.WITH_NAME_SHORT} -{opt.WITH_LAST_ANALYSIS_SHORT}"
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.csv_col_url(csv_file, "URL")


def test_loc_portfolios(csv_file: Generator[str]) -> None:
    """test_loc_portfolios"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.PORTFOLIOS} --topLevelOnly --{opt.WITH_URL}"
    if tutil.SQ.edition() in (c.CE, c.DE):
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.csv_col_sorted(csv_file, "portfolio key")
    assert tutil.csv_col_int(csv_file, "ncloc", False)


def test_loc_separator(csv_file: Generator[str]) -> None:
    """test_loc_separator"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.CSV_SEPARATOR} +"
    assert tutil.run_cmd(loc.main, cmd) == e.OK


def test_loc_branches(csv_file: Generator[str]) -> None:
    """test_loc_branches"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} {ALL_OPTIONS} --{opt.WITH_TAGS}"
    if tutil.SQ.edition() == c.CE:
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.csv_col_match(csv_file, "branch", r"^(|[^\s]+)$")


def test_loc_pull_requests(csv_file: Generator[str]) -> None:
    """test_loc_pull_requests"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.PULL_REQUESTS} --{opt.WITH_TAGS}"
    if tutil.SQ.edition() == c.CE:
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.csv_col_int(csv_file, "pr")
    assert tutil.csv_col_is_value(csv_file, "type", "pullrequest", "project")


def test_loc_branches_json(json_file: Generator[str]) -> None:
    """test_loc"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS} --{opt.WITH_TAGS}"
    if tutil.SQ.edition() == c.CE:
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.json_field_match(json_file, "branch", r"^(|[^\s]+)$")


def test_loc_proj_all_options(csv_file: Generator[str]) -> None:
    """test_loc_proj_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} {ALL_OPTIONS} --{opt.WITH_TAGS}"
    if tutil.SQ.edition() == c.CE:
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return

    assert tutil.run_cmd(loc.main, cmd) == e.OK
    # Check file contents
    assert tutil.csv_cols_present(csv_file, "project key", "branch", "project name", "tags")
    assert tutil.csv_col_datetime(csv_file, "last analysis")
    assert tutil.csv_col_int(csv_file, "ncloc", False)
    assert tutil.csv_col_url(csv_file, "URL")
    assert tutil.csv_col_datetime(csv_file, "last analysis")
    assert not tutil.csv_col_all_empty(csv_file, "tags")


def test_loc_apps_all_options(csv_file: Generator[str]) -> None:
    """test_loc_apps_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --apps {ALL_OPTIONS} --{opt.WITH_TAGS}"
    if tutil.SQ.edition() == c.CE:
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return

    assert tutil.run_cmd(loc.main, cmd) == e.OK
    # Check file contents
    assert tutil.csv_cols_present(csv_file, "app key", "app name", "branch", "tags")
    assert tutil.csv_col_int(csv_file, "ncloc", False)
    assert tutil.csv_col_url(csv_file, "URL")
    assert tutil.csv_col_datetime(csv_file, "last analysis")
    assert not tutil.csv_col_all_empty(csv_file, "tags")


def test_loc_portfolios_all_options(csv_file: Generator[str]) -> None:
    """test_loc_portfolios_all_options"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --portfolios {ALL_OPTIONS}"
    if tutil.SQ.edition() in (c.CE, c.DE):
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.csv_cols_present(csv_file, "portfolio key", "portfolio name")
    assert tutil.csv_col_int(csv_file, "ncloc", False)
    assert tutil.csv_col_datetime(csv_file, "last analysis")
    assert tutil.csv_col_url(csv_file, "URL")


def test_loc_proj_all_options_json(json_file: Generator[str]) -> None:
    """test_loc_proj_all_options_json"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS} --{opt.WITH_TAGS}"
    if tutil.SQ.edition() == c.CE:
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return

    assert tutil.run_cmd(loc.main, cmd) == e.OK
    # Check file contents
    assert tutil.json_fields_present(json_file, "project", "projectName")
    assert tutil.json_field_int(json_file, "ncloc", False)
    assert tutil.json_field_url(json_file, "url")
    assert tutil.json_field_datetime(json_file, "lastAnalysis")
    assert tutil.json_field_not_all_empty(json_file, "tags")


def test_loc_apps_all_options_json(json_file: Generator[str]) -> None:
    """test_loc_apps_all_options_json"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS} --apps --{opt.WITH_TAGS}"
    if tutil.SQ.edition() == c.CE:
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return

    assert tutil.run_cmd(loc.main, cmd) == e.OK
    # Check file contents
    assert tutil.json_fields_present(json_file, "app", "appName")
    assert tutil.json_field_int(json_file, "ncloc", False)
    assert tutil.json_field_url(json_file, "url")
    assert tutil.json_field_datetime(json_file, "lastAnalysis")
    assert tutil.json_field_not_all_empty(json_file, "tags")


def test_loc_portfolios_all_options_json(json_file: Generator[str]) -> None:
    """test_loc_portfolios_all_options_json"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {json_file} {ALL_OPTIONS} --portfolios"
    if tutil.SQ.edition() in (c.CE, c.DE):
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return

    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.json_fields_present(json_file, "portfolio", "portfolioName")
    assert tutil.json_field_int(json_file, "ncloc", False)
    assert tutil.json_field_url(json_file, "url")
    assert tutil.json_field_datetime(json_file, "lastAnalysis")
    # Check file contents


def test_branch(csv_file: Generator[str]) -> None:
    """test_branch"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.BRANCH_REGEXP} develop"
    if tutil.SQ.edition() == c.CE:
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.csv_nbr_lines(csv_file) > 0
    assert not tutil.csv_col_all_empty(csv_file, "branch")
    assert tutil.csv_col_is_value(csv_file, "type", "branch", "project")
    assert tutil.csv_col_match(csv_file, "branch", r"^(develop|)$")
    assert tutil.csv_col_match(csv_file, "type", r"^(branch|project)$")
    assert tutil.csv_col_match(csv_file, "pr", r"^$")


def test_pr(csv_file: Generator[str]) -> None:
    """test_pr"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.PULL_REQUESTS}"
    if tutil.SQ.edition() == c.CE:
        assert tutil.run_cmd(loc.main, cmd) == e.UNSUPPORTED_OPERATION
        return
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.csv_nbr_lines(csv_file) > 0
    assert tutil.csv_col_is_value(csv_file, "type", "pullrequest", "project")
    assert not tutil.csv_col_all_empty(csv_file, "pr")
    assert tutil.csv_col_match(csv_file, "type", r"^(pullrequest|project)$")


def test_project_regexp(csv_file: Generator[str]) -> None:
    """test_pr"""
    cmd = f"{CMD} --{opt.REPORT_FILE} {csv_file} --{opt.KEY_REGEXP} okorach.+"
    assert tutil.run_cmd(loc.main, cmd) == e.OK
    assert tutil.csv_nbr_lines(csv_file) > 0
    assert tutil.csv_col_all_empty(csv_file, "pr")
    assert tutil.csv_col_all_empty(csv_file, "branch")
    assert tutil.csv_col_is_value(csv_file, "type", "project")
    assert tutil.csv_col_match(csv_file, "type", r"^project$")
    assert tutil.csv_col_match(csv_file, "project key", r"^okorach.+$")


# ---------------------------------------------------------------------------
# Unit tests for the sort helpers (no SonarQube connection required)
# ---------------------------------------------------------------------------


def test_sort_helper_project_key() -> None:
    """__project_key returns obj.key for projects and parent key for branches."""
    assert _project_key(_P_ALPHA) == "alpha"
    branch = _Branch(_P_ALPHA, 10, datetime(2024, 1, 1))
    assert _project_key(branch) == "alpha"


def test_sort_helper_object_ncloc() -> None:
    """__object_ncloc returns the LoC as int, 0 for None/invalid."""
    assert _object_ncloc(_P_ALPHA) == 100
    assert _object_ncloc(_P_GAMMA) == 200

    class _BadLoc:
        concerned_object = None
        key = "bad"

        def loc(self):
            return None

        def last_analysis(self):
            return None

    assert _object_ncloc(_BadLoc()) == 0


def test_sort_helper_latest() -> None:
    """__latest returns the most recent of two dates, ignoring None."""
    d1 = datetime(2024, 1, 1)
    d2 = datetime(2025, 6, 1)
    assert _latest(d1, d2) == d2
    assert _latest(d2, d1) == d2
    assert _latest(None, d1) == d1
    assert _latest(d1, None) == d1
    assert _latest(None, None) is None


def test_sort_helper_aggregate_by_project_ncloc() -> None:
    """__aggregate_by_project with ncloc takes the max across branches."""
    b1 = _Branch(_P_ALPHA, 300, datetime(2026, 1, 1))
    b2 = _Branch(_P_ALPHA, 10, datetime(2020, 1, 1))
    agg = _aggregate_by_project([b1, b2], "ncloc")
    assert agg["alpha"] == 300


def test_sort_helper_aggregate_by_project_last_analysis() -> None:
    """__aggregate_by_project with lastAnalysis takes the most recent date."""
    b1 = _Branch(_P_ALPHA, 100, datetime(2026, 1, 1))
    b2 = _Branch(_P_ALPHA, 100, datetime(2020, 1, 1))
    agg = _aggregate_by_project([b1, b2], "lastAnalysis")
    assert agg["alpha"] == datetime(2026, 1, 1)


def test_sort_helper_aggregate_none_last_analysis() -> None:
    """__aggregate_by_project keeps None for a project never analysed."""
    agg = _aggregate_by_project([_P_GAMMA], "lastAnalysis")
    assert agg["gamma"] is None


def test_sort_helper_sort_key_ncloc() -> None:
    """__sort_key for ncloc: ascending uses positive value, descending uses negative."""
    agg = {"alpha": 100}
    asc = _sort_key(_P_ALPHA, "ncloc", agg, reverse=False)
    desc = _sort_key(_P_ALPHA, "ncloc", agg, reverse=True)
    assert asc == (100.0, "alpha")
    assert desc == (-100.0, "alpha")


def test_sort_helper_sort_key_last_analysis_none() -> None:
    """__sort_key maps None last-analysis to +inf so it always sorts last."""
    agg = {"gamma": None}
    asc = _sort_key(_P_GAMMA, "lastAnalysis", agg, reverse=False)
    desc = _sort_key(_P_GAMMA, "lastAnalysis", agg, reverse=True)
    import math

    assert math.isinf(asc[0]) and asc[0] > 0
    assert math.isinf(desc[0]) and desc[0] > 0


def test_sort_objects_by_key() -> None:
    """__sort_objects with key+/key- sorts alphabetically."""
    objs = [_P_BETA, _P_ALPHA, _P_GAMMA]
    assert [o.key for o in _sort_objects(list(objs), "key+")] == ["alpha", "beta", "gamma"]
    assert [o.key for o in _sort_objects(list(objs), "key-")] == ["gamma", "beta", "alpha"]


def test_sort_objects_by_ncloc() -> None:
    """__sort_objects with ncloc+/ncloc- sorts by lines of code."""
    objs = [_P_BETA, _P_ALPHA, _P_GAMMA]  # ncloc: 50, 100, 200
    assert [o.key for o in _sort_objects(list(objs), "ncloc+")] == ["beta", "alpha", "gamma"]
    assert [o.key for o in _sort_objects(list(objs), "ncloc-")] == ["gamma", "alpha", "beta"]


def test_sort_objects_by_last_analysis_none_last() -> None:
    """__sort_objects puts never-analysed projects last in both directions."""
    objs = [_P_GAMMA, _P_BETA, _P_ALPHA]  # gamma has no analysis
    asc = [o.key for o in _sort_objects(list(objs), "lastAnalysis+")]
    desc = [o.key for o in _sort_objects(list(objs), "lastAnalysis-")]
    assert asc[-1] == "gamma"
    assert desc[-1] == "gamma"
    # alpha (2024) < beta (2025) ascending
    assert asc.index("alpha") < asc.index("beta")
    # beta (2025) first descending
    assert desc.index("beta") < desc.index("alpha")


def test_sort_objects_branch_aggregation_ncloc() -> None:
    """__sort_objects aggregates ncloc across branches — max wins."""
    p_g = _Project("gamma", 0, None)
    b1 = _Branch(p_g, 300, datetime(2026, 1, 1))
    b2 = _Branch(p_g, 10, datetime(2020, 1, 1))
    b_alpha = _Branch(_P_ALPHA, 100, datetime(2024, 1, 1))
    result = [o.key for o in _sort_objects([b_alpha, b1, b2], "ncloc-")]
    # gamma branches have max ncloc=300 > alpha=100 → gamma comes first
    assert result[0].startswith("gamma")
    assert result[1].startswith("gamma")
    assert result[2].startswith("alpha")


def test_sort_objects_filters_none() -> None:
    """__sort_objects silently drops None entries."""
    objs = [_P_ALPHA, None, _P_BETA]
    result = _sort_objects(objs, "key+")
    assert None not in result
    assert len(result) == 2
