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
    global project_key
    global dry_run_mode

    parser = argparse.ArgumentParser(
            description='Search for unexpectedly closed issues and recover their history in a corresponding new issue.')
    parser.add_argument('-p', '--projectKey', help='Project key of the project to search', required=True)
    parser.add_argument('-t', '--token',
                        help='Token to authenticate to SonarQube - Unauthenticated usage is not possible',
                        required=True)
    parser.add_argument('-r', '--recover',
                        help='What information to recover (default is FP and WF, but issue assignment, tags, severity and type change can be recovered too',
                        required=False)
    parser.add_argument('-d', '--dryrun',
                        help='If True, show changes but don\'t apply, if False, apply changes - Default is true',
                        required=False)
    parser.add_argument('-u', '--url', help='Root URL of the SonarQube server, default is http://localhost:9000',
                        required=False)

    args = parser.parse_args()

    project_key = args.projectKey
    sonarqube.env.set_token(args.token)
    sonarqube.env.set_url(args.url if args.url != None else "http://localhost:9000")

    if args.dryrun == "False":
        dry_run_mode = False


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

parse_args()


all_issues = sonarqube.issues.search(project_key)

non_closed_issues = []
mistakenly_closed_issues = []

for issue in all_issues:
    print('----ISSUE-------------------------------------------------------------')
    print(issue.to_string())
    # print('----CHANGELOG-------------')
    # print_object(get_changelog(issue['key']))
    print('----------------------------------------------------------------------')
    if issue.get_status() == 'CLOSED':
        if issue.was_fp_or_wf():
            print("Mistakenly closed: " + issue.to_string())
            mistakenly_closed_issues.append(issue)
    else:
        non_closed_issues.append(issue)

print('----------------------------------------------------------------------')
print('        ', len(mistakenly_closed_issues), 'mistakenly closed issues')
print('----------------------------------------------------------------------')

for issue in mistakenly_closed_issues:
    # print_issue(issue)
    # print_change_log(issue['key'])
    print('Searching sibling for issue key ', issue.id)
    siblings = sonarqube.issues.search_siblings(issue, non_closed_issues, False)
    if len(siblings) >= 0:
        print('   Found', len(siblings), 'SIBLING(S)')
        for sibling in siblings:
            print('  ')
            sibling.print_issue()
        if len(siblings) == 1:
            print('   Automatically applying changelog')
            sonarqube.issues.apply_changelog(siblings[0], issue, True)
        else:
            print('Ambiguity for issue, cannot automatically apply changelog')
    print('----------------------------------------------------------------------')
