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
import traceback
import concurrent.futures

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

AGE_KEY = "last_analysis_age"
NBR_OF_ANALYSES_KEY = "number_of_analyses"
ANALYSES_ANY_BRANCH_KEY = f"{NBR_OF_ANALYSES_KEY}_on_any_branch"
ANALYSES_MAIN_BRANCH_KEY = f"{NBR_OF_ANALYSES_KEY}_on_main_branch"

OVERALL_LOC_KEY = "lines_of_code"
OVERALL_LOC_METRIC = "ncloc"
OVERALL_LINES_KEY = "lines"
OVERALL_LINES_METRIC = "lines"
NEW_CODE_LINES_KEY = "new_code_lines"
NEW_CODE_LINES_METRIC = "new_lines"

NEW_CODE_RATIO_KEY = "new_code_lines_ratio"
NEW_CODE_DAYS_KEY = "new_code_in_days"


def __parse_args(desc: str) -> object:
    """Set and parses CLI arguments"""
    parser = options.set_common_args(desc)
    parser = options.add_thread_arg(parser, "collect project maturity data", 4)
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


def get_project_maturity_data(project: projects.Project) -> dict[str, Any]:
    """Gets the maturity data for a project"""
    log.debug("Collecting maturity data for %s", project)
    proj_measures = project.get_measures([QG_METRIC, OVERALL_LOC_METRIC, OVERALL_LINES_METRIC, NEW_CODE_LINES_METRIC])
    if proj_measures[QG_METRIC] is None or proj_measures[QG_METRIC].value is None:
        qg_status = "UNDEFINED"
        if proj_measures[NEW_CODE_LINES_METRIC] is None or proj_measures[NEW_CODE_LINES_METRIC].value is None:
            qg_status += "/NEVER_ANALYZED"
    else:
        qg_status = proj_measures[QG_METRIC].value
    data = {
        "key": project.key,
        QG: qg_status,
        OVERALL_LOC_KEY: None if not proj_measures[OVERALL_LOC_METRIC] else proj_measures[OVERALL_LOC_METRIC].value,
        OVERALL_LINES_KEY: None if not proj_measures[OVERALL_LINES_METRIC] else proj_measures[OVERALL_LINES_METRIC].value,
        NEW_CODE_LINES_KEY: None if not proj_measures[NEW_CODE_LINES_METRIC] else proj_measures[NEW_CODE_LINES_METRIC].value,
        NEW_CODE_DAYS_KEY: util.age(project.new_code_start_date()),
        AGE_KEY: util.age(project.last_analysis(include_branches=True)),
        f"main_branch_{AGE_KEY}": util.age(project.main_branch().last_analysis()),
    }
    data[NEW_CODE_RATIO_KEY] = None if data[NEW_CODE_LINES_KEY] is None else __rounded(min(1.0, data[NEW_CODE_LINES_KEY] / data["lines"]))

    # Extract project analysis history
    segments = [7, 30, 90]
    history = [util.age(util.string_to_date(d["date"])) for d in project.get_analyses()]
    log.debug("%s history of analysis = %s", project, history)
    section = ANALYSES_MAIN_BRANCH_KEY
    data[section] = {}
    for limit in segments:
        data[section][f"{limit}_days_or_less"] = sum(1 for v in history if v <= limit)
    data[section][f"more_than_{segments[-1]}_days"] = sum(1 for v in history if v > segments[-1])
    proj_branches = project.branches().values()
    history = []
    for branch in proj_branches:
        history += [util.age(util.string_to_date(d["date"])) for d in branch.get_analyses()]
    section = ANALYSES_ANY_BRANCH_KEY
    data[section] = {}
    for limit in [7, 30, 90]:
        data[section][f"{limit}_days_or_less"] = sum(1 for v in history if v <= limit)
    data[section][f"more_than_{segments[-1]}_days"] = sum(1 for v in history if v > segments[-1])
    history = sorted(history)
    log.debug("%s branches history of analysis = %s", project, history)

    # extract pul requests stats
    prs = project.pull_requests().values()
    data["pull_requests"] = {pr.key: {QG: pr.get_measure(QG_METRIC), AGE_KEY: util.age(pr.last_analysis())} for pr in prs}
    return data


