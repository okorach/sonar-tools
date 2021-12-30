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
    This script propagates the manual issue changes (FP, WF, Change
    of severity, of issue type, comments) from:
    - One project to another (normally on different platforms but not necessarily)
    - One branch of a project to another branch of the same project (normally LLBs)

    Only issues with a 100% match are propagates. When there's a doubt, nothing is done
'''


import sys
import json
from sonarqube import env, issues, projects, version
import sonarqube.utilities as util


def __parse_args(desc):
    parser = util.set_common_args(desc)
    parser = util.set_component_args(parser)
    parser = util.set_target_args(parser)
    parser.add_argument('-r', '--recover', required=False,
                        help='''What information to replicate. Default is FP and WF, but issue assignment,
                        tags, severity and type change can be recovered too''')
    parser.add_argument('-b', '--sourceBranch', required=False, help='Name of the source branch')
    parser.add_argument('-B', '--targetBranch', required=False, help='Name of the target branch')
    parser.add_argument('-K', '--targetComponentKeys', required=False,
                        help='''key of the target project when synchronizing 2 projects
                        or 2 branches on a same platform''')
    parser.add_argument('--users', required=True, help='List of services users used for issue-sync')
    parser.add_argument('-f', '--file', required=False, help='Output file for the report, stdout by default')

    return util.parse_and_check_token(parser)


def __process_arguments(params):
    src_params = {'componentKeys': params['componentKeys']}
    if 'sourceBranch' in params and params['sourceBranch'] is not None:
        src_params['branch'] = params['sourceBranch']

    tgt_params = {'componentKeys': params['componentKeys']}
    if 'targetComponentKeys' in params and params['targetComponentKeys'] is not None:
        tgt_params = {'componentKeys': params['targetComponentKeys']}
    if 'targetBranch' in params and params['targetBranch'] is not None:
        tgt_params['branch'] = params['targetBranch']
    return (src_params, tgt_params)


def __process_exact_sibling__(issue, sibling):
    if sibling.has_changelog():
        issue.apply_changelog(sibling)
        msg = 'Source issue changelog applied successfully'
    else:
        msg = 'Source issue has no changelog'
    return {
        'target_issue_key': issue.key,
        'target_issue_url': issue.url(),
        'target_issue_status': 'synchronized',
        'message': msg,
        'source_issue_key': sibling.key,
        'source_issue_url': sibling.url()
    }


def __get_issues__(issue_list):
    iss_list = []
    for issue in issue_list:
        iss_list.append({
            'source_issue_key': issue.key,
            'source_issue_url': issue.url()})
    return iss_list


def __process_multiple_exact_siblings__(issue, siblings):
    util.logger.info('Multiple matches for issue key %s, cannot automatically apply changelog', str(issue))
    return {
        'target_issue_key': issue.id,
        'target_issue_url': issue.url(),
        'target_issue_status': 'unsynchronized',
        'message': 'Multiple matches',
        'matches': __get_issues__(siblings)
    }


def __process_approx_siblings__(issue, siblings):
    util.logger.info('Found %d approximate siblings for issue %s, cannot automatically apply changelog',
                     len(siblings), str(issue))
    return {
        'target_issue_key': issue.key,
        'target_issue_url': issue.url(),
        'target_issue_status': 'unsynchronized',
        'message': 'Approximate matches only',
        'matches': __get_issues__(siblings)
    }


def __process_modified_siblings__(issue, siblings):
    util.logger.info(
        'Found %d siblings for issue %s, but they already have a changelog, cannot automatically apply changelog',
        len(siblings), str(issue))
    return {
        'target_issue_key': issue.key,
        'target_issue_url': issue.url(),
        'target_issue_status': 'unsynchronized',
        'message': 'Target issue already has a changelog',
        'matches': __get_issues__(siblings)
    }


def __process_no_match__(issue):
    util.logger.info(
        'Found no match for issue %s', issue.url())
    return {
        'target_issue_key': issue.key,
        'target_issue_url': issue.url(),
        'target_issue_status': 'unsynchronized',
        'message': 'No match issue found in source',
        'matches': []
    }


def _dump_report_(report, file):
    if file is None:
        f = sys.stdout
        util.logger.info("Dumping report to stdout")
    else:
        f = open(file, "w")
        util.logger.info("Dumping report to file '%s'", file)
    print(json.dumps(report, indent=4, sort_keys=False, separators=(',', ': ')), file=f)
    if file is not None:
        f.close()


def sync_issues_list(src_issues, tgt_issues, users, ignore_component=False):
    nb_applies = 0
    nb_approx_match = 0
    nb_modified_siblings = 0
    nb_multiple_matches = 0
    nb_no_match = 0
    nb_no_changelog = 0
    report = []

    for _, issue in tgt_issues.items():
        util.logger.debug('Searching sibling for issue %s', str(issue))
        (exact_siblings, approx_siblings, modified_siblings) = issue.search_siblings(
            src_issues, allowed_users=users, ignore_component=ignore_component)
        if len(exact_siblings) == 1:
            report.append(__process_exact_sibling__(issue, exact_siblings[0]))
            if exact_siblings[0].has_changelog():
                nb_applies += 1
            else:
                nb_no_changelog += 1
        elif len(exact_siblings) > 1:
            report.append(__process_multiple_exact_siblings__(issue, exact_siblings))
            nb_multiple_matches += 1
        elif approx_siblings:
            report.append(__process_approx_siblings__(issue, approx_siblings))
            nb_approx_match += 1
        elif modified_siblings:
            nb_modified_siblings += 1
            report.append(__process_modified_siblings__(issue, modified_siblings))
        elif not exact_siblings and not approx_siblings and not modified_siblings:
            nb_no_match += 1

    util.logger.info("%d issues to sync in target, %d issues in source", len(tgt_issues), len(src_issues))
    util.logger.info("%d issues were already in sync since source had no changelog", nb_no_changelog)
    util.logger.info("%d issues were synchronized successfully", nb_applies)
    util.logger.info("%d issues could not be synchronized because no match was found in source", nb_no_match)
    util.logger.info("%d issues could not be synchronized because there were multiple matches", nb_multiple_matches)
    util.logger.info("%d issues could not be synchronized because the match was approximate", nb_approx_match)
    util.logger.info("%d issues could not be synchronized because target issue already had a changelog",
                     nb_modified_siblings)
    return report

def sync_project_branches(project_key, src_branch, tgt_branch, users, endpoint):
    src_issues = {}
    for key, issue in issues.search_by_project(project_key, branch=src_branch, endpoint=endpoint).items():
        if issue.has_changelog() and len(issue.modifiers_excluding_service_users(users)) > 0:
            src_issues[key] = issue
    util.logger.info("Found %d issues with manual changes on project %s branch %s",
        len(src_issues), project_key, src_branch)
    tgt_issues = issues.search_by_project(project_key, branch=tgt_branch, endpoint=endpoint)
    util.logger.info("Found %d issues with manual changes on project %s target branch %s",
        len(tgt_issues), project_key, tgt_branch)
    return sync_issues_list(src_issues, tgt_issues, users)


def main():
    args = __parse_args('Replicates issue history between 2 same projects on 2 SonarQube platforms or 2 branches')
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)
    source_env = env.Environment(url=args.url, token=args.token)
    params = vars(args)
    util.check_environment(params)
    source_key = params['componentKeys']
    target_key = params.get('targetComponentKeys', None)
    source_branch = params.get('sourceBranch', None)
    target_branch = params.get('targetBranch', None)
    target_url = params.get('urlTarget', None)
    users = [x.strip() for x in args.users.split(',')]

    for opt in ('url', 'token', 'urlTarget', 'tokenTarget'):
        params.pop(opt, None)
    (src_params, tgt_params) = __process_arguments(params)
    report = []
    if target_url is None and target_key is None and source_branch is None and target_branch is None:
        # Sync all branches of a given project
        branches = projects.Project(key=source_key, endpoint=source_env).get_branches()
        for b1 in branches:
            for b2 in branches:
                report += sync_project_branches(source_key, b1.name, b2.name, users, endpoint=source_env)

    elif target_url is None and target_key is None and source_branch is not None and target_branch is not None:
        # Sync 2 branches of a given project
        report = sync_project_branches(source_key, source_branch, target_branch, users, endpoint=source_env)

    elif target_url is None and target_key is not None:
        # sync main branch of 2 projects
        src_issues = {}
        for key, issue in issues.search_by_project(source_key, endpoint=source_env, params=None).items():
            if issue.has_changelog():
                src_issues[key] = issue
        util.logger.info("Found %d issues with manual changes on project %s branch %s",
            len(src_issues), source_key, source_branch)
        tgt_issues = issues.search_by_project(target_key, endpoint=source_env, params=tgt_params)
        util.logger.info("Found %d issues with manual changes on project %s branch %s",
            len(tgt_issues), target_key, target_branch)
        report = sync_issues_list(src_issues, tgt_issues, users, ignore_component=(target_key != source_key))

    elif target_url is not None and target_key is not None:
        # sync main branch of 2 projects on different platforms
        target_env = env.Environment(url=args.urlTarget, token=args.tokenTarget)
        src_issues = {}
        for key, issue in issues.search_by_project(source_key, endpoint=source_env, params=None).items():
            if issue.has_changelog():
                src_issues[key] = issue
        util.logger.info("Found %d issues with manual changes on project %s branch %s",
            len(src_issues), source_key, source_branch)

        tgt_issues = issues.search_by_project(target_key, endpoint=target_env, params=None)
        util.logger.info("Found %d issues with manual changes on project %s branch %s",
            len(tgt_issues), target_key, target_branch)
        report = sync_issues_list(src_issues, tgt_issues, users, ignore_component=(target_key != source_key))

    _dump_report_(report, args.file)


if __name__ == '__main__':
    main()
