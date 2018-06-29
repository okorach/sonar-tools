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
    parser.add_argument('-s', '--statuses', help='comma separated issue status', required=False)
    parser.add_argument('-a', '--createdAfter', help='issues created after a given date', required=False)
    parser.add_argument('-b', '--createdBefore', help='issues created before a given date', required=False)
    parser.add_argument('-p', '--p', help='page number', required=False)
    parser.add_argument('--ps', help='page size', required=False)
    parser.add_argument('-r', '--resolutions', help='Comma separated resolution state of the issues', required=False)
    parser.add_argument('--severities', help='Comma separated severities', required=False)
    parser.add_argument('--types', help='Comma separated issue types', required=False)
    parser.add_argument('--tags', help='Comma separated issue tags', required=False)

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

issue_slice = dict(page=0,pages=0,total=0,issues=None) 

page=1
nbr_pages=1
while page <= nbr_pages:
    issue_slice = sonarqube.issues.search(**parms)
    all_issues = issue_slice['issues']

    for issue in all_issues:
        print('----ISSUE' + '-' * 40)
        print(issue.to_string())

    page = issue_slice['page']
    nbr_pages = issue_slice['pages']
    print ("Total issues: ", issue_slice['total'])
    print ("Returned issues: ", len(all_issues))
    print ("Page: ", page)
    print ("Nbr pages: ", nbr_pages)
    page = page+1
    parms['p'] = page