#!/usr/local/bin/python3
'''

    Audits a SonarQube platform

'''
import re
import json
import datetime
import argparse
import requests
import pytz
import sonarqube.measures as measures
import sonarqube.metrics as metrics
import sonarqube.projects as projects
import sonarqube.qualityprofiles as qualityprofiles
import sonarqube.utilities as util
import sonarqube.env as env

def diff(first, second):
    second = set(second)
    return [item for item in first if item not in second]

parser = util.set_common_args('Deletes projects not analyzed since a given numbr of days')
parser.add_argument('-o', '--olderThan', required=True, help='Days since last analysis')
args = parser.parse_args()
sq = env.Environment(url=args.url, token=args.token)
kwargs = vars(args)
util.check_environment(kwargs)

olderThan = int(args.olderThan)
if olderThan < 90:
    util.logger.error("Can't delete projects more recent than 90 days")
    exit(1)
issues = projects.audit(endpoint=sq)
issues += qualityprofiles.audit(endpoint=sq)
issues += sq.audit()
if issues > 0:
    util.logger.warning("%d issues found during audit", issues)
else:
    util.logger.info("%d issues found during audit", issues)
exit(1)