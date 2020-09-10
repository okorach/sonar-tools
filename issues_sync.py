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
    This script propagates the manual issue changes (FP, WF, Change
    of severity, of issue type, comments) from:
    - One project to another (normally on different platforms but not necessarily)
    - One branch of a project to another branch of the same project (normally LLBs)

    Only issues with a 100% match are propagates. When there's a doubt, nothing is done
'''


import sys
import json
import sonarqube.env as env
import sonarqube.issues as issues
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
    return parser.parse_args()


args = parse_args('Replicates issue history between 2 same projects on 2 SonarQube platforms or 2 branches')
source_env = env.Environment(url=args.url, token=args.token)
if args.urlTarget is None:
    args.urlTarget = args.url
if args.tokenTarget is None:
    args.tokenTarget = args.token

if (args.sourceBranch is None and args.targetBranch is not None or
        args.sourceBranch is not None and args.targetBranch is None):
    util.logger.error("Both source and target branches should be specified, aborting")
    sys.exit(2)

target_env = env.Environment(url=args.urlTarget, token=args.tokenTarget)

params = vars(args)
util.check_environment(params)
for key in params.copy():
    if params[key] is None:
        del params[key]
params['projectKey'] = params['componentKeys']
targetParams = params.copy()
if 'targetComponentKeys' in targetParams and targetParams['targetComponentKeys'] is not None:
    targetParams['projectKey'] = targetParams['targetComponentKeys']
    targetParams['componentKeys'] = targetParams['targetComponentKeys']
# Add SQ environment

if 'sourceBranch' in params and params['sourceBranch'] is not None:
    params['branch'] = params['sourceBranch']
params.pop('sourceBranch', 0)
if 'targetBranch' in params and params['targetBranch'] is not None:
    targetParams['branch'] = params['targetBranch']
params.pop('targetBranch', 0)

all_source_issues = issues.search(endpoint=source_env, params=params)
util.logger.info("Found %d issues with manual changes on source project", len(all_source_issues))

all_target_issues = issues.search(endpoint=target_env, params=targetParams)
util.logger.info("Found %d target issues on target project & branch", len(all_target_issues))

ignore_component = targetParams['projectKey'] != params['projectKey']
nb_applies = 0
nb_approx_match = 0
report = []

for issue_key, issue in all_target_issues.items():
    util.logger.debug('Searching sibling for issue %s', str(issue))
    util.logger.info('Searching sibling for issue %s', issue.get_url())
    (exact_siblings, approx_siblings, modified_siblings) = issue.search_siblings(
        all_source_issues, ignore_component=ignore_component)
    nb_exact_siblings = len(exact_siblings)
    nb_approx_siblings = len(approx_siblings)
    nb_modified_siblings = len(modified_siblings)
    util.logger.info('Found %d exact sibling(s) for issue %s', nb_exact_siblings, str(issue))
    if nb_exact_siblings == 1:
        if exact_siblings[0].has_changelog():
            issues.apply_changelog(issue, exact_siblings[0])
            msg = 'Source issue changelog applied successfully'
        else:
            msg = 'Source issue has no changelog'
        report.append({
            'target_issue_key': issue.id,
            'target_issue_url': issue.get_url(),
            'target_issue_status': 'synchronized',
            'message': msg,
            'source_issue_key': exact_siblings[0].id,
            'source_issue_url': exact_siblings[0].get_url()
            })
        nb_applies += 1
        continue
    if nb_exact_siblings > 1:
        util.logger.info('Ambiguity for issue key %s, cannot automatically apply changelog', str(issue))
        issue_list = []
        for sibling in exact_siblings:
            issue_list.append({
                'source_issue_key': sibling.id,
                'source_issue_url': sibling.get_url()})
        report.append({
            'target_issue_key': issue.id,
            'target_issue_url': issue.get_url(),
            'target_issue_status': 'unsynchronized',
            'message': 'Multiple matches',
            'matches': issue_list
        })
        continue
    if nb_approx_siblings > 0:
        util.logger.info('Found %d approximate siblings for issue %s, cannot automatically apply changelog',
                         nb_approx_siblings, str(issue))
        issue_list = []
        for sibling in approx_siblings:
            issue_list.append({
                'source_issue_key': sibling.id,
                'source_issue_url': sibling.get_url()})
        report.append({
            'target_issue_key': issue.id,
            'target_issue_url': issue.get_url(),
            'target_issue_status': 'unsynchronized',
            'message': 'Approximate matches only',
            'matches': issue_list
        })
        if nb_approx_siblings == 1:
            nb_approx_match += 1
    elif nb_modified_siblings > 0:
        util.logger.info('Found %d modified siblings for issue %s, cannot automatically apply changelog',
                         nb_approx_siblings, str(issue))
        issue_list = []
        for sibling in modified_siblings:
            issue_list.append({
                'source_issue_key': sibling.id,
                'source_issue_url': sibling.get_url()})
        report.append({
            'target_issue_key': issue.id,
            'target_issue_url': issue.get_url(),
            'target_issue_status': 'unsynchronized',
            'message': 'Target issue already has a changelog',
            'matches': issue_list
        })

print(json.dumps(report,indent=4, sort_keys=False, separators=(',', ': ')))
util.logger.info("Synchronized %d issues", nb_applies)
util.logger.info("%d issues that were only approximately matching were left unchange", nb_approx_match)