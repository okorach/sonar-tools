#
# sonar-tools
# Copyright (C) 2019-2021 Olivier Korach
# mailto:olivier.korach AT gmail DOT com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
'''

    Abstraction of the SonarQube "component" concept

'''

import json
import sonarqube.sqobject as sq
import sonarqube.utilities as util
import sonarqube.env as env
import sonarqube.measures as measures


class Component(sq.SqObject):

    def __init__(self, key, sqenv=None, data=None):
        super().__init__(key, sqenv)
        self._name = None
        self.id = None
        self.qualifier = None
        self.path = None
        self.language = None
        self.nbr_issues = None
        self._ncloc = None
        if data is not None:
            self.__load__(data)

    def __load__(self, data):
        self.id = data.get('id', None)
        self._name = data.get('name', None)
        self.qualifier = data.get('qualifier', None)
        self.path = data.get('path', None)
        self.language = data.get('language', None)

    def get_subcomponents(self, strategy='children', with_issues=False):
        parms = {'component': self.key, 'strategy': strategy, 'ps': 1,
                 'metricKeys': 'bugs,vulnerabilities,code_smells,security_hotspots'}
        resp = env.get('measures/component_tree', params=parms, ctxt=self.env)
        data = json.loads(resp.text)
        nb_comp = data['paging']['total']
        util.logger.debug("Found %d subcomponents to %s", nb_comp, self.key)
        nb_pages = (nb_comp + 500 - 1)//500
        comp_list = {}
        parms['ps'] = 500
        for page in range(nb_pages):
            parms['p'] = page + 1
            resp = env.get('measures/component_tree', params=parms, ctxt=self.env)
            data = json.loads(resp.text)
            for d in data['components']:
                issues = 0
                for m in d['measures']:
                    issues += int(m['value'])
                if with_issues and issues == 0:
                    util.logger.debug("Subcomponent %s has 0 issues, skipping", d['key'])
                    continue
                comp_list[d['key']] = Component(key=d['key'], sqenv=self.env, data=d)
                comp_list[d['key']].nbr_issues = issues
                util.logger.debug("Component %s has %d issues", d['key'], issues)
        return comp_list

    def get_number_of_filtered_issues(self, params):
        import sonarqube.issues as issues
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
        import sonarqube.issues as issues
        return issues.get_oldest_issue(endpoint=self.env, params={'componentKeys': self.key})

    def get_newest_issue_date(self):
        ''' Returns the newest date of all issues found '''
        import sonarqube.issues as issues
        return issues.get_newest_issue(endpoint=self.env, params={'componentKeys': self.key})

    def get_issues(self):
        import sonarqube.issues as issues
        issue_list = issues.search(endpoint=self.env, params={'componentKeys': self.key})
        self.nbr_issues = len(issue_list)
        return issue_list

    def get_measures(self, metric_list, branch=None, pr_id=None):
        return measures.component(component_key=self.key, metric_keys=','.join(metric_list),
            endpoint=self.env, branch=branch, pr_id=pr_id)

    def get_measure(self, metric, branch=None, pr_id=None, fallback=None):
        res = self.get_measures(metric_list=[metric], branch=branch, pr_id=pr_id)
        for key in res:
            if key == metric:
                return res[key]
        return fallback


def get_components(component_types, endpoint=None):
    resp = env.get('projects/search', params={'ps': 500, 'qualifiers': component_types}, ctxt=endpoint)
    data = json.loads(resp.text)
    return data['components']


def get_subcomponents(component_key, strategy='children', with_issues=False, endpoint=None):
    return Component(key=component_key, sqenv=endpoint).get_subcomponents(strategy=strategy, with_issues=with_issues)


def search_objects(api, params, returned_field, object_class, endpoint=None):
    params['ps'] = 500
    resp = env.get(api, params=params, ctxt=endpoint)
    data = json.loads(resp.text)
    if 'paging' in data['paging'] and 'total' in data['paging'] and data['paging']['total'] > 500:
        util.logger.critical("Pagination on applications search is not yet supported "
        "and there are more than 500 of them. Will return only 500 first objects")
    objects = {}
    for obj in data[returned_field]:
        objects[obj['key']] = object_class(obj['key'], endpoint=endpoint, data=obj)
    return objects
