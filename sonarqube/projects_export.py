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

    Exports all projects of a SonarQube platform

'''
import sys
import os
import json
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.env as env


def main():
    parser = util.set_common_args('Exports all projects of a SonarQube platform')
    parser.add_argument('--exportTimeout', required=False, type=int, default=180, help='Maximum wait time for export')

    args = util.parse_and_check_token(parser)
    util.check_environment(vars(args))

    sq = env.Environment(url=args.url, token=args.token)
    project_list = projects.search(endpoint=sq)
    nb_projects = len(project_list)
    util.logger.info("%d projects to export", nb_projects)
    i = 0
    statuses = {}
    exports = []

    for key, p in project_list.items():
        dump = p.export(timeout=args.exportTimeout)
        status = dump['status']
        if status in statuses:
            statuses[status] += 1
        else:
            statuses[status] = 1

        data = {'key': key, 'status': status}
        if status == 'SUCCESS':
            #print(f"{key},SUCCESS,{os.path.basename(dump['file'])}")
            data['file'] = os.path.basename(dump['file'])
            data['path'] = dump['file']
        #else:
            #print(f"{key},FAIL,{status}")

        exports.append(data)
        util.logger.info("%d/%d exports (%d%%) - Latest: %s - %s", len(exports), nb_projects,
                         int(len(exports) * 100 / nb_projects), key, status)

        summary = ''
        for s in statuses:
            summary += f"{s}:{statuses[s]}, "
        util.logger.info("%s", summary)

    print(json.dumps({
        'sonarqube_environment': {
            'version': '.'.join([str(n) for n in sq.get_version()]),
            'plugins': sq.get_sysinfo()['Statistics']['plugins'],
        },
        'project_exports': exports}, sort_keys=True, indent=3, separators=(',', ': ')))
    util.logger.info("%s", summary)
    sys.exit(0)


if __name__ == "__main__":
    main()
