#
# sonar-tools
# Copyright (C) 2021 Olivier Korach
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

    Abstraction of the SonarQube "application" concept

'''
import json
from sonarqube import env
import sonarqube.components as comp
import sonarqube.utilities as util
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb

_OBJECTS = {}

LIST_API = 'APP'
# SEARCH_API = 'projects/search'
GET_API = 'applications/show'
MAX_PAGE_SIZE = 500
PORTFOLIO_QUALIFIER = 'VW'


class Application(comp.Component):

    def __init__(self, key, endpoint, data=None):
        global _OBJECTS
        super().__init__(key=key, sqenv=endpoint)
        self.id = None
        self.name = None
        self.selection_mode = None
        self._visibility = None
        self.ncloc = None
        self._nbr_projects = None
        self.__load(data)
        _OBJECTS[key] = self

    def __str__(self):
        return f"Application key '{self.key}'"

    def __load(self, data=None):
        ''' Loads an application object with contents of data '''
        if data is None:
            resp = env.get(GET_API, ctxt=self.env, params={'key': self.key})
            data = json.loads(resp.text)
        self.id = data.get('key', None)
        self.name = data.get('name', None)
        self._visibility = data.get('visibility', None)

    def get_name(self):
        if self.name is None:
            self.__load()
        return self.name

    def visibility(self):
        if self._visibility is None:
            self.__load()
        return self._visibility

    def nbr_projects(self):
        if self._nbr_projects is None:
            data = json.loads(env.get('measures/component', ctxt=self.env,
                params={'component': self.key, 'metricKeys': 'projects,ncloc'}).text)['component']['measures']
            for m in data:
                if m['metric'] == 'projects':
                    self._nbr_projects = int(m['value'])
                elif m['metric'] == 'ncloc':
                    self.ncloc = int(m['value'])
        return self._nbr_projects

    def delete(self, api='applications/delete', params=None):
        _ = env.post('applications/delete', ctxt=self.env, params={'application': self.key})
        return True

    def __audit_projects(self, audit_settings):
        if not audit_settings['audit.applications'] or not audit_settings['audit.applications.empty']:
            util.logger.debug("Auditing applications is disabled, skipping...")
            return []
        problems = []
        n = self.nbr_projects()
        if n in (None, 0):
            rule = rules.get_rule(rules.RuleId.APPLICATION_EMPTY)
            msg = rule.msg.format(str(self))
            util.logger.warning(msg)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        else:
            util.logger.debug("%s has %d projects", str(self), n)

        return problems

    def audit(self, audit_settings):
        util.logger.info("Auditing %s", str(self))
        return (
            self.__audit_projects(audit_settings)
        )


def count(endpoint=None):
    resp = env.get('api/components/search_projects',
        params={'ps': 1, 'filter': 'qualifier%20=%20APP'}, ctxt=endpoint)
    data = json.loads(resp.text)
    return data['paging']['total']


def search(endpoint=None):
    objects = comp.search_objects('api/components/search_projects', params={'filter': 'qualifier = APP'},
        returned_field='components', object_class=Application, endpoint=endpoint)
    return objects


def get(key, sqenv=None):
    global _OBJECTS
    if key not in _OBJECTS:
        _OBJECTS[key] = Application(key=key, endpoint=sqenv)
    return _OBJECTS[key]


def audit(audit_settings, endpoint=None):
    objects_list = search(endpoint)
    problems = []
    for _, obj in objects_list.items():
        problems += obj.audit(audit_settings)
    return problems
