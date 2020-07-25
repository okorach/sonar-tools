#!/usr/local/bin/python3

'''
        Abstraction of the SonarQube metric concept
'''

import re
import json
import requests
import sonarqube.env as env
import sonarqube.sqobject
import sonarqube.utilities as util

MAIN_METRICS = 'ncloc,bugs,reliability_rating,vulnerabilities,security_rating,code_smells,' + \
    'sqale_rating,sqale_index,coverage,duplicated_lines_density,new_bugs,new_vulnerabilities,new_code_smells,' + \
    'new_technical_debt,new_maintainability_rating,coverage,duplicated_lines_density,' + \
    'new_coverage,new_duplicated_lines_density'

def get_all_metrics(myenv = None):
    # TODO paginated API if more than 500 metrics
    resp = env.get('metrics/search',  params={'ps':500}, ctxt=myenv)
    if resp.status_code != 200:
        util.logger.error('HTTP Error %d from SonarQube API query: %s', resp.status_code, resp.content)
    data = json.loads(resp.text)
    return data['metrics']

def get_all_metrics_csv(myenv = None):
    metrics = get_all_metrics(myenv)
    csv = ''
    for metric in metrics:
        if metric['key'] == 'new_development_cost':
            # Skip new_development_cost metric to work around a SonarQube 7.9 bug
            continue
        csv = csv + "{0},".format(metric['key'])
    return csv[:-1]

def is_a_rating(metric):
    return re.match(r"^(new_)?(security|security_review|reliability|maintainability)_rating$", metric)
