#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3

import sys
import json
import requests
import sonarqube.env as env
import sonarqube.issues as issues
import sonarqube.utilities as util

# Mandatory script input parameters
dry_run_mode = False

def parse_args():
    parser = util.set_common_args('SonarQube issues extractor')
    parser.add_argument('-s', '--statuses', help='comma separated issue status', required=False)
    parser.add_argument('-a', '--createdAfter', help='issues created after a given date', required=False)
    parser.add_argument('-b', '--createdBefore', help='issues created before a given date', required=False)
    #parser.add_argument('-p', '--projectKey', help='projectKey', required=False)
    parser.add_argument('-r', '--resolutions', help='Comma separated resolution state of the issues', required=False)
    parser.add_argument('--severities', help='Comma separated severities', required=False)
    parser.add_argument('--types', help='Comma separated issue types', required=False)
    parser.add_argument('--tags', help='Comma separated issue tags', required=False)

    return parser.parse_args()

# ------------------------------------------------------------------------------

try:
    import argparse
except ImportError:
    if sys.version_info < (2, 7, 0):
        util.logger.critical("Python < 2.7, can't import argparse, aborting...")
        exit(1)
args = parse_args()
sqenv = env.Environment(url=args.url, token=args.token)
sqenv.set_env(args.url, args.token)
kwargs = vars(args)
util.check_environment(kwargs)

# Remove unset params from the dict
noneparms = vars(args)
parms = dict()
for parm in noneparms:
    if noneparms[parm] is not None:
        parms[parm] = noneparms[parm]
# Add SQ environment
parms.update(dict(env=sqenv))

for parm in parms:
    util.logger.debug("%s --> %s", parm, parms[parm])

all_issues = issues.search_all_issues_unlimited(sqenv=sqenv, **parms)
print(issues.to_csv_header())
for issue in all_issues:
    print(issue.to_csv())
util.logger.info("Returned issues: %d", len(all_issues))
