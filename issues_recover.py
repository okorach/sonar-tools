#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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
    This script restores issues that may have been closed mistakenly after,
    for instance, a scan with improper settings

    Usage: issuerecoverer.py -r -t <SQ_TOKEN> -u <SQ_URL>
'''

import sonar.env
import sonar.issues
import sonar.utilities as utils


def parse_args(desc):
    parser = utils.set_common_args(desc)
    parser = utils.set_project_args(parser)
    parser.add_argument('-r', '--recover', required=False,
                        help='''What information to recover. Default is FP and WF, but issue assignment,
                        tags, severity and type change can be recovered too''')
    parser.add_argument('-d', '--dryrun', required=False,
                        help='If True, show changes but don\'t apply, if False, apply changes - Default is true')
    return utils.parse_and_check_token(parser)


args = parse_args('Search for unexpectedly closed issues and recover their history in a corresponding new issue.')
sqenv = sonar.env.Environment(some_url=args.url, some_token=args.token)

# Remove unset params from the dict
params = vars(args)
for key in params.copy():
    if params[key] is None:
        del params[key]
# Add SQ environment
params.update({'env': sqenv})

# Fetch all closed issues
search_params = params
search_params['ps'] = 500
search_params['statuses'] = 'CLOSED'
closed_issues = sonar.issues.search_all(endpoint=sqenv, params=search_params)
print("Total number of closed issues: ", len(closed_issues))

# Fetch all open issues
search_params['statuses'] = 'OPEN,CONFIRMED,REOPENED,RESOLVED'
non_closed_issues = sonar.issues.search(**search_params)
print("Number of open issues: ", len(non_closed_issues))

# Search for mistakenly closed issues
mistakenly_closed_issues = []
for issue in closed_issues:
    if issue.has_been_marked_as_wont_fix() or issue.has_been_marked_as_false_positive():
        print("Mistakenly closed: " + issue.to_string())
        mistakenly_closed_issues.append(issue)

print("Number of mistakenly closed issues: ", len(mistakenly_closed_issues))

for issue in mistakenly_closed_issues:
    print('Searching sibling for issue key: ', issue.id)
    (siblings, approx_siblings, modified_siblings) = issue.search_siblings(non_closed_issues)
    nb_siblings = len(siblings)
    if nb_siblings == 1:
        print('   Automatically applying changelog')
        siblings[0].apply_changelog(issue)
    elif nb_siblings > 1:
        print('   Ambiguity for issue, cannot automatically apply changelog, candidate issue keys below')
        for sibling in siblings:
            print(sibling.id + ', ')
