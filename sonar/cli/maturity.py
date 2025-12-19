#!/usr/bin/env python3
#
# sonar-tools
# Copyright (C) 2025 Olivier Korach
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
"""Computes SonarQube maturity metrics"""

from typing import Any
from sonar import utilities as util
from sonar import version
from cli import options
from sonar import exceptions
from sonar import platform
from sonar.util import common_helper as chelp
from sonar.util import component_helper
from sonar import errcodes
from sonar import projects
from sonar import logging as log

TOOL_NAME = "sonar-maturity"

QG_METRIC = "alert_status"
QG = "quality_gate"
AGE = "last_analysis_age"


def __parse_args(desc: str) -> object:
    """Set and parses CLI arguments"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("json",))
    parser = options.add_component_type_arg(parser)
    args = options.parse_and_check(parser=parser, logger_name=TOOL_NAME)

    return args


def get_maturity_data(project: projects.Project) -> dict[str, Any]:
    """Gets the maturity data for a project"""
    data = {
        "key": project.key,
        QG: project.get_measure(QG_METRIC),
        "ncloc": project.get_measure("ncloc"),
        "lines": project.get_measure("lines"),
        "new_lines": project.get_measure("new_lines"),
        AGE: util.age(project.last_analysis(include_branches=True)),
        f"main_branch_{AGE}": util.age(project.main_branch().last_analysis()),
    }
    if data[QG] is None and data["lines"] is None:
        data[QG] = "NONE/NEVER_ANALYZED"
    prs = project.pull_requests().values()
    data["pull_requests"] = {pr.key: {QG: pr.get_measure(QG_METRIC), AGE: util.age(pr.last_analysis())} for pr in prs}
    return data


def compute_summary_age(data: dict[str, Any]) -> dict[str, Any]:
    """Computes statistics on last analysis"""
    nbr_projects = len(data)
    summary_data = {"any_branch": {"never_analyzed": sum(1 for d in data.values() if d["lines"] is None)}, "main_branch": {}}
    segments = [1, 3, 7, 15, 30, 90, 180, 365, 10000]
    low_bound = -1
    for high_bound in segments:
        key = f"between_{low_bound+1}_and_{high_bound}_days"
        count = sum(1 for d in data.values() if d["lines"] is not None and low_bound < d[AGE] <= high_bound)
        summary_data["any_branch"][key] = {"count": count, "percentage": float(f"{count/nbr_projects:.3f}")}
        count = sum(1 for d in data.values() if d["lines"] is not None and low_bound < d[f"main_branch_{AGE}"] <= high_bound)
        summary_data["main_branch"][key] = {"count": count, "percentage": float(f"{count/nbr_projects:.3f}")}
        low_bound = high_bound
    return summary_data


def compute_project_pr_statistics(project_data: dict[str, Any]) -> tuple[int, int, int, int, int]:
    """Computes project level PR statistics related to maturity"""
    proj_count_7_days_pass, proj_count_7_days_fail = 0, 0
    proj_count_pass, proj_count_fail, count_no_prs = 0, 0, 0
    pr_list = project_data.get("pull_requests", {}).values()
    for pr_data in pr_list:
        if pr_data.get(QG) == "OK":
            proj_count_pass += 1
            if pr_data.get(AGE) > 7:
                proj_count_7_days_pass += 1
        else:
            proj_count_fail += 1
            if pr_data.get(AGE) > 7:
                proj_count_7_days_fail += 1
    project_data["pull_request_stats"] = {
        "pr_pass_total": proj_count_pass,
        "pr_fail_total": proj_count_fail,
        "pr_pass_7_days": proj_count_7_days_pass,
        "pr_fail_7_days": proj_count_7_days_fail,
    }
    count_no_prs = 1 if len(pr_list) == 0 else 0
    return proj_count_7_days_pass, proj_count_7_days_fail, proj_count_pass, proj_count_fail, count_no_prs


def compute_pr_statistics(data: dict[str, Any]) -> dict[str, Any]:
    """Computes statistics on pull request analyses"""
    total_prs = sum(len(d.get("pull_requests", {})) for d in data.values())
    summary_data = {}
    total_count_7_days_pass, total_count_7_days_fail = 0, 0
    total_count_pass, total_count_fail, total_count_no_prs = 0, 0, 0
    total_count_enforced, total_count_non_enforced = 0, 0
    for proj_data in data.values():
        count_7_days_pass, count_7_days_fail, count_pass, count_fail, count_no_prs = compute_project_pr_statistics(proj_data)
        if count_no_prs == 0:
            if count_7_days_fail == 0:
                total_count_enforced += 1
            else:
                total_count_non_enforced += 1
        total_count_7_days_pass += count_7_days_pass
        total_count_7_days_fail += count_7_days_fail
        total_count_pass += count_pass
        total_count_fail += count_fail
        total_count_no_prs += count_no_prs

    summary_data = {
        "nbr_of_pull_requests": total_prs,
        "nbr_of_pull_requests_not_analyzed_since_7_days": total_count_7_days_fail + total_count_7_days_pass,
        "nbr_of_pull_requests_passing_quality_gate": {"count": total_count_pass, "percentage": float(f"{total_count_pass/total_prs:.3f}")},
        "nbr_of_pull_requests_failing_quality_gate": {"count": total_count_fail, "percentage": float(f"{total_count_fail/total_prs:.3f}")},
        "nbr_of_pull_requests_not_analyzed_since_7_days_passing_quality_gate": {
            "count": total_count_7_days_pass,
            "percentage": float(f"{total_count_7_days_pass/(total_count_7_days_pass + total_count_7_days_fail):.3f}"),
        },
        "nbr_of_pull_requests_not_analyzed_since_7_days_failing_quality_gate": {
            "count": total_count_7_days_fail,
            "percentage": float(f"{total_count_7_days_fail/(total_count_7_days_pass + total_count_7_days_fail):.3f}"),
        },
        "nbr_of_projects_enforcing_pr_quality_gate": {
            "count": total_count_enforced,
            "percentage": float(f"{total_count_enforced/len(data):.3f}"),
        },
        "nbr_of_projects_not_enforcing_pr_quality_gate": {
            "count": total_count_non_enforced,
            "percentage": float(f"{total_count_non_enforced/len(data):.3f}"),
        },
        "nbr_of_projects_with_no_pull_requests": {"count": total_count_no_prs, "percentage": float(f"{total_count_no_prs/len(data):.3f}")},
    }
    return summary_data


def compute_summary_qg(data: dict[str, Any]) -> dict[str, Any]:
    """Computes statistics on quality gate statuses"""
    nbr_projects = len(data)
    summary_data = {}
    possible_status = {d[QG] for d in data.values()}
    for status in possible_status:
        count = sum(1 for d in data.values() if d[QG] == status)
        summary_data[status] = {"count": count, "percentage": float(f"{count/nbr_projects:.3f}")}
    return summary_data


def write_results(filename: str, data: dict[str, Any]) -> None:
    """Writes results to a file"""
    with util.open_file(filename) as fd:
        print(util.json_dump(data), file=fd)
    log.info(f"Maturity report written to file '{filename}'")


def main() -> None:
    """Entry point for sonar-maturity"""
    start_time = util.start_clock()
    try:
        kwargs = util.convert_args(__parse_args("Extracts a maturity score for a platform, a project or a portfolio"))
        sq = platform.Platform(**kwargs)
        sq.verify_connection()
        sq.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")
        project_list = component_helper.get_components(
            endpoint=sq,
            component_type="projects",
            key_regexp=kwargs[options.KEY_REGEXP],
            branch_regexp=None,
        )
        if len(project_list) == 0:
            raise exceptions.SonarException(f"No project matching regexp '{kwargs[options.KEY_REGEXP]}'", errcodes.WRONG_SEARCH_CRITERIA)
        i, nb_projects = 0, len(project_list)
        maturity_data = {}
        for project in project_list:
            log.debug("Collecting maturity data for %s", project)
            maturity_data[project.key] = get_maturity_data(project)
            i += 1
            if i % 10 == 0 or i == nb_projects:
                log.info("Collected maturity data for %d/%d projects (%d%%)", i, nb_projects, int(100 * i / nb_projects))

        summary_data: dict[str, Any] = {}
        summary_data["total_projects"] = len(maturity_data)
        summary_data["quality_gate_project_statistics"] = compute_summary_qg(maturity_data)
        summary_data["last_analysis_statistics"] = compute_summary_age(maturity_data)
        summary_data["quality_gate_enforcement_statistics"] = compute_pr_statistics(maturity_data)
        write_results(kwargs.get(options.REPORT_FILE), {"summary": summary_data, "details": maturity_data})
    except exceptions.SonarException as e:
        chelp.clear_cache_and_exit(e.errcode, e.message)

    chelp.clear_cache_and_exit(0, start_time=start_time)
