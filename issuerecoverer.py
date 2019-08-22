#!/usr/local/bin/python

import sys
import json
import requests
import sonarqube.env
import sonarqube.issues
import sonarqube.utilities as utils

# Mandatory script input parameters
global project_key

global dry_run_mode
dry_run_mode = False

def print_object(o):
    print(json.dumps(o, indent=3, sort_keys=True))

def parse_args(desc):
    parser = utils.set_common_args(desc)
    parser.add_argument('-r', '--recover', required=False,
                        help='''What information to recover. Default is FP and WF, but issue assignment,
                        tags, severity and type change can be recovered too''')
    parser.add_argument('-d', '--dryrun', required=False,
                        help='If True, show changes but don\'t apply, if False, apply changes - Default is true')
    return parser.parse_args()

# ------------------------------------------------------------------------------

args = parse_args('Search for unexpectedly closed issues and recover their history in a corresponding new issue.')
sqenv = sonarqube.env.Environment(url=args.url, token=args.token)
sonarqube.env.set_env(args.url, args.token)

# Remove unset params from the dict
tmpparms = vars(args)
parms = tmpparms.copy()
for key in tmpparms:
    if parms[key] is None:
        del parms[key]
# Add SQ environment
parms.update(dict(env=sqenv))

for parm in parms:
    print(parm, '->', parms[parm])

returned_data = dict()

search_parms = parms
search_parms['ps'] = 500

# Fetch all closed issues
search_parms = parms
search_parms['statuses'] = 'CLOSED'
closed_issues = sonarqube.issues.search_all_issues(**search_parms)
print ("Total number of closed issues: ", len(closed_issues))

# Fetch all open issues
search_parms['statuses'] = 'OPEN,CONFIRMED,REOPENED,RESOLVED'
non_closed_issues = sonarqube.issues.search(**search_parms)
print ("Number of open issues: ", len(non_closed_issues))

# Search for mistakenly closed issues
mistakenly_closed_issues = []
for issue in closed_issues:
    if issue.was_fp_or_wf():
        print("Mistakenly closed: " + issue.to_string())
        mistakenly_closed_issues.append(issue)

print ("Number of mistakenly closed issues: ", len(mistakenly_closed_issues))

for issue in mistakenly_closed_issues:
    print('Searching sibling for issue key: ', issue.id)
    siblings = sonarqube.issues.search_siblings(issue, non_closed_issues, False)
    nb_siblings = len(siblings)
    print ("Number of siblings: ", nb_siblings)
    if nb_siblings == 1:
        print('   Automatically applying changelog')
        sonarqube.issues.apply_changelog(siblings[0], issue, True)
    elif nb_siblings > 1:
        print('   Ambiguity for issue, cannot automatically apply changelog, candidate issue keys below')
        for sibling in siblings:
            print(sibling.id + ', ')
