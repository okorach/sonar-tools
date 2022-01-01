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

SRC_KEY = 'sourceIssueKey'
SRC_URL = 'sourceIssueUrl'
SYNC_MSG = 'syncMessage'
SYNC_MATCHES = 'matches'
TGT_KEY = 'targetIssueKey'
TGT_URL = 'targetIssueUrl'
TGT_STATUS = 'targetIssueStatus'

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
    parser.add_argument('--login', required=True,
                        help='One (or several) comma separated services accounts used for issue-sync')
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
        TGT_KEY: issue.key,
        TGT_URL: issue.url(),
        TGT_STATUS: 'synchronized',
        SYNC_MSG: msg,
        SRC_KEY: sibling.key,
        SRC_URL: sibling.url()
    }


def __get_issues(issue_list):
    iss_list = []
    for issue in issue_list:
        iss_list.append({SRC_KEY: issue.key, SRC_URL: issue.url()})
    return iss_list


def __process_multiple_exact_siblings(issue, siblings):
    util.logger.info('Multiple matches for issue key %s, cannot automatically apply changelog', str(issue))
    return {
        TGT_KEY: issue.id,
        TGT_URL: issue.url(),
        TGT_STATUS: 'unsynchronized',
        SYNC_MSG: 'Multiple matches',
        SYNC_MATCHES: __get_issues(siblings)
    }


def __process_approx_siblings(issue, siblings):
    util.logger.info('Found %d approximate siblings for issue %s, cannot automatically apply changelog',
                     len(siblings), str(issue))
    return {
        TGT_KEY: issue.key,
        TGT_URL: issue.url(),
        TGT_STATUS: 'unsynchronized',
        SYNC_MSG: 'Approximate matches only',
        SYNC_MATCHES: __get_issues(siblings)
    }


def __process_modified_siblings(issue, siblings):
    util.logger.info(
        'Found %d siblings for issue %s, but they already have a changelog, cannot automatically apply changelog',
        len(siblings), str(issue))
    return {
        TGT_KEY: issue.key,
        TGT_URL: issue.url(),
        TGT_STATUS: 'unsynchronized',
        SYNC_MSG: 'Target issue already has a changelog',
        SYNC_MATCHES: __get_issues(siblings)
    }


def __process_no_match(issue):
    util.logger.info(
        'Found no match for issue %s', issue.url())
    return {
        TGT_KEY: issue.key,
        TGT_URL: issue.url(),
        TGT_STATUS: 'unsynchronized',
        SYNC_MSG: 'No match issue found in source',
        SYNC_MATCHES: []
    }


def __dump_report(report, file):
    txt = json.dumps(report, indent=3, sort_keys=False, separators=(',', ': '))
    if file is None:
        util.logger.info("Dumping report to stdout")
        print(txt)
    else:
        util.logger.info("Dumping report to file '%s'", file)
        with open(file, "w", encoding='utf-8') as fh:
            print(txt, file=fh)

def sync_issues_list(src_issues, tgt_issues, settings):
    counters = {'nb_applies': 0, 'nb_approx_match': 0, 'nb_modified_siblings': 0,
                'nb_multiple_matches': 0, 'nb_no_match': 0, 'nb_no_changelog': 0}
    report = []

    util.logger.info("%d issues to sync in target, %d issues in source", len(tgt_issues), len(src_issues))
    for _, issue in tgt_issues.items():
        util.logger.debug('Searching sibling for issue %s', str(issue))
        (exact_siblings, approx_siblings, modified_siblings) = issue.search_siblings(
            src_issues, allowed_users=settings[issues.SYNC_SERVICE_ACCOUNTS],
            ignore_component=settings[issues.SYNC_IGNORE_COMPONENTS])
        if len(exact_siblings) == 1:
            report.append(__process_exact_sibling(issue, exact_siblings[0], settings))
            if exact_siblings[0].has_changelog():
                counters['nb_applies'] += 1
            else:
                counters['nb_no_changelog'] += 1
        elif len(exact_siblings) > 1:
            report.append(__process_multiple_exact_siblings(issue, exact_siblings))
            counters['nb_multiple_matches'] += 1
        elif approx_siblings:
            report.append(__process_approx_siblings(issue, approx_siblings))
            counters['nb_approx_match'] += 1
        elif modified_siblings:
            counters['nb_modified_siblings'] += 1
            report.append(__process_modified_siblings(issue, modified_siblings))
        elif not exact_siblings and not approx_siblings and not modified_siblings:
            counters['nb_no_match'] += 1

    return (report, counters)


