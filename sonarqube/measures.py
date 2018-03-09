#!python3

import json
import requests
import env

class Measure:

    def __init__(self):
        self.name = ''
        self.value = ''

    def read(self, project_key, metric_key):
        params = dict(component=project_key, metricKeys=metric_key)
        resp = requests.get(url=root_url + '/api/measures/component', auth=credentials, params=params)
        data = json.loads(resp.text)
        return data['component']['measures']



def load_measures(project_key, metrics_list):
    params = dict(component=project_key, metricKeys=metrics_list)
    url = env.get_url()
    resp = requests.get(url=url + '/api/measures/component', auth=env.get_credentials(), params=params)
    data = json.loads(resp.text)
    return data['component']['measures']

