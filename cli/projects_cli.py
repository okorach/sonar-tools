#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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

    Exports all projects of a SonarQube platform

"""

import sys
import json

from cli import options
import sonar.logging as log
from sonar import errcodes, exceptions, utilities, version
from sonar import platform, projects

TOOL_NAME = "sonar-projects"


def __export_projects(endpoint: platform.Platform, **kwargs) -> None:
    """Exports a list (or all) of projects into zip files"""
    ed = endpoint.edition()
    if ed == "sonarcloud":
        utilities.exit_fatal("Can't export projects on SonarCloud, aborting...", errcodes.UNSUPPORTED_OPERATION)
    if ed in ("community", "developer") and endpoint.version()[:2] < (9, 2):
        utilities.exit_fatal(f"Can't export projects on {ed} Edition before 9.2, aborting...", errcodes.UNSUPPORTED_OPERATION)
    try:
        dump = projects.export_zip(
            endpoint=endpoint, key_list=kwargs[options.KEYS], export_timeout=kwargs["exportTimeout"], threads=kwargs[options.NBR_THREADS]
        )
    except exceptions.ObjectNotFound:
        sys.exit(errcodes.NO_SUCH_KEY)

    try:
        with utilities.open_file(kwargs[options.REPORT_FILE]) as fd:
            print(utilities.json_dump(dump), file=fd)
    except (PermissionError, FileNotFoundError) as e:
        utilities.exit_fatal(f"OS error while projects export file: {e}", exit_code=errcodes.OS_ERROR)


def __check_sq_environments(import_sq: platform.Platform, export_sq: dict[str, str]) -> None:
    """Checks if export and import environments are compatibles"""
    imp_version = import_sq.version(digits=2, as_string=True)
    if imp_version != export_sq["version"]:
        utilities.exit_fatal("Export was not performed with same SonarQube version, aborting...", errcodes.UNSUPPORTED_OPERATION)
    for export_plugin in export_sq["plugins"]:
        e_name = export_plugin["name"]
        e_vers = export_plugin["version"]
        found = False
        for import_plugin in import_sq.plugins():
            if import_plugin["name"] == e_name and import_plugin["version"] == e_vers:
                found = True
                break
        if not found:
            utilities.exit_fatal(
                f"Plugin '{e_name}' version '{e_vers}' was not found or not in same version on import platform, aborting...",
                errcodes.UNSUPPORTED_OPERATION,
            )


def __import_projects(endpoint: platform.Platform, **kwargs) -> None:
    """Imports a list of projects in SonarQube EE+"""
    file = kwargs[options.REPORT_FILE]
    if not file:
        utilities.exit_fatal(f"Option --{options.REPORT_FILE} is mandatory to import", exit_code=errcodes.ARGS_ERROR)

    try:
        with open(file, "r", encoding="utf-8") as fd:
            data = json.load(fd)
    except (FileNotFoundError, PermissionError) as e:
        utilities.exit_fatal(f"OS error while reading file '{file}': {e}", exit_code=errcodes.OS_ERROR)
    except json.JSONDecodeError as e:
        utilities.exit_fatal(f"JSON decoding error while reading file '{file}': {e}", exit_code=errcodes.OS_ERROR)
    project_list = data["project_exports"]
    __check_sq_environments(endpoint, data["sonarqube_environment"])

    nb_projects = len(project_list)
    log.info("%d projects to import", nb_projects)
    i = 0
    statuses = {}
    for project in project_list:
        try:
            o_proj = projects.Project.create(key=project["key"], endpoint=endpoint, name=project["key"])
            status = o_proj.import_zip()
            s = f"IMPORT {status}"
        except exceptions.ObjectAlreadyExists:
            s = "CREATE projectAlreadyExist"
        if s in statuses:
            statuses[s] += 1
        else:
            statuses[s] = 1
        i += 1
        log.info("%d/%d exports (%d%%) - Latest: %s - %s", i, nb_projects, int(i * 100 / nb_projects), project["key"], status)
        log.info("%s", ", ".join([f"{k}:{v}" for k, v in statuses.items()]))


def main() -> None:
    """Main entry point of sonar-projects"""
    start_time = utilities.start_clock()
    parser = options.set_common_args("Exports all projects of a SonarQube platform")
    parser = options.set_key_arg(parser)
    parser = options.add_import_export_arg(parser, "projects zip")
    parser = options.set_output_file_args(parser, allowed_formats=("json",))
    parser = options.add_thread_arg(parser, "projects zip export")
    parser.add_argument(
        "--exportTimeout",
        required=False,
        type=int,
        default=180,
        help="Maximum wait time for export of 1 project",
    )
    try:
        kwargs = utilities.convert_args(options.parse_and_check(parser=parser, logger_name=TOOL_NAME))
        sq = platform.Platform(**kwargs)
        sq.verify_connection()
        sq.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")
    except (options.ArgumentsError, exceptions.ObjectNotFound) as e:
        utilities.exit_fatal(e.message, e.errcode)

    if kwargs[options.EXPORT]:
        __export_projects(sq, **kwargs)
    elif kwargs[options.IMPORT]:
        __import_projects(sq, **kwargs)
    else:
        utilities.exit_fatal(f"One of --{options.EXPORT} or --{options.IMPORT} option must be chosen", exit_code=errcodes.ARGS_ERROR)

    utilities.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
