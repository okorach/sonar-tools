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
from sonarqube import aggregations, env
import sonarqube.utilities as util
import sonarqube.audit_rules as rules

_OBJECTS = {}

LIST_API = 'views/list'
SEARCH_API = 'views/search'
GET_API = 'views/show'
MAX_PAGE_SIZE = 500
PORTFOLIO_QUALIFIER = 'VW'


class Portfolio(aggregations.Aggregation):

    def __init__(self, key, endpoint, data=None):
        global _OBJECTS
        super().__init__(key=key, endpoint=endpoint)
        self._selection_mode = None
        self._load(data)
        _OBJECTS[key] = self

    def __str__(self):
        return f"Portfolio key '{self.key}'"

    def _load(self, data=None, api=None, key_name='key'):
        ''' Loads a portfolio object with contents of data '''
        super()._load(data=data, api=GET_API, key_name='key')
        self._selection_mode = data.get('selectionMode', None)

    def selection_mode(self):
        if self._selection_mode is None:
            self._load()
        return self._selection_mode

    def get_components(self):
        resp = env.get('measures/component_tree', ctxt=self.env,
            params={'component': self.key, 'metricKeys': 'ncloc', 'strategy': 'children', 'ps': 500})
        comp_list = {}
        for c in json.loads(resp.text)['components']:
            comp_list[c['key']] = c
        return comp_list

    def delete(self, api='views/delete', params=None):
        _ = env.post('views/delete', ctxt=self.env, params={'key': self.key})
        return True

    def _audit_empty(self, audit_settings):
        if not audit_settings['audit.portfolios'] or not audit_settings['audit.portfolios.empty']:
            util.logger.debug("Auditing portfolios is disabled, skipping...")
            return []
        return self._audit_empty_aggregation(broken_rule=rules.RuleId.PORTFOLIO_EMPTY)

    def audit(self, audit_settings):
        util.logger.info("Auditing %s", str(self))
        return (
            self._audit_empty(audit_settings)
        )


def count(endpoint=None):
    return aggregations.count(api=SEARCH_API, endpoint=endpoint)


def search(endpoint=None):
    portfolio_list = {}
    edition = env.edition(ctxt=endpoint)
    if edition not in ('enterprise', 'datacenter'):
        util.logger.info("No portfolios in %s edition", edition)
    else:
        resp = env.get(LIST_API, ctxt=endpoint)
        data = json.loads(resp.text)
        for p in data['views']:
            if p['qualifier'] == 'VW':
                portfolio_list[p['key']] = Portfolio(p['key'], endpoint=endpoint, data=p)
    return portfolio_list


def get(key, sqenv=None):
    global _OBJECTS
    if key not in _OBJECTS:
        _OBJECTS[key] = Portfolio(key=key, endpoint=sqenv)
    return _OBJECTS[key]


def audit(audit_settings, endpoint=None):
    plist = search(endpoint)
    problems = []
    for _, p in plist.items():
        problems += p.audit(audit_settings)
    return problems
