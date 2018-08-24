#!/usr/local/bin/python
#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3

import json
import requests
import sonarqube.env
import sonarqube.issues
import sys

# Mandatory script input parameters
global project_key

global dry_run_mode
dry_run_mode = False

def print_object(o):
    print(json.dumps(o, indent=3, sort_keys=True))

def parse_args():
    parser = argparse.ArgumentParser(
            description='Search for unexpectedly closed issues and recover their history in a corresponding new issue.')
    sonarqube.env.add_standard_arguments(parser)
    parser.add_argument('-r', '--recover',
                        help='What information to recover. Default is FP and WF, but issue assignment, tags, severity and type change can be recovered too',
                        required=False)
    parser.add_argument('-d', '--dryrun',
                        help='If True, show changes but don\'t apply, if False, apply changes - Default is true',
                        required=False)
    args = parser.parse_args()

    return args

# ------------------------------------------------------------------------------

try:
    import argparse
except ImportError:
    if sys.version_info < (2, 7, 0):
        print("Error:")
        print("You are running an old version of python. Two options to fix the problem")
        print("  Option 1: Upgrade to python version >= 2.7")
        print("  Option 2: Install argparse library for the current python version")
        print("            See: https://pypi.python.org/pypi/argparse")

args = parse_args()
sqenv = sonarqube.env.Environment(url=args.url, token=args.token)
sonarqube.env.set_env(args.url, args.token)

# Remove unset params from the dict
noneparms = vars(args)
parms = dict()
for parm in noneparms:
    if noneparms[parm] is not None:
        parms[parm] = noneparms[parm]
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
search_parms['ps'] = 500
page=1
nbr_pages=1
closed_issues = []
while page <= nbr_pages:
    search_parms['p'] = page
    returned_data = sonarqube.issues.search(**search_parms)
    closed_issues = closed_issues + returned_data['issues']
    page = returned_data['page']
    nbr_pages = returned_data['pages']
    page = page+1
    search_parms['p'] = page
    print ("Number of closed issues: ", len(closed_issues))
print ("Total number of closed issues: ", len(closed_issues))



# Fetch all open issues
search_parms['statuses'] = 'OPEN,CONFIRMED,REOPENED,RESOLVED'
page=1
nbr_pages=1
non_closed_issues = []
while page <= nbr_pages:
    search_parms['p'] = page
    returned_data = sonarqube.issues.search(**search_parms)
    non_closed_issues = non_closed_issues + returned_data['issues']
    page = returned_data['page']
    nbr_pages = returned_data['pages']
    page = page+1
    search_parms['p'] = page
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