def sync_branches(key1, endpoint1, settings, key2=None, endpoint2=None, branch1=None, branch2=None):
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
    return sync_issues_list(src_issues, tgt_issues, settings)


def __add_counters(counts, tmp_counts):
    for k in tmp_counts:
        if k not in counts:
            counts[k] = 0
        counts[k] += tmp_counts[k]
    return counts


def sync_project_branches_between_platforms(source_key, target_key, settings, endpoint, target_endpoint):
    src_branches = projects.Project(key=source_key, endpoint=endpoint).get_branches()
    tgt_branches = projects.Project(key=target_key, endpoint=target_endpoint).get_branches()
    report = []
    counters = {}
    for src_b in src_branches:
        for tgt_b in tgt_branches:
            if src_b.name != tgt_b.name:
                continue
            (tmp_report, tmp_counts) = sync_branches(
                key1=source_key, key2=target_key, endpoint1=endpoint, endpoint2=target_endpoint,
                branch1=src_b.name, branch2=tgt_b.name, settings=settings)
            report += tmp_report
            counters = __add_counters(counters, tmp_counts)
    return (report, counters)


def sync_all_project_branches(key, settings, endpoint):
    branches = projects.Project(key=key, endpoint=endpoint).get_branches()
    report = []
    counters = {}
    for b1 in branches:
        for b2 in branches:
            if b1.name == b2.name:
                continue
            (tmp_report, tmp_counts) = sync_branches(
                key1=key, endpoint1=endpoint, branch1=b1.name, branch2=b2.name, settings=settings)
            report += tmp_report
            counters = __add_counters(counters, tmp_counts)
    return (report, counters)


def main():
    args = __parse_args('Replicates issue history between 2 same projects on 2 SonarQube platforms or 2 branches')
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)
    source_env = env.Environment(some_url=args.url, some_token=args.token)
    params = vars(args)
    util.check_environment(params)
    source_key = params['componentKeys']
    target_key = params.get('targetComponentKeys', None)
    source_branch = params.get('sourceBranch', None)
    target_branch = params.get('targetBranch', None)
    target_url = params.get('urlTarget', None)

    settings = {issues.SYNC_ADD_COMMENTS: not params['nocomment'],
                issues.SYNC_ADD_LINK: not params['nolink'],
                issues.SYNC_ASSIGN: True,
                issues.SYNC_IGNORE_COMPONENTS: False,
                issues.SYNC_SERVICE_ACCOUNTS: [x.strip() for x in args.login.split(',')]}
    report = []
    try:
        if not projects.exists(source_key, endpoint=source_env):
            raise env.NonExistingObjectError(source_key, f"Project key '{source_key}' does not exist")
        if target_url is None and target_key is None and source_branch is None and target_branch is None:
            # Sync all branches of a given project
            (report, counters) = sync_all_project_branches(source_key, settings, source_env)
        elif target_url is None and target_key is None and source_branch is not None and target_branch is not None:
            # Sync 2 branches of a given project
            if source_branch != target_branch:
                (report, counters) = sync_branches(key1=source_key, endpoint1=source_env, settings=settings,
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
            (report, counters) = sync_issues_list(src_issues, tgt_issues, settings)

        elif target_url is not None and target_key is not None:
            target_env = env.Environment(some_url=args.urlTarget, some_token=args.tokenTarget)
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
                (report, counters) = sync_issues_list(src_issues, tgt_issues, settings)
            else:
                # sync main all branches of 2 projects on different platforms
                (report, counters) = sync_project_branches_between_platforms(source_key, target_key,
                    endpoint=source_env, target_endpoint=target_env, settings=settings)

        __dump_report(report, args.file)
        util.logger.info("%d issues were already in sync since source had no changelog",
                         counters.get('nb_no_changelog', 0))
        util.logger.info("%d issues were synchronized successfully", counters.get('nb_applies', 0))
        util.logger.info("%d issues could not be synchronized because no match was found in source",
                         counters.get('nb_no_match', 0))
        util.logger.info("%d issues could not be synchronized because there were multiple matches",
                         counters.get('nb_multiple_matches', 0))
        util.logger.info("%d issues could not be synchronized because the match was approximate",
                         counters.get('nb_approx_match', 0))
        util.logger.info("%d issues could not be synchronized because target issue already had a changelog",
                        counters.get('nb_modified_siblings', 0))

    except env.NonExistingObjectError as e:
        util.logger.critical(e.message)
        sys.exit(1)


if __name__ == '__main__':
    main()
