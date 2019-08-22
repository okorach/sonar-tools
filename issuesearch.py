#!/usr/local/bin/python
#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3

import json
import requests
import sonarqube.env as env
import sonarqube.issues as issues
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
    env.add_standard_arguments(parser)
    parser.add_argument('-s', '--statuses', help='comma separated issue status', required=False)
    parser.add_argument('-a', '--createdAfter', help='issues created after a given date', required=False)
    parser.add_argument('-b', '--createdBefore', help='issues created before a given date', required=False)
    #parser.add_argument('-p', '--projectKey', help='projectKey', required=False)
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
sqenv = env.Environment(url=args.url, token=args.token)
sqenv.set_env(args.url, args.token)

# Remove unset params from the dict
noneparms = vars(args)
parms = dict()
for parm in noneparms:
    if noneparms[parm] is not None:
        parms[parm] = noneparms[parm]
# Add SQ environment
parms.update(dict(env=sqenv))

for parm in parms:
    env.debug(parm, '->', parms[parm])

all_issues = issues.search_all_issues_unlimited(**parms)
print(issues.to_csv_header())
for issue in all_issues:
    print(issue.to_csv())
env.debug ("Returned issues: ", len(all_issues))