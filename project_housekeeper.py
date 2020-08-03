#!/usr/local/bin/python3
'''

    Deletes projects that has not been analyzed for a given amount of time

'''
import re
import json

import argparse
import requests
import sonarqube.measures as measures
import sonarqube.metrics as metrics
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.env as env

def diff(first, second):
    second = set(second)
    return [item for item in first if item not in second]

parser = util.set_common_args('Deletes projects not analyzed since a given numbr of days')
parser.add_argument('-o', '--olderThan', required=True, help='Days since last analysis')
args = parser.parse_args()
kwargs = vars(args)
util.check_environment(kwargs)

olderThan = int(args.olderThan)
if olderThan < 90:
    util.logger.error("Can't delete projects more recent than 90 days")
    exit(1)

projects.delete_old_projects(days=olderThan, endpoint=env.Environment(url=args.url, token=args.token))
