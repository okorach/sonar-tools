#!python3

import json
import requests
import env

class Measure:

    def __init__(self):
        self.name = ''
        self.value = ''

    def read(self, project_key, metric_key, myenv):
        parms = dict(component=project_key, metricKeys=metric_key)
        if (myenv is None):
            resp = env.get('/api/measures/component',  parms)
        else:
            resp = myenv.get('/api/measures/component',  parms)
        data = json.loads(resp.text)
        return data['component']['measures']



def load_measures(project_key, metrics_list, myenv):
    parms = dict(component=project_key, metricKeys=metrics_list)
    if (myenv is None):
        resp = env.get('/api/measures/component',  parms)
    else:
        resp = myenv.get('/api/measures/component', parms)
    data = json.loads(resp.text)
    return data['component']['measures']

