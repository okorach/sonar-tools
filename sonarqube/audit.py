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

    Audits a SonarQube platform

'''
import sys
import sonarqube.projects as projects
import sonarqube.qualityprofiles as qualityprofiles
import sonarqube.qualitygates as qualitygates
import sonarqube.users as users
import sonarqube.utilities as util
import sonarqube.version as version
import sonarqube.env as env
import sonarqube.audit_problem as pb
import sonarqube.audit_config as conf


def __deduct_format__(fmt, file):
    if fmt is not None:
        return fmt
    if file is not None:
        ext = file.split('.').pop(-1).lower()
        if ext == 'csv' or ext == 'json':
            return ext
    return 'csv'


def main():
    util.set_logger('sonar-audit')
    parser = util.set_common_args('Deletes projects not analyzed since a given numbr of days')
    parser.add_argument('-w', '--what', required=False,
                        help='What to audit (qp,qg,settings,projects) comma separated, everything by default')
    parser.add_argument('--format', choices=['csv', 'json'], required=False,
                        help='''Output format for audit report
If not specified, it is the output file extension if json or csv, then csv by default''')
    parser.add_argument('-f', '--file', required=False, help='Output file for the report, stdout by default')
    args = util.parse_and_check_token(parser)

    sq = env.Environment(url=args.url, token=args.token)
    kwargs = vars(args)
    util.check_environment(kwargs)
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)
    settings = conf.load('sonar-audit.properties')

    if args.what is None:
        args.what = 'qp,qg,settings,projects,users'
    what_to_audit = args.what.split(',')

    problems = []
    if 'projects' in what_to_audit:
        problems += projects.audit(endpoint=sq, audit_settings=settings)
    if 'qp' in what_to_audit:
        problems += qualityprofiles.audit(endpoint=sq)
    if 'qg' in what_to_audit:
        problems += qualitygates.audit(endpoint=sq)
    if 'settings' in what_to_audit:
        problems += sq.audit(audit_settings=settings)
    if 'users' in what_to_audit:
        problems += users.audit(endpoint=sq, audit_settings=settings)

    args.format = __deduct_format__(args.format, args.file)
    pb.dump_report(problems, args.file, args.format)

    if problems:
        util.logger.warning("%d issues found during audit", len(problems))
    else:
        util.logger.info("%d issues found during audit", len(problems))
    sys.exit(len(problems))


if __name__ == "__main__":
    main()
