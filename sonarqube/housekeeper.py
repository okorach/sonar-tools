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

    Removes obsolete data from SonarQube platform
    Currently only projects not analyzed since a given number of days

'''
import sys
import sonarqube.env as env
import sonarqube.projects as projects
import sonarqube.users as users
import sonarqube.user_tokens as utokens
import sonarqube.utilities as util
import sonarqube.version as version
import sonarqube.audit_problem as pb


def get_project_problems(max_days, endpoint):
    problems = []
    if max_days < 90:
        util.logger.error("Can't delete projects more recent than 90 days")
        return problems

    settings = {
        'audit.projects.maxLastAnalysisAge': max_days,
        'audit.projects.neverAnalyzed': False,
        'audit.projects.duplicates': False,
        'audit.projects.visibility': False,
        'audit.projects.permissions': False,
        'audit.projects.lastAnalysisDate': True
    }
    problems = projects.audit(endpoint=endpoint, audit_settings=settings)
    nb_proj = len(problems)
    if nb_proj == 0:
        util.logger.info("%d projects older than %d days found during audit", nb_proj, max_days)
    else:
        total_loc = 0
        for p in problems:
            if p.concerned_object is not None and isinstance(p.concerned_object, projects.Project):
                loc = int(p.concerned_object.get_measure('ncloc', fallback='0'))
                total_loc += loc
        util.logger.warning("%d projects older than %d days for a total of %d LoC found during audit",
                            nb_proj, max_days, total_loc)
    return problems

def get_user_problems(max_days, endpoint):
    settings = {
        'audit.tokens.maxAge': max_days,
        'audit.tokens.unusedAge': 30,
    }
    user_problems = users.audit(endpoint=endpoint, audit_settings=settings)
    nb_user_problems = len(user_problems)
    if nb_user_problems == 0:
        util.logger.info("%d user tokens older than %d days found during audit", nb_user_problems, max_days)
    else:
        util.logger.warning("%d user tokens older than %d days found during audit", nb_user_problems, max_days)
    return user_problems

def main():
    util.set_logger('sonar-housekeeper')
    parser = util.set_common_args('Deletes projects not analyzed since a given numbr of days')
    parser.add_argument('--mode', required=False, choices=['dry-run', 'delete'],
                        default='dry-run',
                        help='''
                        If 'dry-run', script only lists objects (projects or tokens) to delete,
                        If 'delete' it deletes projects or tokens
                        ''')
    parser.add_argument('-P', '--projects', required=False, help='Deletes projects', action='store_true')
    parser.add_argument('-T', '--tokens', required=False, help='Deletes user tokens', action='store_true')
    parser.add_argument('-o', '--olderThan', required=True, type=int,
                        help='Number of days since last analysis to delete file')
    args = util.parse_and_check_token(parser)
    sq = env.Environment(url=args.url, token=args.token)
    kwargs = vars(args)
    mode = args.mode
    max_days = args.olderThan
    util.check_environment(kwargs)
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)
    problems = []
    if args.projects:
        problems = get_project_problems(max_days, sq)

    if args.tokens:
        problems += get_user_problems(max_days, sq)

    pb.dump_report(problems, file=None, file_format='csv')

    if mode == 'dry-run':
        sys.exit(0)

    revoked_token_count = 0
    deleted_project_count = 0
    deleted_loc = 0
    for p in problems:
        if p.concerned_object is None:
            continue    # BUG
        if isinstance(p.concerned_object, projects.Project):
            loc = int(p.concerned_object.get_measure('ncloc', fallback='0'))
            util.logger.info("Deleting project '%s', %d LoC", p.concerned_object.key, loc)
            p.concerned_object.delete()
            deleted_project_count += 1
            deleted_loc += loc
        if isinstance(p.concerned_object, utokens.UserToken):
            util.logger.info("Revoking token '%s' of user login '%s'", str(p.concerned_object), p.concerned_object.login)
            p.concerned_object.revoke()
            revoked_token_count += 1
    util.logger.info("%d projects and %d LoCs deleted", deleted_project_count, deleted_loc)
    util.logger.info("%d tokens revoked", revoked_token_count)
    sys.exit(len(problems))

if __name__ == "__main__":
    main()
