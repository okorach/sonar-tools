#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3
import os
import re
import json
import argparse
import requests
import sonarqube.measures as measures
import sonarqube.metrics as metrics
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.env as env

parser = util.set_common_args('Extract measures of projects')
parser.add_argument('-p', '--pollInterval', required=False, help='Interval to check exports status')
parser.add_argument('--exportTimeout', required=False, help='Maximum wait time for export')

args = parser.parse_args()
myenv = env.Environment(url=args.url, token=args.token)
kwargs = vars(args)
util.check_environment(kwargs)
poll_interval = 1
if args.pollInterval is not None:
    poll_interval = int(args.pollInterval)
if args.exportTimeout is not None:
    export_timeout = int(args.exportTimeout)

project_list = projects.get_projects(False, myenv)
nb_projects = len(project_list)
util.logger.info("%d projects to export", nb_projects)
i = 0
statuses = {}
for p in project_list:
    key = p['key']
    dump = projects.Project(key, sqenv = myenv).export(timeout = export_timeout)
    status = dump['status']
    if status in statuses:
        statuses[status] += 1
    else:
        statuses[status] = 1
    if status == 'SUCCESS':
        print("{0},{1}".format(key, os.path.basename(dump['file'])))
    i += 1
    util.logger.info("%d/%d exports (%d%%) - Latest: %s - %s", i, nb_projects, int(i * 100/nb_projects), key, status)
    summary = ''
    for s in statuses:
        summary += "{0}:{1}, ".format(s, statuses[s])
    util.logger.info("%s", summary)