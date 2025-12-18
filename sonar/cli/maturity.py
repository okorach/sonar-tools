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

from sonar import utilities as util
from sonar import version
from cli import options
from sonar import exceptions
from sonar import platform
from sonar.util import common_helper as chelp
from sonar.util import component_helper
from sonar import errcodes
from sonar import projects

TOOL_NAME = "sonar-maturity"


def __parse_args(desc: str) -> object:
    """Set and parses CLI arguments"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("json", "csv"))
    parser = options.add_component_type_arg(parser)
    args = options.parse_and_check(parser=parser, logger_name=TOOL_NAME)

    return args


def get_maturity_data(project: projects.Project) -> dict:
    """Gets the maturity data for a project"""
    data = {
        "key": project.key,
        "qualityGateStatus": project.get_measure("alert_status"),
        "ncloc": project.get_measure("ncloc"),
        "lines": project.get_measure("lines"),
        "new_lines": project.get_measure("new_lines"),
    }
    if data["qualityGateStatus"] is None and data["lines"] is None:
        data["qualityGateStatus"] = "NONE/NEVER_ANALYZED"
    return data


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
        # print(util.json_dump(maturity_data))
        for key, data in maturity_data.items():
            print(f"{key}: {','.join([str(v) for v in data.values()])}")
        possible_status = {d["qualityGateStatus"] for d in maturity_data.values()}
        percents = {status: sum(1 for d in maturity_data.values() if d["qualityGateStatus"] == status) for status in possible_status}
        for status, count in percents.items():
            print(f"{status}: {count} ({count * 100/len(maturity_data):.1f}%)")
    except exceptions.SonarException as e:
        chelp.clear_cache_and_exit(e.errcode, e.message)

    chelp.clear_cache_and_exit(0, start_time=start_time)
