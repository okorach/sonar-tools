#!/usr/local/bin/python3

import json
import requests
import sonarqube.env as env
import sonarqube.sqobject
import sonarqube.utilities as util


def get_all_metrics(myenv):
    if myenv is None:
        resp = env.get('/api/metrics/search',  {})
    else:
        resp = myenv.get('/api/metrics/search', {})
    if resp.status_code != 200:
        util.logger.error('HTTP Error %d from SonarQube API query: %s', resp.status_code, resp.content)
    data = json.loads(resp.text)
    return data['metrics']

def get_all_metrics_csv(myenv = None):
    metrics = get_all_metrics(myenv)
    # Workaround for SonarQube Web API bug that does not return vulnerabilities metric
    csv = 'vulnerabilities'
    for metric in metrics:
        if metric['key'] == 'new_development_cost' or metric['key'] == 'vulnerabilities':
            # Skip new_development_cost metric to work around a SonarQube 7.9 bug
            continue
        csv = csv + ",{0}".format(metric['key'])
    return csv
