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


def __dump_loc(projects, file, file_format, **kwargs):
    if file is None:
        fd = sys.stdout
        util.logger.info("Dumping LoC report to stdout")
    else:
        fd = open(file, "w", encoding='utf-8')
        util.logger.info("Dumping LoC report to file '%s'", file)
    sep = ','

    print("# Project Key", end='', file=fd)
    if kwargs['projectName']:
        print(f"{sep}Project Name", end='', file=fd)
    print(f"{sep}LoC", end='', file=fd)
    if kwargs['lastAnalysis']:
        print(f"{sep}Last Analysis", end='', file=fd)
    print('', file=fd)
    nb_loc = 0
    nb_projects = 0
    for _, p in projects.items():
        project_loc = p.ncloc(include_branches=True)
        print(f"{p.key}", end='', file=fd)
        if kwargs['projectName']:
            print(f"{sep}{p.name}", end='', file=fd)
        print(f"{sep}{project_loc}", end='', file=fd)
        if kwargs['lastAnalysis']:
            print(f"{sep}{p.last_analysis_date(include_branches=True)}", end='', file=fd)
        print('', file=fd)
        nb_loc += project_loc
        nb_projects += 1
        if nb_projects % 50 == 0:
            util.logger.info("%d PROJECTS and %d LoCs, still counting...", nb_projects, nb_loc)
    if file is not None:
        fd.close()
    util.logger.info("%d PROJECTS and %d LoCs", len(projects), nb_loc)


def main():
    parser = util.set_common_args('Extract projects lines of code, as computed for the licence')
    parser = util.set_component_args(parser)
    parser.add_argument('-n', '--projectName', required=False, default=False, action='store_true',
                        help='Also list the project name on top of the project key')
    parser.add_argument('-a', '--lastAnalysis', required=False, default=False, action='store_true',
                        help='Also list the last analysis date on top of nbr of LoC')
    parser.add_argument('-o', '--outputFile', required=False, help='File to generate the report, default is stdout'
                        'Format is automatically deducted from file extension, if extension given')
    parser.add_argument('-f', '--format', required=False, default='csv',
                        help='Format of output (json, csv), default is csv')
    args = util.parse_and_check_token(parser)
    endpoint = env.Environment(url=args.url, token=args.token)
    util.check_environment(vars(args))
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)

    # Mandatory script input parameters



    project_list = projects.search(endpoint=endpoint)
    __dump_loc(project_list, args.outputFile, args.format, **vars(args))
    sys.exit(0)


if __name__ == '__main__':
    main()
