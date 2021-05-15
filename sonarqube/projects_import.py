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
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.env as env


def main():
    parser = util.set_common_args('Imports a list of projects in a SonarQube platform')
    parser.add_argument('-f', '--projectsFile', required=True, help='File with the list of projects')

    args = util.parse_and_check_token(parser)
    myenv = env.Environment(url=args.url, token=args.token)
    util.check_environment(vars(args))

    f = open(args.projectsFile, "r")
    project_list = []
    for line in f:
        (key, status, _) = line.split(',', 2)
        if status is None or status != 'FAIL':
            project_list.append(key)
    f.close()

    nb_projects = len(project_list)
    util.logger.info("%d projects to import", nb_projects)
    i = 0
    statuses = {}
    for key in project_list:
        status = projects.create_project(key=key, sqenv=myenv)
        if status != 200:
            s = "CREATE {0}".format(status)
            if s in statuses:
                statuses[s] += 1
            else:
                statuses[s] = 1
        else:
            status = projects.Project(key, endpoint=myenv).importproject()
            s = "IMPORT {0}".format(status)
            if s in statuses:
                statuses[s] += 1
            else:
                statuses[s] = 1
        i += 1
        util.logger.info("%d/%d exports (%d%%) - Latest: %s - %s", i, nb_projects,
                         int(i * 100 / nb_projects), key, status)
        summary = ''
        for s in statuses:
            summary += "{0}:{1}, ".format(s, statuses[s])
        util.logger.info("%s", summary)
    sys.exit(0)


if __name__ == "__main__":
    main()
