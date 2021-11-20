#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2021 Olivier Korach
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
'''

    Imports a list of projects to a SonarQube platform

'''
import sys
import json
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.env as env

def _check_sq_environments(import_sq, export_sq):
    version = import_sq.version(digits=2, as_string=True)
    if version != export_sq['version']:
        util.logger.error("Export was not performed with same SonarQube version, aborting...")
        print("Export was not performed with same SonarQube version, aborting...")
        sys.exit(1)
    for export_plugin in export_sq['plugins']:
        e_name = export_plugin['name']
        e_vers = export_plugin['version']
        found = False
        for import_plugin in import_sq.plugins():
            if import_plugin['name'] == e_name and import_plugin['version'] == e_vers:
                found = True
                break
        if not found:
            util.logger.critical(
                'Plugin %s version %s was not found or not in same version on import platform, aborting...',
                e_name, e_vers)
            print(f'Plugin {e_name} version {e_vers} was not found or not in same version on import platform, aborting...')
            sys.exit(2)

def main():
    parser = util.set_common_args('Imports a list of projects in a SonarQube platform')
    parser.add_argument('-f', '--projectsFile', required=True, help='File with the list of projects')

    args = util.parse_and_check_token(parser)
    sq = env.Environment(url=args.url, token=args.token)
    util.check_environment(vars(args))

    with open(args.projectsFile, "r", encoding='utf-8') as file:
        data = json.load(file)
    project_list = data['project_exports']
    _check_sq_environments(sq, data['sonarqube_environment'])

    nb_projects = len(project_list)
    util.logger.info("%d projects to import", nb_projects)
    i = 0
    statuses = {}
    for project in project_list:
        status = projects.create_project(key=project['key'], sqenv=sq)
        if status != 200:
            s = f"CREATE {status}"
            if s in statuses:
                statuses[s] += 1
            else:
                statuses[s] = 1
        else:
            status = projects.Project(project['key'], endpoint=sq).importproject()
            s = f"IMPORT {status}"
            if s in statuses:
                statuses[s] += 1
            else:
                statuses[s] = 1
        i += 1
        util.logger.info("%d/%d exports (%d%%) - Latest: %s - %s", i, nb_projects,
                         int(i * 100 / nb_projects), project['key'], status)
        summary = ''
        for s in statuses:
            summary += "{0}:{1}, ".format(s, statuses[s])
        util.logger.info("%s", summary)
    sys.exit(0)


if __name__ == "__main__":
    main()
