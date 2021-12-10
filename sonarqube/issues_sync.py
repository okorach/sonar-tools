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
from sonarqube import env, issues, version
import sonarqube.utilities as util


def parse_args(desc):
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
    parser.add_argument('-f', '--file', required=False, help='Output file for the report, stdout by default')

    return util.parse_and_check_token(parser)


def __process_arguments__(params):
    for key in params.copy():
        if params[key] is None:
            del params[key]
    params['projectKey'] = params['componentKeys']
    tgt_params = params.copy()
    if 'targetComponentKeys' in tgt_params and tgt_params['targetComponentKeys'] is not None:
        tgt_params['projectKey'] = tgt_params['targetComponentKeys']
        tgt_params['componentKeys'] = tgt_params['targetComponentKeys']
    # Add SQ environment

    if 'sourceBranch' in params and params['sourceBranch'] is not None:
        params['branch'] = params['sourceBranch']
    params.pop('sourceBranch', 0)
    if 'targetBranch' in params and params['targetBranch'] is not None:
        tgt_params['branch'] = params['targetBranch']
    params.pop('targetBranch', 0)
    return (params, tgt_params)


def __process_exact_sibling__(issue, sibling):
    if sibling.has_changelog():
        issue.apply_changelog(sibling)
        msg = 'Source issue changelog applied successfully'
    else:
        msg = 'Source issue has no changelog'
    return {
        'target_issue_key': issue.key,
        'target_issue_url': issue.get_url(),
        'target_issue_status': 'synchronized',
        'message': msg,
        'source_issue_key': sibling.key,
        'source_issue_url': sibling.get_url()
    }


def __get_issues__(issue_list):
    iss_list = []
    for issue in issue_list:
        iss_list.append({
            'source_issue_key': issue.key,
            'source_issue_url': issue.get_url()})
    return iss_list


def __process_multiple_exact_siblings__(issue, siblings):
    util.logger.info('Multiple matches for issue key %s, cannot automatically apply changelog', str(issue))
    return {
        'target_issue_key': issue.id,
        'target_issue_url': issue.get_url(),
        'target_issue_status': 'unsynchronized',
        'message': 'Multiple matches',
        'matches': __get_issues__(siblings)
    }


def __process_approx_siblings__(issue, siblings):
    util.logger.info('Found %d approximate siblings for issue %s, cannot automatically apply changelog',
                     len(siblings), str(issue))
    return {
        'target_issue_key': issue.key,
        'target_issue_url': issue.get_url(),
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
        'target_issue_url': issue.get_url(),
        'target_issue_status': 'unsynchronized',
        'message': 'Target issue already has a changelog',
        'matches': __get_issues__(siblings)
    }


def __process_no_match__(issue):
    util.logger.info(
        'Found no match for issue %s', issue.get_url())
    return {
        'target_issue_key': issue.key,
        'target_issue_url': issue.get_url(),
        'target_issue_status': 'unsynchronized',
        'message': 'No match issue found in source',
        'matches': []
    }


def __verify_branch_params__(src_branch, tgt_branch):
    if (src_branch is None and tgt_branch is not None or src_branch is not None and tgt_branch is None):
        util.logger.error("Both source and target branches should be specified, aborting")
        sys.exit(2)


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


def main():
    args = parse_args('Replicates issue history between 2 same projects on 2 SonarQube platforms or 2 branches')
    source_env = env.Environment(url=args.url, token=args.token)

    params = vars(args)
    util.check_environment(params)
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)

    __verify_branch_params__(args.sourceBranch, args.targetBranch)

    if args.urlTarget is None:
        args.urlTarget = args.url
    if args.tokenTarget is None:
        args.tokenTarget = args.token
    util.logger.debug("Target = %s@%s", args.tokenTarget, args.urlTarget)
    target_env = env.Environment(url=args.urlTarget, token=args.tokenTarget)

    (params, tgt_params) = __process_arguments__(params)

    all_source_issues = issues.search_by_project(params['projectKey'], endpoint=source_env, params=params)
    manual_source_issues = {}
    for key, issue in all_source_issues.items():
        if issue.has_changelog():
            manual_source_issues[key] = issue
    all_source_issues = manual_source_issues

    util.logger.info("Found %d issues with manual changes on project %s branch %s",
        len(all_source_issues), params['projectKey'], params['branch'])

    all_target_issues = issues.search_by_project(params['projectKey'], endpoint=target_env, params=tgt_params)
    util.logger.info("Found %d target issues on target project/branch", len(all_target_issues))

    ignore_component = tgt_params['projectKey'] != params['projectKey']
    nb_applies = 0
    nb_approx_match = 0
    nb_modified_siblings = 0
    nb_multiple_matches = 0
    nb_no_match = 0
    nb_no_changelog = 0
    report = []

    for _, issue in all_target_issues.items():
        util.logger.debug('Searching sibling for issue %s', str(issue))
        (exact_siblings, approx_siblings, modified_siblings) = issue.search_siblings(
            all_source_issues, ignore_component=ignore_component)
        if len(exact_siblings) == 1:
            report.append(__process_exact_sibling__(issue, exact_siblings[0]))
            if exact_siblings[0].has_changelog():
                nb_applies += 1
            else:
                nb_no_changelog += 1
            continue
        if len(exact_siblings) > 1:
            report.append(__process_multiple_exact_siblings__(issue, exact_siblings))
            nb_multiple_matches += 1
            continue
        if approx_siblings:
            report.append(__process_approx_siblings__(issue, approx_siblings))
            nb_approx_match += 1
            continue
        if modified_siblings:
            nb_modified_siblings += 1
            report.append(__process_modified_siblings__(issue, modified_siblings))
            continue
        if not exact_siblings and not approx_siblings and not modified_siblings:
            nb_no_match += 1
            # report.append(__process_no_match__(issue))

    _dump_report_(report, args.file)
    util.logger.info("%d issues to sync in target, %d issues in source", len(all_target_issues), len(all_source_issues))
    util.logger.info("%d issues were already in sync since source had no changelog", nb_no_changelog)
    util.logger.info("%d issues were synchronized successfully", nb_applies)
    util.logger.info("%d issues could not be synchronized because no match was found in source", nb_no_match)
    util.logger.info("%d issues could not be synchronized because there were multiple matches", nb_multiple_matches)
    util.logger.info("%d issues could not be synchronized because the match was approximate", nb_approx_match)
    util.logger.info("%d issues could not be synchronized because target issue already had a changelog",
                     nb_modified_siblings)


if __name__ == '__main__':
    main()
