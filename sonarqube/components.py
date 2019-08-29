#!python3

import sys
import datetime
import json
import requests
import sonarqube.env as env
import sonarqube.issues as issues

class Component:

    def __init__(self, key, name=None, sqenv=None):
        self.key = key
        self.name = name
        self.sqenv = sqenv
        self.nbr_issues = None

    def get_subcomponents(self):
        params = dict(component=self.key, strategy='children', ps=500, p=1)
        if sqenv is None:
            resp = env.get('/api/components/tree', params)
        else:
            resp = self.sqenv.get('/api/components/tree', params)
        data = json.loads(resp.text)
        comps = []
        for comp in data['components']:
            comps = comps + Component(key=comp['key'], name=comp['name'], sqenv=self.sqenv)
        return comps

    def get_number_of_filtered_issues(self, **kwargs):
        kwargs['componentKey'] = self.key
        kwargs['ps'] = 1
        returned_data = issues.search(sqenv=self.sqenv, **kwargs)
        return returned_data['total']

    def get_number_of_issues(self):
        ''' Returns number of issues of a component '''
        if self.nbr_issues is None:
            self.nbr_issues = self.get_number_of_filtered_issues(**{'componentKey': self.key})
        return self.nbr_issues


    def get_all_issues(self):
        return self.get_issues()

    def get_oldest_issue_date(self):
        ''' Returns the oldest date of all issues found '''
        return issues.get_oldest_issue(sqenv=self.sqenv, **{'componentKeys': self.key})

    def get_newest_issue(self):
        ''' Returns the newest date of all issues found '''
        return issues.get_newest_issue(sqenv=self.sqenv, **{'componentKeys': self.key})

    def get_issues(self, **kwargs):
        kwargs['componentKeys'] = self.key
        oldest = self.get_oldest_issue_date(sqenv=self.sqenv, **kwargs)
        if oldest is None:
            return []

        nbr_issues = self.get_number_of_filtered_issues(**kwargs)
        issue_list = []
        if nbr_issues <= 10000:
            issue_list = issues.search_all_issues(sqenv=self.sqenv, **kwargs)
        elif 'createdAfter' not in kwargs or 'createdBefore' not in kwargs:
            startdate = datetime.datetime.strptime(oldest, '%Y-%m-%dT%H:%M:%S%z')
            enddate = datetime.datetime.strptime(self.get_newest_issue(), '%Y-%m-%dT%H:%M:%S%z')
            kwargs['createdAfter']  = "%04d-%02d-%02d" % (startdate.year, startdate.month, startdate.day)
            kwargs['createdBefore'] = "%04d-%02d-%02d" % (enddate.year, enddate.month, enddate.day)
            issue_list = self.get_issues(**kwargs)
        elif kwargs['createdAfter'] != kwargs['createdBefore']:
            startdate = datetime.datetime.strptime(kwargs['createdAfter'], '%Y-%m-%d')
            enddate = datetime.datetime.strptime(kwargs['createdBefore'], '%Y-%m-%d')
            mid_date = startdate + datetime.timedelta(days=abs((enddate - startdate).days) // 2)
            kwargs['createdAfter']  = "%04d-%02d-%02d" % (mid_date.year, mid_date.month, mid_date.day)
            kwargs['createdBefore'] = "%04d-%02d-%02d" % (enddate.year, enddate.month, enddate.day)
            issue_list = self.get_issues(**kwargs)
            kwargs['createdAfter']  = "%04d-%02d-%02d" % (startdate.year, startdate.month, startdate.day)
            kwargs['createdBefore'] = "%04d-%02d-%02d" % (mid_date.year, mid_date.month, mid_date.day)
            issue_list = issue_list + self.get_issues(**kwargs)
        else:
            issue_list = []
            for comp in self.get_subcomponents():
                issue_list = issue_list + comp.get_all_issues()

        env.debug("For component %s, %d issues found after filter" % (key, len(issue_list)))
        return issue_list


def get_components(component_types):
    params = dict(ps=500, qualifiers=component_types)
    resp = requests.get(url=env.get_url() + '/api/projects/search', auth=env.get_credentials(), params=params)
    data = json.loads(resp.text)
    return data['components']
