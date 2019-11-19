#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3
import re
import json
import argparse
import requests
import sonarqube.measures as measures
import sonarqube.metrics as metrics
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.env as env


MAIN_METRICS = 'bugs,reliability_rating,vulnerabilities,security_rating,code_smells,' + \
    'sqale_rating,sqale_index,coverage,duplicated_lines_density,new_bugs,new_vulnerabilities,new_code_smells,' + \
    'new_technical_debt,new_maintainability_rating,coverage,duplicated_lines_density,' + \
    'new_coverage,new_duplicated_lines_density'

def diff(first, second):
    second = set(second)
    return [item for item in first if item not in second]

def get_rating_letter(n):
    if n == '1.0':
        return 'A'
    elif n == '2.0':
        return 'B'
    elif n == '3.0':
        return 'C'
    elif n == '4.0':
        return 'D'
    elif n == '5.0':
        return 'E'
    else:
        util.logger.error("Wrong numeric rating provided %s", n)
        return None

parser = util.set_common_args('Extract measures of projects')
parser.add_argument('-m', '--metricKeys', required=False, help='Comma separated list of metrics or _all or _main')
parser.add_argument('-r', '--ratingsAsLetters', action='store_true', required=False, \
                    help='Reports ratings as ABCDE letters instead of 12345 numbers')

args = parser.parse_args()
myenv = env.Environment(url=args.url, token=args.token)
kwargs = vars(args)
util.check_environment(kwargs)

# Mandatory script input parameters
csv_sep = ";"

if args.metricKeys == '_all':
    metrics = metrics.get_all_metrics_csv(myenv)
elif args.metricKeys == '_main':
    metrics = MAIN_METRICS
elif args.metricKeys is not None:
    metrics = args.metricKeys
else:
    metrics = MAIN_METRICS

print ("Project Key%sProject Name%sLast Analysis" % (csv_sep, csv_sep), end=csv_sep)
metrics_list = re.split(',', metrics)
main_metrics_list = re.split(',', MAIN_METRICS)
if args.metricKeys == '_all':
    for m in re.split(',', MAIN_METRICS):
        print ("%s" % m, end=csv_sep)
    metrics_list = diff(metrics_list, main_metrics_list)

for m in metrics_list:
    print ("%s" % m, end=csv_sep)
print('')
project_list = projects.get_projects(True, myenv)
for project in project_list:
    last_analysis = project['lastAnalysisDate'] if 'lastAnalysisDate' in project else 'Not analyzed yet'
    all_measures = measures.load_measures(project['key'], metrics, myenv)
    p_meas = {}
    for measure in all_measures:
        name = measure['metric'] if 'metric' in measure else ''
        if 'value' in measure:
            value = measure['value']
        elif 'periods' in measure:
            value = measure['periods'][0]['value']
        else:
            value = ''
        if args.ratingsAsLetters and re.match(r"^(new_)?(security|security_review|reliability|maintainability)_rating$", name):
            p_meas[name] = get_rating_letter(value)
        else:
            p_meas[name] = value
    line = ''
    print("%s%s%s%s%s" % (project['key'], csv_sep, project['name'], csv_sep, last_analysis), end='')
    if args.metricKeys == '_all':
        for metric in main_metrics_list:
            line = line + csv_sep + p_meas[metric].replace(csv_sep, '|') if metric in p_meas else line + csv_sep
    for metric in metrics_list:
        line = line + csv_sep + p_meas[metric].replace(csv_sep, '|') if metric in p_meas else line + csv_sep + "None"
    print(line)

util.logger.info("%d PROJECTS", projects.count(True, myenv))
