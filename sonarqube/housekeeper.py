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
import sonarqube.audit_config as conf
from sonarqube import projects, users, env, version
from sonarqube.branches import Branch
from sonarqube.pull_requests import PullRequest
from sonarqube.user_tokens import UserToken
import sonarqube.utilities as util
import sonarqube.audit_problem as pb


def get_project_problems(max_days_proj, max_days_branch, max_days_pr, endpoint):
    problems = []
    if max_days_proj < 90:
        util.logger.error("As a safety measure, can't delete projects more recent than 90 days")
        return problems

    settings = {
        'audit.projects.maxLastAnalysisAge': max_days_proj,
        'audit.projects.branches.maxLastAnalysisAge': max_days_branch,
        'audit.projects.pullRequests.maxLastAnalysisAge': max_days_pr,
        'audit.projects.neverAnalyzed': False,
        'audit.projects.duplicates': False,
        'audit.projects.visibility': False,
        'audit.projects.permissions': False
    }
    settings = conf.load(config_name='sonar-audit', settings=settings)
    problems = projects.audit(endpoint=endpoint, audit_settings=settings)
    nb_proj = 0
    total_loc = 0
    for p in problems:
        if p.concerned_object is not None and isinstance(p.concerned_object, projects.Project):
            nb_proj += 1
            total_loc += int(p.concerned_object.get_measure('ncloc', fallback='0'))

    if nb_proj == 0:
        util.logger.info("%d projects older than %d days found during audit", nb_proj, max_days_proj)
    else:
        util.logger.warning("%d projects older than %d days for a total of %d LoC found during audit",
                            nb_proj, max_days_proj, total_loc)
    return problems

def get_user_problems(max_days, endpoint):
    settings = {
        'audit.tokens.maxAge': max_days,
        'audit.tokens.maxUnusedAge': 30,
    }
    settings = conf.load(config_name='sonar-audit', settings=settings)
    user_problems = users.audit(endpoint=endpoint, audit_settings=settings)
    nb_user_problems = len(user_problems)
    if nb_user_problems == 0:
        util.logger.info("%d user tokens older than %d days found during audit", nb_user_problems, max_days)
    else:
        util.logger.warning("%d user tokens older than %d days found during audit", nb_user_problems, max_days)
    return user_problems


def _parse_arguments():
    util.set_logger('sonar-housekeeper')
    parser = util.set_common_args('Deletes projects not analyzed since a given numbr of days')
    parser.add_argument('--mode', required=False, choices=['dry-run', 'delete'],
                        default='dry-run',
                        help='''
                        If 'dry-run', script only lists objects (projects, branches, PRs or tokens) to delete,
                        If 'delete' it deletes projects or tokens
                        ''')
    parser.add_argument('-P', '--projects', required=False, type=int, default=0,
        help='Deletes projects not analyzed since a given number of days')
    parser.add_argument('-B', '--branches', required=False, type=int, default=0,
        help='Deletes branches not to be kept and not analyzed since a given number of days')
    parser.add_argument('-R', '--pullrequests', required=False, type=int, default=0,
        help='Deletes pull requests not analyzed since a given number of days')
    parser.add_argument('-T', '--tokens', required=False, type=int, default=0,
        help='Deletes user tokens older than a certain number of days')
    return util.parse_and_check_token(parser)

def _delete_objects(problems):
    revoked_token_count = 0
    deleted_projects = {}
    deleted_branch_count = 0
    deleted_pr_count = 0
    deleted_loc = 0
    for p in problems:
        obj = p.concerned_object
        if obj is None:
            continue    # BUG
        if isinstance(obj, projects.Project):
            loc = int(obj.get_measure('ncloc', fallback='0'))
            util.logger.info("Deleting project '%s', %d LoC", obj.key, loc)
            if obj.delete():
                deleted_projects[obj.key] = obj
                deleted_loc += loc
        if isinstance(obj, Branch):
            if obj.project.key in deleted_projects:
                util.logger.info("Project '%s' deleted, so no need to delete its branch '%s'",
                    obj.project.key, obj.key)
            else:
                obj.delete()
                deleted_branch_count += 1
        if isinstance(obj, PullRequest):
            if obj.project.key in deleted_projects:
                util.logger.info("Project '%s' deleted, so no need to delete its PR '%s'",
                    obj.project.key, obj.key)
            else:
                obj.delete()
                deleted_pr_count += 1
        if isinstance(obj, UserToken) and obj.revoke():
            revoked_token_count += 1
    return (len(deleted_projects), deleted_loc, deleted_branch_count, deleted_pr_count, revoked_token_count)

def main():
    args = _parse_arguments()

    sq = env.Environment(url=args.url, token=args.token)
    kwargs = vars(args)
    mode = args.mode
    util.check_environment(kwargs)
    util.logger.debug("Args = %s", str(kwargs))
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)
    problems = []
    if args.projects > 0 or args.branches > 0 or args.pullrequests > 0:
        problems = get_project_problems(args.projects, args.branches, args.pullrequests, sq)

    if args.tokens:
        problems += get_user_problems(args.tokens, sq)

    pb.dump_report(problems, file=None, file_format='csv')

    if mode == 'dry-run':
        sys.exit(0)

    (deleted_proj, deleted_loc, deleted_branches, deleted_prs, revoked_tokens) = _delete_objects(problems)
    util.logger.info("%d projects and %d LoCs deleted", deleted_proj, deleted_loc)
    util.logger.info("%d branches deleted", deleted_branches)
    util.logger.info("%d pull requests deleted", deleted_prs)
    util.logger.info("%d tokens revoked", revoked_tokens)
    sys.exit(len(problems))

if __name__ == "__main__":
    main()
