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
        "qualityGateStatus": project.get_measure("alert_status"),
        "ncloc": project.get_measure("ncloc"),
        "lines": project.get_measure("lines"),
        "new_lines": project.get_measure("new_lines"),
        "lastAnalysis": util.age(project.last_analysis(include_branches=True)),
        "mainBranchLastAnalysis": util.age(project.main_branch().last_analysis()),
    }
    if data["qualityGateStatus"] is None and data["lines"] is None:
        data["qualityGateStatus"] = "NONE/NEVER_ANALYZED"
    return data


def compute_summary_age(data: dict[str, Any]) -> dict[str, Any]:
    """Computes statistics on last analysis"""
    nbr_projects = len(data)
    summary_data = {"any_branch": {"never_analyzed": sum(1 for d in data.values() if d["lines"] is None)}, "main_branch": {}}
    segments = [1, 3, 7, 15, 30, 90, 180, 365, 10000]
    low_bound = -1
    for high_bound in segments:
        key = f"between_{low_bound+1}_and_{high_bound}_days"
        count = sum(1 for d in data.values() if d["lines"] is not None and low_bound < d["lastAnalysis"] <= high_bound)
        summary_data["any_branch"][key] = {"count": count, "percentage": float(f"{count/nbr_projects:.3f}")}
        count = sum(1 for d in data.values() if d["lines"] is not None and low_bound < d["mainBranchLastAnalysis"] <= high_bound)
        summary_data["main_branch"][key] = {"count": count, "percentage": float(f"{count/nbr_projects:.3f}")}
        low_bound = high_bound
    return summary_data


def compute_summary_qg(data: dict[str, Any]) -> dict[str, Any]:
    """Computes statistics on quality gate statuses"""
    nbr_projects = len(data)
    summary_data = {}
    possible_status = {d["qualityGateStatus"] for d in data.values()}
    for status in possible_status:
        count = sum(1 for d in data.values() if d["qualityGateStatus"] == status)
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
        maturity_data = {project.key: get_maturity_data(project) for project in project_list}
        summary_data: dict[str, Any] = {}
        summary_data["total_projects"] = len(maturity_data)
        summary_data["quality_gate_statuses"] = compute_summary_qg(maturity_data)
        summary_data["last_analysis"] = compute_summary_age(maturity_data)
        write_results(kwargs.get(options.REPORT_FILE), {"summary": summary_data, "details": maturity_data})
    except exceptions.SonarException as e:
        chelp.clear_cache_and_exit(e.errcode, e.message)

    chelp.clear_cache_and_exit(0, start_time=start_time)
