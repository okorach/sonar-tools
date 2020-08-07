#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "component" concept

'''

import sys
import datetime
import json
import requests
import sonarqube.sqobject as sq
import sonarqube.utilities as util
import sonarqube.env as env
import sonarqube.measures as measures
import sonarqube.issues as issues

class Component(sq.SqObject):

    def __init__(self, key, name=None, sqenv=None):
        super().__init__(key, sqenv)
        self.name = name
        self.nbr_issues = None
        self.env = sqenv

    def get_subcomponents(self):
        params = {'component':self.key, 'strategy':'children', 'ps':500, 'p':1}
        resp = env.get('components/tree', params, self.env)
        data = json.loads(resp.text)
        comps = []
        for comp in data['components']:
            comps.append(Component(key=comp['key'], name=comp['name'], sqenv=self.env))
        return comps

    def get_number_of_filtered_issues(self, params):
        params['componentKey'] = self.key
        params['ps'] = 1
        returned_data = issues.search(endpoint=self.env, params=params)
        return returned_data['total']

    def get_number_of_issues(self):
        ''' Returns number of issues of a component '''
        if self.nbr_issues is None:
            self.nbr_issues = self.get_number_of_filtered_issues({'componentKey': self.key})
        return self.nbr_issues

    def get_oldest_issue_date(self):
        ''' Returns the oldest date of all issues found '''
        return issues.get_oldest_issue(endpoint=self.env, params={'componentKeys': self.key})

    def get_newest_issue_date(self):
        ''' Returns the newest date of all issues found '''
        return issues.get_newest_issue(endpoint=self.env, params={'componentKeys': self.key})

    def get_issues(self):
        issue_list = issues.search(endpoint=self.env, params={'componentKeys':self.key})
        self.nbr_issues = len(issue_list)
        return issue_list

    def get_measures(self, metric_list):
        return measures.component(component_key=self.key, metric_keys=','.join(metric_list), endpoint=self.env)

    def get_measure(self, metric):
        res = self.get_measures(metric_list = [metric])
        for m in res:
            if m['metric'] == metric:
                return m['value']
        return None

def get_components(component_types):
    params = dict(ps=500, qualifiers=component_types)
    resp = env.get('projects/search', params=params)
    data = json.loads(resp.text)
    return data['components']
