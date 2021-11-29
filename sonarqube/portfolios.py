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

    Abstraction of the SonarQube "portfolio" concept

'''
import json
import sonarqube.env as env
import sonarqube.components as comp
import sonarqube.utilities as util
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb

PORTFOLIOS = {}

LIST_API = 'views/list'
SEARCH_API = 'views/search'
GET_API = 'views/show'
MAX_PAGE_SIZE = 500
PORTFOLIO_QUALIFIER = 'VW'


class Portfolio(comp.Component):

    def __init__(self, key, endpoint, data=None):
        super().__init__(key=key, sqenv=endpoint)
        self.id = None
        self.name = None
        self.selection_mode = None
        self.visibility = None
        self.permissions = None
        self.user_permissions = None
        self.group_permissions = None
        self.branches = None
        self.ncloc = None
        self._nbr_projects = None
        self.__load__(data)
        PORTFOLIOS[key] = self

    def __str__(self):
        return f"Portfolio key '{self.key}'"

    def __load__(self, data=None):
        ''' Loads a portfolio object with contents of data '''
        if data is None:
            resp = env.get(GET_API, ctxt=self.env, params={'key': self.key})
            data = json.loads(resp.text)
        self.id = data.get('key', None)
        self.name = data.get('name', None)
        self.visibility = data.get('visibility', None)
        self.selection_mode = data.get('selectionMode', None)

    def get_name(self):
        if self.name is None:
            self.__load__()
        return self.name

    def get_visibility(self):
        if self.visibility is None:
            self.__load__()
        return self.visibility

    def get_selection_mode(self):
        if self.selection_mode is None:
            self.__load__()
        return self.selection_mode

    def get_components(self):
        resp = env.get('measures/component_tree', ctxt=self.env,
            params={'component': self.key, 'metricKeys':'ncloc', 'strategy':'children', 'ps':500})
        comp_list = {}
        for c in json.loads(resp.text)['components']:
            comp_list[c['key']] = c
        return comp_list

    def nbr_projects(self):
        if self._nbr_projects is None:
            data = json.loads(env.get('measures/component', ctxt=self.env,
                params={'component': self.key, 'metricKeys':'projects,ncloc'}).text)['component']['measures']
            for m in data:
                if m['metric'] == 'projects':
                    self._nbr_projects = int(m['value'])
                elif m['metric'] == 'ncloc':
                    self.ncloc = int(m['value'])
        return self._nbr_projects

    def delete(self, api='views/delete', params=None):
        _ = env.post('views/delete', ctxt=self.env, params={'key': self.key})
        return True

    def __audit_projects(self, audit_settings):
        if not audit_settings['audit.portfolios'] or not audit_settings['audit.portfolios.empty']:
            util.logger.debug("Auditing portfolios is disabled, skipping...")
            return []
        problems = []
        n = self.nbr_projects()
        if n in (None, 0):
            rule = rules.get_rule(rules.RuleId.PORTFOLIO_EMPTY)
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
    resp = env.get(SEARCH_API, ctxt=endpoint, params={'ps':1})
    data = json.loads(resp.text)
    return data['paging']['total']


def search(endpoint=None):
    resp = env.get(LIST_API, ctxt=endpoint)
    data = json.loads(resp.text)
    plist = {}
    for p in data['views']:
        plist[p['key']] = Portfolio(p['key'], endpoint=endpoint, data=p)
    return plist


def get(key, sqenv=None):
    global PORTFOLIOS
    if key not in PORTFOLIOS:
        _ = Portfolio(key=key, endpoint=sqenv)
    return PORTFOLIOS[key]


def audit(audit_settings, endpoint=None):
    plist = search(endpoint)
    problems = []
    for _, p in plist.items():
        problems += p.audit(audit_settings)
    return problems
