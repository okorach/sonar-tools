#!/usr/local/bin/python3
'''
    Exports some measures of all projects
    - Either all measures (-m _all)
    - Or the main measures (-m _main)
    - Or a custom selection of measures (-m <measure1,measure2,measure3...>)
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

parser = util.set_common_args('Extract measures of projects')
parser = util.set_component_args(parser)
parser.add_argument('-m', '--metricKeys', required=False, help='Comma separated list of metrics or _all or _main')
parser.add_argument('-b', '--withBranches', required=False, action='store_true', help='Also extract branches metrics')
parser.add_argument('--withTags', required=False, action='store_true', help='Also extract project tags')
parser.set_defaults(withBranches=False, withTags=False)
parser.add_argument('-r', '--ratingsAsLetters', action='store_true', required=False, \
                    help='Reports ratings as ABCDE letters instead of 12345 numbers')

args = parser.parse_args()
myenv = env.Environment(url=args.url, token=args.token)
kwargs = vars(args)
util.check_environment(kwargs)

# Mandatory script input parameters
csv_sep = ";"

if args.metricKeys == '_all':
    wanted_metrics = metrics.get_all_metrics_csv(myenv)
elif args.metricKeys == '_main':
    wanted_metrics = metrics.MAIN_METRICS
elif args.metricKeys is not None:
    wanted_metrics = args.metricKeys
else:
    wanted_metrics = metrics.MAIN_METRICS

print ("Project Key%sProject Name%sBranch%sLast Analysis" % (csv_sep, csv_sep, csv_sep), end=csv_sep)
metrics_list = re.split(',', wanted_metrics)
main_metrics_list = re.split(',', metrics.MAIN_METRICS)
if args.metricKeys == '_all':
    for m in re.split(',', metrics.MAIN_METRICS):
        print ("%s" % m, end=csv_sep)
    metrics_list = diff(metrics_list, main_metrics_list)

for m in metrics_list:
    print ("%s" % m, end=csv_sep)
print('')

project_list = projects.search(endpoint=myenv)
nb_branches = 0
for _, project in project_list.items():
    util.logger.debug("Checking project %s - %s", project, str(project))
    last_analysis = project.get_last_analysis_date(False)
    branch_data = project.get_branches()
    branch_list = []
    for b in branch_data:
        util.logger.debug("Checking branch %s", b['name'])
        if args.withBranches or b['isMain']:
            branch_list.append(b)
            util.logger.debug("Branch %s appended", b['name'])

    for b in branch_list:
        nb_branches += 1
        p_meas = measures.component(project.key, wanted_metrics, branch_name=b['name'], endpoint=myenv)
        last_analysis = b.get('analysisDate', '')
        line = ''
        print("%s%s%s%s%s%s%s" % (project.key, csv_sep, project.name, csv_sep, b['name'], \
            csv_sep, last_analysis), end='')
        if args.metricKeys == '_all':
            for metric in main_metrics_list:
                line = line + csv_sep + p_meas[metric].replace(csv_sep, '|') if metric in p_meas else line + csv_sep
        for metric in metrics_list:
            line = line + csv_sep + p_meas[metric].replace(csv_sep, '|') if metric in p_meas \
                else line + csv_sep + "None"
        print(line)

util.logger.info("%d PROJECTS %d branches", len(project_list), nb_branches)
