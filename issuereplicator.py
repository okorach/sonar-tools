#!/usr/local/bin/python
#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3

import sys
import json
import argparse
import requests
import sonarqube.env as env
import sonarqube.issues as issues
import sonarqube.utilities as utils

# Mandatory script input parameters
global project_key
global dry_run_mode
dry_run_mode = False

def print_object(o):
    print(json.dumps(o, indent=3, sort_keys=True))

# ------------------------------------------------------------------------------


def parse_args(desc):
    parser = utils.set_common_args(desc)
    parser.add_argument('-r', '--recover', required=False,
                        help='''What information to replicate. Default is FP and WF, but issue assignment,
                        tags, severity and type change can be recovered too''')
    parser.add_argument('-d', '--dryrun', required=False,
                        help='If True, show changes but don\'t apply, if False, apply changes - Default is true')
    return parser.parse_args()


args = parse_args('Replicates issue history between 2 same projects on 2 SonarQube platforms or 2 branches')
source_env = env.Environment(url=args.url, token=args.token)
target_env = env.Environment(url=args.urlTarget, token=args.tokenTarget)

parms = vars(args)
for key in parms:
    if parms[key] is None:
        del parms[key]
parms['componentKeys'] = parms['projectKey']
# Add SQ environment

parms.update(dict(env=source_env))
all_source_issues = issues.search_all_issues(**parms)
print("Found %d issues with manual changes on source project\n" % len(all_source_issues))

parms.update(dict(env=target_env))
all_target_issues = issues.search_all_issues(**parms)
print("Found %d target issues on target project\n" % len(all_target_issues))

for issue in all_target_issues:
    print('Searching sibling for issue key %s\n' % issue.id)
    siblings = issues.search_siblings(issue, all_source_issues, False)
    nb_siblings = len(siblings)
    if nb_siblings >= 0:
        print('   Found %d sibling(s)\n' % nb_siblings)
        if nb_siblings == 1:
            print('Found a match issue id %s' % siblings[0].id)
            if siblings[0].has_changelog_or_comments():
                print('   Automatically applying changelog')
                issues.apply_changelog(issue, siblings[0], True)
            else:
                print('   No changelog to apply')
        else:
            print('   Ambiguity for issue, cannot automatically apply changelog, candidate issue keys below')
            for sibling in siblings:
                print(sibling.id + ', ')
