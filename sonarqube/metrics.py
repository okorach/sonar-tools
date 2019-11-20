#!/usr/local/bin/python3

import json
import requests
import sonarqube.env as env
import sonarqube.sqobject
import sonarqube.utilities as util


def get_all_metrics(myenv):
    # TODO paginated API if more than 500 metrics
    if myenv is None:
        resp = env.get('/api/metrics/search',  {'ps':500})
    else:
        resp = myenv.get('/api/metrics/search', {'ps':500})
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
