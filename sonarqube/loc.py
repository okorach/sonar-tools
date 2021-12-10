#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2021 Olivier Korach
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
    Exports LoC per projects
'''
import sys
from sonarqube import projects, env, version
import sonarqube.utilities as util


def main():
    parser = util.set_common_args('Extract projects lines of code, as computed for the licence')
    parser = util.set_component_args(parser)
    parser.add_argument('-n', '--projectName', required=False, default=False, action='store_true',
                        help='Also list the project name on top of the project key')
    parser.add_argument('-a', '--lastAnalysis', required=False, default=False, action='store_true',
                        help='Also list the last analysis date on top of nbr of LoC')
    args = util.parse_and_check_token(parser)
    endpoint = env.Environment(url=args.url, token=args.token)
    util.check_environment(vars(args))
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)

    # Mandatory script input parameters
    sep = ","
    print("# Project Key", end='')
    if args.projectName:
        print(f"{sep}Project Name", end='')
    print(f"{sep}LoC", end='')
    if args.lastAnalysis:
        print(f"{sep}Last Analysis", end='')
    print('')

    project_list = projects.search(endpoint=endpoint)
    nb_loc = 0
    for _, p in project_list.items():
        project_loc = p.ncloc(include_branches=True)
        print(f"{p.key}", end='')
        if args.projectName:
            print(f"{sep}{p.name}", end='')
        print(f"{sep}{project_loc}", end='')
        if args.lastAnalysis:
            print(f"{sep}{p.last_analysis_date(include_branches=True)}", end='')
        print('')
        nb_loc += project_loc
    util.logger.info("%d PROJECTS and %d LoCs", len(project_list), nb_loc)
    sys.exit(0)


if __name__ == '__main__':
    main()
