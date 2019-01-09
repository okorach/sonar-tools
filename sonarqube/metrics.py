#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3

import json
import requests
import sonarqube.env
import sonarqube.sqobject


def get_all_metrics(myenv):
    parms = dict()
    if (myenv is None):
        resp = sonarqube.env.get('/api/metrics/search',  parms)
    else:
        resp = myenv.get('/api/metrics/search', parms)
    data = json.loads(resp.text)
    return data['metrics']

def get_all_metrics_csv(myenv = None):
    metrics = get_all_metrics(myenv)
    is_first = True
    for metric in metrics:
        if is_first:
            csv_list = metric['key']
            is_first = False
        else:
            csv_list = csv_list + ',' + metric['key']
    return csv_list
    