#!/usr/local/bin/python
import json
import requests
import string
import sonarqube.measures
import sonarqube.projects
import sonarqube.env
import argparse

def parse_args():
    global __project_key
    parser = argparse.ArgumentParser(
            description='Extract measures of projects')
    parser.add_argument('-p', '--projectKey', help='Project key of the project to search', required=False)
    parser.add_argument('-t', '--token',
                        help='Token to authenticate to SonarQube - Unauthenticated usage is not possible',
                        required=True)
    parser.add_argument('-u', '--url', help='Root URL of the SonarQube server, default is http://localhost:9000',
                        required=False)

    args = parser.parse_args()

    __project_key = args.projectKey
    sonarqube.env.set_token(args.token)
    sonarqube.env.set_url(args.url if args.url != None else "http://localhost:9000")


parse_args()
# Mandatory script input parameters
csv_sep = ";"

metrics = 'ncloc,new_violations,new_bugs,complexity,coverage,sqale_index'
project_list = sonarqube.projects.get_projects(True)

print("key" + csv_sep + "name" + csv_sep + "last analysis" + csv_sep + string.replace(metrics, ",", csv_sep))
metrics_list = metrics.split(",")

for project in project_list:
    key = project['key']
    p_name = project['name']
    last_analysis = project['lastAnalysisDate'] if 'lastAnalysisDate' in project else 'Not analyzed yet'
    line = key + csv_sep + p_name + csv_sep + last_analysis
    
    all_measures = sonarqube.measures.load_measures(key, metrics)
    p_meas = {}
    for measure in all_measures:
        name = measure['metric'] if 'metric' in measure else ''
        value = measure['value'] if 'value' in measure else ''
        p_meas[name] = value
    for measure in metrics_list:
        line = line + csv_sep + p_meas[measure] if measure in p_meas else line + csv_sep
    print(line)


print(str(sonarqube.projects.count(True)) + " PROJECTS")