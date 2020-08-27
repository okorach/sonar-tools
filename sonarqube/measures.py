#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "measure" concept

'''
import json
import sonarqube.env as env
import sonarqube.utilities as util
import sonarqube.sqobject as sq
import sonarqube.metrics as metrics


class Measure(sq.SqObject):
    API_ROOT = 'measures'
    API_COMPONENT = API_ROOT + '/component'
    API_HISTORY = API_ROOT + '/search_history'

    def __init__(self, key=None, value=None, endpoint=None):
        super().__init__(key=key, env=endpoint)
        if metrics.is_a_rating(self.key):
            self.value = get_rating_letter(value)
        else:
            self.value = value
        self.history = None

    def read(self, project_key, metric_key):
        resp = self.get(Measure.API_COMPONENT, {'component': project_key, 'metricKeys': metric_key})
        data = json.loads(resp.text)
        return data['component']['measures']

    def count_history(self, project_key, params=None):
        if params is None:
            params = {}
        params.update({'component': project_key, 'metrics': self.key, 'ps': 1})
        resp = self.get(Measure.API_HISTORY, params=params)
        data = json.loads(resp.text)
        return data['paging']['total']

    def search_history(self, project_key, params=None, page=0):
        MAX_PAGE_SIZE = 1000
        measures = {}
        if page != 0:
            if params is None:
                params = {}
            resp = self.get(Measure.API_HISTORY, {'component': project_key, 'metrics': self.key, 'ps': 1000})
            data = json.loads(resp.text)
            for m in data['measures'][0]['history']:
                measures[m['date']] = m['value']
            return measures
        nb_pages = (self.count_history(project_key, params=params) + MAX_PAGE_SIZE - 1) // MAX_PAGE_SIZE
        for p in range(nb_pages):
            measures.update(self.search_history(project_key=project_key, params=params, page=p + 1))
        return measures


def component(component_key, metric_keys, endpoint=None, **kwargs):
    kwargs['component'] = component_key
    kwargs['metricKeys'] = metric_keys
    resp = env.get(Measure.API_COMPONENT, params=kwargs, ctxt=endpoint)
    data = json.loads(resp.text)
    m_list = {}
    for m in data['component']['measures']:
        value = m.get('value', '')
        if value == '' and 'periods' in m:
            value = m['periods'][0]['value']
        if metrics.is_a_rating(m['metric']):
            m_list[m['metric']] = get_rating_letter(value)
        else:
            m_list[m['metric']] = value
    return m_list


def get_rating_letter(rating_number_str):
    try:
        n_int = int(float(rating_number_str))
        return chr(n_int + 64)
    except ValueError:
        util.logger.error("Wrong numeric rating provided %s", rating_number_str)
        return rating_number_str


def get_rating_number(rating_letter):
    l = rating_letter.upper()
    if l in ['A', 'B', 'C', 'D', 'E']:
        return ord(l) - 64
    return rating_letter
