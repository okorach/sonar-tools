#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3
import re
import json
import datetime
import argparse
import requests
import pytz
import sonarqube.measures as measures
import sonarqube.metrics as metrics
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.env as env

def diff(first, second):
    second = set(second)
    return [item for item in first if item not in second]

parser = util.set_common_args('Extract measures of projects')
parser.add_argument('-o', '--olderThan', required=True, help='Days since last analysis')
args = parser.parse_args()
myenv = env.Environment(url=args.url, token=args.token)
kwargs = vars(args)
util.check_environment(kwargs)

csv_sep = ";"
olderThan = int(args.olderThan)
if olderThan < 90:
    util.logger.error("Can't delete projects more recent than 90 days")
    exit(1)

today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
mindate = today - datetime.timedelta(days=olderThan)
project_list = projects.get_projects(include_applications = False, sqenv = myenv)
proj_to_delete = 0
loc_to_delete = 0
for project in project_list:
    last_analysis = today
    if 'lastAnalysisDate' in project:
        last_analysis = datetime.datetime.strptime(project['lastAnalysisDate'], '%Y-%m-%dT%H:%M:%S%z')
    p_obj = projects.Project(project['key'], sqenv = myenv)
    for b in p_obj.get_branches():
        branch_analysis_date = datetime.datetime.strptime(b.get('analysisDate', ''), '%Y-%m-%dT%H:%M:%S%z')
        if branch_analysis_date > last_analysis:
            last_analysis = branch_analysis_date
    last_analysis = last_analysis.replace(tzinfo=pytz.UTC)
    if last_analysis < mindate:
        util.logger.info("Project key %s has not been analyzed for %d days, it should be deleted",
                         p_obj.key, (today - last_analysis).days)
        proj_to_delete += 1
        loc_to_delete += int(p_obj.get_measure('ncloc'))


util.logger.info("%d PROJECTS %d LoCs to delete", proj_to_delete, loc_to_delete)
