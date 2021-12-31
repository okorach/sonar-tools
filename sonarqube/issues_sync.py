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
    parser.add_argument('--login', required=True, help='One (or several) comma separated services accounts used for issue-sync')
    parser.add_argument('--nocomment', required=False, default=False, action='store_true',
                        help='If specified, will not comment related to the sync in the target issue')
    # parser.add_argument('--noassign', required=False, default=False, action='store_true',
    #                    help="If specified, will not apply issue assignment in the target issue")
    parser.add_argument('--nolink', required=False, default=False, action='store_true',
                        help="If specified, will not add a link to source issue in the target issue comments")
    parser.add_argument('-f', '--file', required=False, help='Output file for the report, stdout by default')

    return util.parse_and_check_token(parser)


def __process_exact_sibling(issue, sibling, settings):
    if sibling.has_changelog():
        issue.apply_changelog(sibling, settings)
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


def __get_issues(issue_list):
    iss_list = []
    for issue in issue_list:
        iss_list.append({
            'source_issue_key': issue.key,
            'source_issue_url': issue.url()})
    return iss_list


def __process_multiple_exact_siblings(issue, siblings):
    util.logger.info('Multiple matches for issue key %s, cannot automatically apply changelog', str(issue))
    return {
        'target_issue_key': issue.id,
        'target_issue_url': issue.url(),
        'target_issue_status': 'unsynchronized',
        'message': 'Multiple matches',
        'matches': __get_issues(siblings)
    }


def __process_approx_siblings(issue, siblings):
    util.logger.info('Found %d approximate siblings for issue %s, cannot automatically apply changelog',
                     len(siblings), str(issue))
    return {
        'target_issue_key': issue.key,
        'target_issue_url': issue.url(),
        'target_issue_status': 'unsynchronized',
        'message': 'Approximate matches only',
        'matches': __get_issues(siblings)
    }


def __process_modified_siblings(issue, siblings):
    util.logger.info(
        'Found %d siblings for issue %s, but they already have a changelog, cannot automatically apply changelog',
        len(siblings), str(issue))
    return {
        'target_issue_key': issue.key,
        'target_issue_url': issue.url(),
        'target_issue_status': 'unsynchronized',
        'message': 'Target issue already has a changelog',
        'matches': __get_issues(siblings)
    }


def __process_no_match(issue):
    util.logger.info(
        'Found no match for issue %s', issue.url())
    return {
        'target_issue_key': issue.key,
        'target_issue_url': issue.url(),
        'target_issue_status': 'unsynchronized',
        'message': 'No match issue found in source',
        'matches': []
    }


def __dump_report(report, file):
    if file is None:
        f = sys.stdout
        util.logger.info("Dumping report to stdout")
    else:
        f = open(file, "w")
        util.logger.info("Dumping report to file '%s'", file)
    print(json.dumps(report, indent=4, sort_keys=False, separators=(',', ': ')), file=f)
    if file is not None:
        f.close()


def sync_issues_list(src_issues, tgt_issues, users, settings):
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
            src_issues, allowed_users=users, ignore_component=settings[issues.SYNC_IGNORE_COMPONENTS])
        if len(exact_siblings) == 1:
            report.append(__process_exact_sibling(issue, exact_siblings[0], settings))
            if exact_siblings[0].has_changelog():
                nb_applies += 1
            else:
                nb_no_changelog += 1
        elif len(exact_siblings) > 1:
            report.append(__process_multiple_exact_siblings(issue, exact_siblings))
            nb_multiple_matches += 1
        elif approx_siblings:
            report.append(__process_approx_siblings(issue, approx_siblings))
            nb_approx_match += 1
        elif modified_siblings:
            nb_modified_siblings += 1
            report.append(__process_modified_siblings(issue, modified_siblings))
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


def sync_branches(key1, endpoint1, users, key2=None, endpoint2=None, branch1=None, branch2=None, settings=None):
    util.logger.info("Synchronizing branch %s of project %s and branch %s of project %s", branch1, key1, branch2, key2)
    if key2 is None:
        key2 = key1
    if endpoint2 is None:
        endpoint2 = endpoint1
    src_issues = {}
    for key, issue in issues.search_by_project(key1, endpoint=endpoint1, branch=branch1).items():
        if not issue.has_changelog():
            continue
        src_issues[key] = issue
    util.logger.info("Found %d issues with manual changes on project %s branch %s", len(src_issues), key1, branch1)
    if len(src_issues) <= 0:
        util.logger.info("No issues with manual changes on project %s branch %s, skipping...", key1, branch1)
        return {}
    tgt_issues = issues.search_by_project(key2, endpoint=endpoint2, branch=branch2)
    util.logger.info("Found %d issues on project %s branch %s", len(tgt_issues), key2, branch2)
    settings[issues.SYNC_IGNORE_COMPONENTS] = (key1 != key2)
    return sync_issues_list(src_issues, tgt_issues, users, settings)


