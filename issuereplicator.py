#!/usr/local/bin/python
#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3

import sys
import json
import argparse
import requests
import sonarqube.env as env
import sonarqube.issues as issues
import sonarqube.utilities as util

# Mandatory script input parameters
dry_run_mode = False

# ------------------------------------------------------------------------------


def parse_args(desc):
    parser = util.set_common_args(desc)
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
util.logger.info("Found %d issues with manual changes on source project", len(all_source_issues))

parms.update(dict(env=target_env))
all_target_issues = issues.search_all_issues(**parms)
util.logger.info("Found %d target issues on target project", len(all_target_issues))

for issue in all_target_issues:
    util.logger.info('Searching sibling for issue key %s', issue.id)
    siblings = issues.search_siblings(issue, all_source_issues, False)
    nb_siblings = len(siblings)
    util.logger.debug('Found %d sibling(s) for issue %s', nb_siblings, issue.id)
    if nb_siblings == 0:
        continue
    if nb_siblings >= 1:
        util.logger.info('Ambiguity for issue key %s, cannot automatically apply changelog', issue.id)
        util.logger.info('Candidate issue keys below')
        for sibling in siblings:
            util.logger.debug(sibling.id)
        continue
    # Exactly 1 match
    util.logger.debug('Found a match issue id %s', siblings[0].id)
    if siblings[0].has_changelog_or_comments():
        util.logger.debug('Automatically applying changelog')
        issues.apply_changelog(issue, siblings[0], True)
    else:
        util.logger.debug('No changelog to apply')
