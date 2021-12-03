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
from sonarqube import projects, env
import sonarqube.utilities as util


def main():
    parser = util.set_common_args('Extract projects lines of code, as computed for the licence')
    parser = util.set_component_args(parser)
    args = util.parse_and_check_token(parser)
    endpoint = env.Environment(url=args.url, token=args.token)
    util.check_environment(vars(args))

    # Mandatory script input parameters
    sep = ","
    print("Project Key{0}Project Name{0}LoC{0}Last Analysis".format(sep))

    project_list = projects.search(endpoint=endpoint)
    nb_loc = 0
    for _, p in project_list.items():
        project_loc = p.ncloc(include_branches=True)
        print(f"{p.key}{sep}{p.name}{sep}{project_loc}{sep}{p.last_analysis_date(include_branches=True)}")
        nb_loc += project_loc
    util.logger.info("%d PROJECTS and %d LoCs", len(project_list), nb_loc)
    sys.exit(0)


if __name__ == '__main__':
    main()
