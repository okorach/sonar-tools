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

    Parent class of applications and portfolios

'''
import json
from sonarqube import env
import sonarqube.components as comp
import sonarqube.utilities as util
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb

class Aggregation(comp.Component):

    def __init__(self, key, endpoint, data=None):
        super().__init__(key=key, sqenv=endpoint)
        self._id = None
        self._name = None
        self._visibility = None
        self._ncloc = None
        self._nbr_projects = None

    def _load(self, data=None, api=None, key_name='key'):
        ''' Loads an aggregation object with contents of data '''
        if data is None:
            resp = env.get(api, ctxt=self.env, params={key_name: self.key})
            data = json.loads(resp.text)
        self._id = self.key
        self._name = data.get('name', None)
        self._visibility = data.get('visibility', None)

    def name(self):
        if self._name is None:
            self._load()
        return self._name

    def visibility(self):
        if self._visibility is None:
            self._load()
        return self._visibility

    def nbr_projects(self):
        if self._nbr_projects is None:
            data = json.loads(env.get('measures/component', ctxt=self.env,
                params={'component': self.key, 'metricKeys': 'projects,ncloc'}).text)['component']['measures']
            for m in data:
                if m['metric'] == 'projects':
                    self._nbr_projects = int(m['value'])
                elif m['metric'] == 'ncloc':
                    self._ncloc = int(m['value'])
        return self._nbr_projects

    def _audit_empty_aggregation(self, broken_rule):
        problems = []
        n = self.nbr_projects()
        if n in (None, 0):
            rule = rules.get_rule(broken_rule)
            msg = rule.msg.format(str(self))
            util.logger.warning(msg)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        else:
            util.logger.debug("%s has %d projects", str(self), n)

        return problems


def count(api, params=None, endpoint=None):
    if params is None:
        params = {}
    params['ps'] = 1
    resp = env.get(api, params=params, ctxt=endpoint)
    data = json.loads(resp.text)
    return data['paging']['total']
