#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "measure" concept

'''
import json
import requests
import sonarqube.env as env
import sonarqube.utilities as util
import sonarqube.sqobject as sq

class Measure (sq.SqObject):
    API_ROOT = '/api/measures'
    API_COMPONENT = API_ROOT + '/component'
    API_HISTORY = API_ROOT + '/search_history'
    def __init__(self, key = None, value = None, **kwargs):
        super().__init__(key=key,env=kwargs['env'])
        self.value = value
        self.history = None

    def read(self, project_key, metric_key):
        resp = self.get(Measure.API_COMPONENT,  {'component':project_key, 'metricKeys':metric_key})
        data = json.loads(resp.text)
        return data['component']['measures']

    def get_history(self, project_key):
        resp = self.get(Measure.API_HISTORY,  {'component':project_key, 'metrics':self.key, 'ps':1000})
        data = json.loads(resp.text)
        return data['component']['measures']

def component(component, metricKeys, endpoint=None, **kwargs):
    kwargs['component'] = component
    kwargs['metricKeys'] = metricKeys
    resp = env.get(Measure.API_COMPONENT, params=kwargs, ctxt=endpoint)
    if resp.status_code != 200:
        util.logger.error('HTTP Error %d from SonarQube API query: %s', resp.status_code, resp.content)

    data = json.loads(resp.text)
    return data['component']['measures']

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
