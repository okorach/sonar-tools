#!python3

import json
import requests
import sonarqube.env

class Measure:

    def __init__(self):
        self.name = ''
        self.value = ''

    def read(self, project_key, metric_key):
        params = dict(component=project_key, metricKeys=metric_key)
        resp = requests.get(url=sonarqube.env.get_url() + '/api/measures/component', auth=sonarqube.env.get_credentials(), params=params)
        data = json.loads(resp.text)
        return data['component']['measures']



def load_measures(project_key, metrics_list):
    params = dict(component=project_key, metricKeys=metrics_list)
    resp = requests.get(url=sonarqube.env.get_url() + '/api/measures/component', auth=sonarqube.env.get_credentials(), params=params)
    data = json.loads(resp.text)
    return data['component']['measures']

