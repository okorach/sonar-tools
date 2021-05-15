#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2020 Olivier Korach
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

    Removes obsolete data from SonarQube platform
    Currently only projects not analyzed since a given number of days

'''
import sys
import sonarqube.env as env
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.version as version
import sonarqube.audit_problem as pb


def main():
    util.set_logger('sonar-housekeeper')
    parser = util.set_common_args('Deletes projects not analyzed since a given numbr of days')
    parser.add_argument('--mode', required=False, choices=['dry-run', 'delete'],
                        default='dry-run',
                        help="If 'dry-run', script only lists projects to delete, if 'delete' it deletes projects")
    parser.add_argument('-o', '--olderThan', required=True, type=int,
                        help='Number of days since last analysis to delete file')
    args = util.parse_and_check_token(parser)
    sq = env.Environment(url=args.url, token=args.token)
    kwargs = vars(args)
    mode = args.mode
    util.check_environment(kwargs)
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)
    if args.olderThan < 90:
        util.logger.error("Can't delete projects more recent than 90 days")
        sys.exit(1)

    settings = {
        'audit.projects.maxLastAnalysisAge': args.olderThan,
        'audit.projects.neverAnalyzed': False,
        'audit.projects.duplicates': False,
        'audit.projects.visibility': False,
        'audit.projects.permissions': False,
        'audit.projects.lastAnalysisDate': True
    }
    problems = projects.audit(endpoint=sq, audit_settings=settings)

    if not problems:
        util.logger.info("%d projects older than %d days found during audit", len(problems), args.olderThan)
        sys.exit(0)

    pb.dump_report(problems, file=None, file_format='csv')
    total_loc = 0
    nb_proj = 0
    for p in problems:
        if p.concerned_object is not None and isinstance(p.concerned_object, projects.Project):
            loc = int(p.concerned_object.get_measure('ncloc', fallback='0'))
            total_loc += loc
            nb_proj += 1
    util.logger.warning("%d projects older than %d days for a total of %d LoC found during audit",
                        nb_proj, args.olderThan, total_loc)
    if mode == 'dry-run':
        sys.exit(0)

    for p in problems:
        if p.concerned_object is not None and isinstance(p.concerned_object, projects.Project):
            util.logger.info("Deleting project '%s', %d LoC", p.concerned_object.key, loc)
            p.concerned_object.delete()
    util.logger.info("%d projects and %d LoCs deleted", nb_proj, total_loc)
    sys.exit(len(problems))


if __name__ == "__main__":
    main()
