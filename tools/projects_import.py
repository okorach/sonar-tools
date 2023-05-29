#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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

    Imports a list of projects to a SonarQube platform

"""
import sys
import json
from sonar import options, platform, version, exceptions
from sonar.projects import projects
import sonar.utilities as util


def _check_sq_environments(import_sq, export_sq):
    imp_version = import_sq.version(digits=2, as_string=True)
    if imp_version != export_sq["version"]:
        util.exit_fatal(
            "Export was not performed with same SonarQube version, aborting...",
            options.ERR_UNSUPPORTED_OPERATION,
        )
    for export_plugin in export_sq["plugins"]:
        e_name = export_plugin["name"]
        e_vers = export_plugin["version"]
        found = False
        for import_plugin in import_sq.plugins():
            if import_plugin["name"] == e_name and import_plugin["version"] == e_vers:
                found = True
                break
        if not found:
            util.exit_fatal(
                f"Plugin '{e_name}' version '{e_vers}' was not found or not in same version on import platform, aborting...",
                options.ERR_UNSUPPORTED_OPERATION,
            )


def main():
    parser = util.set_common_args("Imports a list of projects in a SonarQube platform")
    parser.add_argument("-f", "--projectsFile", required=True, help="File with the list of projects")
    args = util.parse_and_check_token(parser)
    util.check_environment(vars(args))
    util.check_token(args.token)
    util.logger.info("sonar-tools version %s", version.PACKAGE_VERSION)
    sq = platform.Platform(some_url=args.url, some_token=args.token, cert_file=args.clientCert)

    with open(args.projectsFile, "r", encoding="utf-8") as file:
        data = json.load(file)
    project_list = data["project_exports"]
    _check_sq_environments(sq, data["sonarqube_environment"])

    nb_projects = len(project_list)
    util.logger.info("%d projects to import", nb_projects)
    i = 0
    statuses = {}
    for project in project_list:
        try:
            o_proj = projects.Project.create(key=project["key"], endpoint=sq, name=project["key"])
            status = o_proj.import_zip()
            s = f"IMPORT {status}"
            if s in statuses:
                statuses[s] += 1
            else:
                statuses[s] = 1
        except exceptions.ObjectAlreadyExists:
            s = "CREATE projectAlreadyExist"
            if s in statuses:
                statuses[s] += 1
            else:
                statuses[s] = 1
        i += 1
        util.logger.info(
            "%d/%d exports (%d%%) - Latest: %s - %s",
            i,
            nb_projects,
            int(i * 100 / nb_projects),
            project["key"],
            status,
        )
        summary = ""
        for k, v in statuses.items():
            summary += f"{k}:{v}, "
        util.logger.info("%s", summary[:-2])
    sys.exit(0)


if __name__ == "__main__":
    main()
