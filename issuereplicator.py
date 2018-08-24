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
    parser.add_argument('-p', '--projectKey', help='Project key of the project to search', required=True)
    parser.add_argument('-u', '--urlSource',
                        help='Root URL of the source SonarQube server',
                        required=True)
    parser.add_argument('-t', '--tokenSource',
                        help='Token to authenticate to source SonarQube - Unauthenticated usage is not possible',
                        required=True)
    parser.add_argument('-U', '--urlTarget', help='Root URL of the target SonarQube server',
                        required=True)
    parser.add_argument('-T', '--tokenTarget',
                        help='Token to authenticate to target SonarQube - Unauthenticated usage is not possible',
                        required=True)
    parser.add_argument('-r', '--recover',
                        help='What information to recover (default is FP and WF, but issue assignment, tags, severity and type change can be recovered too',
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
source_env = sonarqube.env.Environment(url=args.urlSource, token=args.tokenSource)
target_env = sonarqube.env.Environment(url=args.urlTarget, token=args.tokenTarget)

noneparms = vars(args)
parms = dict()
parms['componentKeys'] = noneparms['projectKey']
# Add SQ environment
parms.update(dict(env=source_env))
all_source_issues = sonarqube.issues.search_all_issues(**parms)
print('Found ' + str(len(all_source_issues)) + " source issues")
parms.update(dict(env=target_env))
all_target_issues = sonarqube.issues.search_all_issues(**parms)

print('Found ' + str(len(all_target_issues)) + " target issues")

for issue in all_target_issues:
    print('Searching sibling for issue key ', issue.id)
    siblings = sonarqube.issues.search_siblings(issue, all_source_issues, False)
    nb_siblings = len(siblings)
    if nb_siblings >= 0:
        print('   Found ' + str(nb_siblings) + ' sibling(s)')
        if nb_siblings == 1:
            print('Found a match issue id ' + siblings[0].id)
            if siblings[0].has_changelog_or_comments():
                print('   Automatically applying changelog')
                sonarqube.issues.apply_changelog(issue, siblings[0], True)
            else:
                print('   No changelog to apply')
        else:
            print('   Ambiguity for issue, cannot automatically apply changelog, candidate issue keys below')
            for sibling in siblings:
                print(sibling.id + ', ')
