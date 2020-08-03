#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "component" concept

'''
import sys
import datetime
import json
import requests
import sonarqube.sqobject as sq
import sonarqube.env as env
import sonarqube.issues as issues
import sonarqube.measures as measures
import sonarqube.utilities as util

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

    def get_number_of_filtered_issues(self, **kwargs):
        kwargs['componentKey'] = self.key
        kwargs['ps'] = 1
        returned_data = issues.search(sqenv=self.env, **kwargs)
        return returned_data['total']

    def get_number_of_issues(self):
        ''' Returns number of issues of a component '''
        if self.nbr_issues is None:
            self.nbr_issues = self.get_number_of_filtered_issues(**{'componentKey': self.key})
        return self.nbr_issues

    def get_all_issues(self, **kwargs):
        return self.get_issues(**kwargs)

    def get_oldest_issue_date(self):
        ''' Returns the oldest date of all issues found '''
        return issues.get_oldest_issue(sqenv=self.env, **{'componentKeys': self.key})

    def get_newest_issue_date(self):
        ''' Returns the newest date of all issues found '''
        return issues.get_newest_issue(sqenv=self.env, **{'componentKeys': self.key})

    def __get_issues_by_dir__(self, **kwargs):
        issue_list = []
        subdirs = issues.get_facets(sqenv = self.env, facet = 'directories', **kwargs)
        util.logger.debug("Found %d subdirectories", len(subdirs))
        for subdir in subdirs:
            kwargs['directories'] = subdir['val']
            util.logger.debug("Searching issues in sub-component %s / directory %s", \
                self.key, kwargs['directories'])
            nbr_issues = self.get_number_of_filtered_issues(**kwargs)
            if nbr_issues < 10000:
                issue_list = issue_list + issues.search_all_issues(sqenv = self.env, **kwargs)
                continue
            subfiles = issues.get_facets(sqenv = self.env, facet = 'fileUuids', **kwargs)
            util.logger.debug("Found %d files", len(subfiles))
            for f in subfiles:
                kwargs['fileUuids'] = f['val']
                util.logger.debug("Searching issues in sub-component %s / directory %s / File %s", \
                    self.key, kwargs['directories'], kwargs['fileUuids'])
                issue_list = issue_list + issues.search_all_issues(sqenv = self.env, **kwargs)
        return issue_list

    def get_issues(self, **kwargs):
        kwargs['componentKeys'] = self.key
        util.logger.debug(str(kwargs))
        oldest = self.get_oldest_issue_date()
        if oldest is None:
            return []

        nbr_issues = self.get_number_of_filtered_issues(**kwargs)
        issue_list = []
        if nbr_issues <= 10000:
            issue_list = issues.search_all_issues(sqenv=self.env, **kwargs)
            for i in issue_list:
                util.logger.debug(i.to_csv())
        elif 'createdAfter' not in kwargs or 'createdBefore' not in kwargs:
            startdate = datetime.datetime.strptime(oldest, '%Y-%m-%dT%H:%M:%S%z')
            enddate = datetime.datetime.strptime(self.get_newest_issue_date(), '%Y-%m-%dT%H:%M:%S%z')
            kwargs['createdAfter']  = util.format_date(startdate)
            kwargs['createdBefore'] = util.format_date(enddate)
            issue_list = self.get_issues(**kwargs)
        elif kwargs['createdAfter'] != kwargs['createdBefore']:
            startdate = datetime.datetime.strptime(kwargs['createdAfter'], '%Y-%m-%d')
            enddate = datetime.datetime.strptime(kwargs['createdBefore'], '%Y-%m-%d')
            diffdays = abs((enddate - startdate).days)
            util.logger.debug("Too many issues, splitting date window [%s - %s] in 2", startdate, enddate)
            mid_date = startdate + datetime.timedelta(days=diffdays//2)
            kwargs['createdAfter']  = util.format_date(startdate)
            kwargs['createdBefore'] = util.format_date(mid_date)
            util.logger.debug("1st new window: [%s - %s]", kwargs['createdAfter'], kwargs['createdBefore'])
            issue_list = self.get_issues(**kwargs)
            if diffdays <= 1:
                mid_date = enddate
            else:
                mid_date = mid_date + datetime.timedelta(days=1)
            kwargs['createdAfter']  = util.format_date(mid_date)
            kwargs['createdBefore'] = util.format_date(enddate)
            util.logger.debug("2nd new window: [%s - %s]", kwargs['createdAfter'], kwargs['createdBefore'])
            issue_list = issue_list + self.get_issues(**kwargs)
        else:
            issue_list = self.__get_issues_by_dir__()

        util.logger.info("For component %s, %d issues found after filter", self.key, len(issue_list))
        return issue_list

    def get_measures(self, metric_list):
        return measures.component(component=self.key, metricKeys=','.join(metric_list), endpoint=self.env)

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