def compute_summary_age(data: dict[str, Any]) -> dict[str, Any]:
    """Computes statistics on last analysis"""
    nbr_projects = len(data)
    summary_data = {"any_branch": {"never_analyzed": sum(1 for d in data.values() if d["lines"] is None)}, "main_branch": {}}
    segments = [1, 3, 7, 15, 30, 90, 180, 365, 10000]
    low_bound = -1
    for high_bound in segments:
        key = f"between_{low_bound+1}_and_{high_bound}_days"
        count = sum(1 for d in data.values() if d["lines"] is not None and low_bound < d[AGE_KEY] <= high_bound)
        summary_data["any_branch"][key] = __count_percentage(count, nbr_projects)
        count = sum(1 for d in data.values() if d["lines"] is not None and low_bound < d[f"main_branch_{AGE_KEY}"] <= high_bound)
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
            if pr_data.get(AGE_KEY) > 7:
                proj_count_7_days_pass += 1
        else:
            proj_count_fail += 1
            if pr_data.get(AGE_KEY) > 7:
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
    summary_data = {NEW_CODE_DAYS_KEY: {}, NEW_CODE_RATIO_KEY: {}}

    data_nc = {k: v for k, v in data.items() if v[NEW_CODE_LINES_KEY] is not None and v[NEW_CODE_DAYS_KEY] is not None}
    log.debug("Computes stats from %s", util.json_dump(data_nc))
    # Filter out projects with no new node
    summary_data[NEW_CODE_DAYS_KEY]["no_new_code"] = __count_percentage(nbr_projects - len(data_nc), nbr_projects)
    summary_data[NEW_CODE_RATIO_KEY]["no_new_code"] = summary_data[NEW_CODE_DAYS_KEY]["no_new_code"]

    segments = [30, 60, 90, 180, 365, 10000]
    low_bound = -1
    for i in range(len(segments)):
        high_bound = segments[i]
        if i + 1 < len(segments):
            key = f"between_{low_bound+1}_and_{high_bound}_days"
            count = sum(1 for d in data_nc.values() if low_bound < d[NEW_CODE_DAYS_KEY] <= high_bound)
        else:
            key = f"more_than_{low_bound}_days"
            count = sum(1 for d in data_nc.values() if low_bound < d[NEW_CODE_DAYS_KEY])
        summary_data[NEW_CODE_DAYS_KEY][key] = __count_percentage(count, nbr_projects)
        low_bound = high_bound
    low_bound = -0.001
    segments = [0.05, 0.1, 0.2, 0.4, 0.7, 1.0]
    for i in range(len(segments)):
        high_bound = segments[i]
        if i + 1 < len(segments):
            key = f"between_{int(low_bound*100)}_and_{int(high_bound*100)}_percent"
            count = sum(1 for d in data_nc.values() if d["lines"] != 0 and low_bound < d[NEW_CODE_LINES_KEY] / d["lines"] <= high_bound)
        else:
            key = f"more_than_{int(low_bound*100)}_percent"
            count = sum(1 for d in data_nc.values() if d["lines"] != 0 and low_bound < d[NEW_CODE_LINES_KEY] / d["lines"])
        summary_data[NEW_CODE_RATIO_KEY][key] = __count_percentage(count, nbr_projects)
        low_bound = high_bound

    return summary_data


def compute_analysis_frequency_statistics(data: dict[str, Any]) -> dict[str, Any]:
    """Computes the proportions of project that are analyzed more or less frequently"""
    DAYS = "7_days_or_less"
    return {
        "more_than_20_times_over_the_last_7_days": sum(1 for proj in data.values() if 20 <= proj[ANALYSES_ANY_BRANCH_KEY][DAYS]),
        "between_5_and_19_times_over_the_last_7_days": sum(1 for proj in data.values() if 5 <= proj[ANALYSES_ANY_BRANCH_KEY][DAYS] < 20),
        "between_1_and_4_times_over_the_last_7_days": sum(1 for proj in data.values() if 1 <= proj[ANALYSES_ANY_BRANCH_KEY][DAYS] < 5),
        "not_analyzed_over_the_last_7_days": sum(1 for proj in data.values() if proj[ANALYSES_ANY_BRANCH_KEY][DAYS] == 0),
    }


def write_results(filename: str, data: dict[str, Any]) -> None:
    """Writes results to a file"""
    with util.open_file(filename) as fd:
        print(util.json_dump(data), file=fd)
    log.info(f"Maturity report written to file '{filename}'")


def get_maturity_data(project_list: list[projects.Project], threads: int) -> dict[str, Any]:
    """Gets project maturity data in multithreaded way"""
    log.info("Collecting project maturity data on %d threads", threads)
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix="ProjMaturity") as executor:
        futures, futures_map = [], {}
        for proj in project_list:
            future = executor.submit(get_project_maturity_data, proj)
            futures.append(future)
            futures_map[future] = proj
        i, nb_projects = 0, len(project_list)
        maturity_data = {}
        for future in concurrent.futures.as_completed(futures):
            proj = futures_map[future]
            try:
                maturity_data[proj.key] = future.result(timeout=60)
            except TimeoutError as e:
                log.error(f"Getting maturity data for {str(proj)} timed out after 60 seconds for {str(future)}.")
            except Exception as e:
                traceback.print_exc()
                log.error(f"Exception {str(e)} when collecting maturity data of {str(proj)}.")
            i += 1
            if i % 10 == 0 or i == nb_projects:
                log.info("Collected maturity data for %d/%d projects (%d%%)", i, nb_projects, int(100 * i / nb_projects))
    return dict(sorted(maturity_data.items()))


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

        maturity_data = get_maturity_data(project_list, threads=kwargs[options.NBR_THREADS])

        summary_data: dict[str, Any] = {}
        summary_data["total_projects"] = len(maturity_data)
        summary_data["quality_gate_project_statistics"] = compute_summary_qg(maturity_data)
        summary_data["last_analysis_statistics"] = compute_summary_age(maturity_data)
        summary_data["quality_gate_enforcement_statistics"] = compute_pr_statistics(maturity_data)
        summary_data["new_code_statistics"] = compute_new_code_statistics(maturity_data)
        summary_data["frequency_statistics"] = compute_analysis_frequency_statistics(maturity_data)
        write_results(kwargs.get(options.REPORT_FILE), {"platform": sq.basics(), "summary": summary_data, "details": maturity_data})
    except exceptions.SonarException as e:
        chelp.clear_cache_and_exit(e.errcode, e.message)

    chelp.clear_cache_and_exit(0, start_time=start_time)
