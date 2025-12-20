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


def __rounded(nbr: float) -> float:
    """Rounds a float to 3 decimal digits"""
    return float(f"{nbr:.3f}")


def __count_percentage(part: int, total: int) -> dict[str, float]:
    """Computes percentage value"""
    if total == 0:
        return {"count": 0, "percentage": 0.0}
    return {"count": part, "percentage": __rounded(part / total)}


def get_maturity_data(project: projects.Project) -> dict[str, Any]:
    """Gets the maturity data for a project"""
    data = {
        "key": project.key,
        QG: project.get_measure(QG_METRIC),
        "ncloc": project.get_measure("ncloc"),
        "lines": project.get_measure("lines"),
        "new_lines": project.get_measure("new_lines"),
        "new_code_age": util.age(project.new_code_start_date()),
        AGE: util.age(project.last_analysis(include_branches=True)),
        f"main_branch_{AGE}": util.age(project.main_branch().last_analysis()),
    }
    if data[QG] is None and data["lines"] is None:
        data[QG] = "NONE/NEVER_ANALYZED"
    data["new_code_lines_ratio"] = None if data["new_lines"] is None else __rounded(min(1.0, data["new_lines"] / data["lines"]))
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
        summary_data["any_branch"][key] = __count_percentage(count, nbr_projects)
        count = sum(1 for d in data.values() if d["lines"] is not None and low_bound < d[f"main_branch_{AGE}"] <= high_bound)
        summary_data["main_branch"][key] = __count_percentage(count, nbr_projects)
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

    total_7_days = total_count_7_days_pass + total_count_7_days_fail
    summary_data = {
        "pull_requests_total": total_prs,
        "pull_requests_passing_quality_gate": __count_percentage(total_count_pass, total_prs),
        "pull_requests_failing_quality_gate": __count_percentage(total_count_fail, total_prs),
        "pull_requests_not_analyzed_since_7_days_total": total_7_days,
        "pull_requests_not_analyzed_since_7_days_passing_quality_gate": __count_percentage(total_count_7_days_pass, total_7_days),
        "pull_requests_not_analyzed_since_7_days_failing_quality_gate": __count_percentage(total_count_7_days_fail, total_7_days),
        "projects_enforcing_pr_quality_gate": __count_percentage(total_count_enforced, len(data)),
        "projects_not_enforcing_pr_quality_gate": __count_percentage(total_count_non_enforced, len(data)),
        "projects_with_no_pull_requests": __count_percentage(total_count_no_prs, len(data)),
    }
    return summary_data


def compute_summary_qg(data: dict[str, Any]) -> dict[str, Any]:
    """Computes statistics on quality gate statuses"""
    nbr_projects = len(data)
    summary_data = {}
    possible_status = {d[QG] for d in data.values()}
    for status in possible_status:
        count = sum(1 for d in data.values() if d[QG] == status)
        summary_data[status] = __count_percentage(count, nbr_projects)
    return summary_data


def compute_new_code_statistics(data: dict[str, Any]) -> dict[str, Any]:
    """Computes statistics on new code"""
    nbr_projects = len(data)
    summary_data = {"new_code_in_days": {}, "new_code_in_percentage": {}}
    # Filter out projects with no new node
    data_nc = {k: v for k, v in data.items() if v["new_lines"] is not None}
    summary_data["new_code_in_days"]["no_new_code"] = __count_percentage(nbr_projects - len(data_nc), nbr_projects)
    summary_data["new_code_in_percentage"]["no_new_code"] = summary_data["new_code_in_days"]["no_new_code"]

    segments = [30, 60, 90, 180, 365, 10000]
    low_bound = -1
    for i in range(len(segments)):
        high_bound = segments[i]
        if i + 1 < len(segments):
            key = f"between_{low_bound+1}_and_{high_bound}_days"
            count = sum(1 for d in data_nc.values() if low_bound < d["new_code_age"] <= high_bound)
        else:
            key = f"more_than_{low_bound}_days"
            count = sum(1 for d in data_nc.values() if low_bound < d["new_code_age"])
        summary_data["new_code_in_days"][key] = __count_percentage(count, nbr_projects)
        low_bound = high_bound
    low_bound = -0.001
    segments = [0.05, 0.1, 0.2, 0.4, 0.7, 1.0]
    for i in range(len(segments)):
        high_bound = segments[i]
        if i + 1 < len(segments):
            key = f"between_{int(low_bound*100)}_and_{int(high_bound*100)}_percent"
            count = sum(1 for d in data_nc.values() if d["lines"] != 0 and low_bound < d["new_lines"] / d["lines"] <= high_bound)
        else:
            key = f"more_than_{int(low_bound*100)}_percent"
            count = sum(1 for d in data_nc.values() if d["lines"] != 0 and low_bound < d["new_lines"] / d["lines"])
        summary_data["new_code_in_percentage"][key] = __count_percentage(count, nbr_projects)
        low_bound = high_bound

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
        summary_data["new_code_statistics"] = compute_new_code_statistics(maturity_data)
        write_results(kwargs.get(options.REPORT_FILE), {"summary": summary_data, "details": maturity_data})
    except exceptions.SonarException as e:
        chelp.clear_cache_and_exit(e.errcode, e.message)

    chelp.clear_cache_and_exit(0, start_time=start_time)