def sync_project_branches_between_platforms(source_key, target_key, users, settings, endpoint, target_endpoint):
    src_branches = projects.Project(key=source_key, endpoint=endpoint).get_branches()
    tgt_branches = projects.Project(key=target_key, endpoint=target_endpoint).get_branches()
    report = []
    for src_b in src_branches:
        for tgt_b in tgt_branches:
            if src_b.name != tgt_b.name:
                continue
            report += sync_branches(key1=source_key, key2=target_key, endpoint1=endpoint, endpoint2=target_endpoint,
                                    users=users, branch1=src_b.name, branch2=tgt_b.name, settings=settings)
    return report

def sync_all_project_branches(key, users, settings, endpoint):
    branches = projects.Project(key=key, endpoint=endpoint).get_branches()
    report = []
    for b1 in branches:
        for b2 in branches:
            if b1.name == b2.name:
                continue
            report += sync_branches(key1=key, endpoint1=endpoint, users=users, branch1=b1.name, branch2=b2.name,
                                    settings=settings)
    return report


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
    users = [x.strip() for x in args.login.split(',')]

    settings = {issues.SYNC_ADD_COMMENTS: not params['nocomment'],
                issues.SYNC_ADD_LINK: not params['nolink'],
                issues.SYNC_ASSIGN: True,
                issues.SYNC_IGNORE_COMPONENTS: False}
    report = []
    try:
        if not projects.exists(source_key, endpoint=source_env):
            raise env.NonExistingObjectError(source_key, f"Project key '{source_key}' does not exist")
        if target_url is None and target_key is None and source_branch is None and target_branch is None:
            # Sync all branches of a given project
            report = sync_all_project_branches(source_key, users, settings, source_env)
        elif target_url is None and target_key is None and source_branch is not None and target_branch is not None:
            # Sync 2 branches of a given project
            if source_branch != target_branch:
                report = sync_branches(key1=source_key, users=users, endpoint1=source_env, settings=settings,
                                       branch1=source_branch, branch2=target_branch)
            else:
                util.logger.critical("Can't sync same source and target branch or a same project, aborting...")

        elif target_url is None and target_key is not None:
            # sync 2 branches of 2 different projects
            if not projects.exists(target_key, endpoint=source_env):
                raise env.NonExistingObjectError(target_key, f"Project key '{target_key}' does not exist")
            src_issues = {}
            for key, issue in issues.search_by_project(source_key, endpoint=source_env, branch=source_branch).items():
                if issue.has_changelog():
                    src_issues[key] = issue
            util.logger.info("Found %d issues with manual changes on project %s branch %s",
                len(src_issues), source_key, source_branch)
            tgt_issues = issues.search_by_project(target_key, endpoint=source_env, branch=target_branch)
            util.logger.info("Found %d issues on project %s", len(tgt_issues), target_key)
            settings[issues.SYNC_IGNORE_COMPONENTS] = (target_key != source_key)
            report = sync_issues_list(src_issues, tgt_issues, users, settings)

        elif target_url is not None and target_key is not None:
            target_env = env.Environment(url=args.urlTarget, token=args.tokenTarget)
            if not projects.exists(target_key, endpoint=target_env):
                raise env.NonExistingObjectError(target_key, f"Project key '{target_key}' does not exist")
            src_issues = {}
            settings[issues.SYNC_IGNORE_COMPONENTS] = (target_key != source_key)
            if source_branch is not None or target_branch is not None:
                # sync main 2 branches of 2 projects on different platforms
                for key, issue in issues.search_by_project(source_key, endpoint=source_env, branch=source_branch).items():
                    if issue.has_changelog():
                        src_issues[key] = issue
                util.logger.info("Found %d issues with manual changes on project %s", len(src_issues), source_key)
                tgt_issues = issues.search_by_project(target_key, endpoint=target_env, branch=target_branch)
                util.logger.info("Found %d issues on project %s", len(tgt_issues), target_key)
                report = sync_issues_list(src_issues, tgt_issues, users, settings)
            else:
                # sync main all branches of 2 projects on different platforms
                report = sync_project_branches_between_platforms(source_key, target_key, users,
                    endpoint=source_env, target_endpoint=target_env, settings=settings)

        __dump_report(report, args.file)
    except env.NonExistingObjectError as e:
        util.logger.critical(e.message)
        sys.exit(1)


if __name__ == '__main__':
    main()
