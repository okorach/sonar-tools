#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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
from sonar import aggregations, env, measures, options
import sonar.sqobject as sq
import sonar.utilities as util
from sonar.audit import rules

_OBJECTS = {}

LIST_API = 'views/list'
SEARCH_API = 'views/search'
GET_API = 'views/show'
MAX_PAGE_SIZE = 500
PORTFOLIO_QUALIFIER = 'VW'


class Portfolio(aggregations.Aggregation):

    def __init__(self, key, endpoint, data=None):
        super().__init__(key, endpoint)
        self._selection_mode = None
        self._load(data)
        _OBJECTS[key] = self

    def __str__(self):
        return f"Portfolio key '{self.key}'"

    def _load(self, data=None, api=None, key_name='key'):
        ''' Loads a portfolio object with contents of data '''
        super()._load(data=data, api=GET_API, key_name='key')
        self._selection_mode = data.get('selectionMode', None)

    def url(self):
        return f"{self.endpoint.url}/portfolio?id={self.key}"

    def selection_mode(self):
        if self._selection_mode is None:
            self._load()
        return self._selection_mode

    def get_components(self):
        resp = env.get('measures/component_tree', ctxt=self.endpoint,
            params={'component': self.key, 'metricKeys': 'ncloc', 'strategy': 'children', 'ps': 500})
        comp_list = {}
        for c in json.loads(resp.text)['components']:
            comp_list[c['key']] = c
        return comp_list

    def delete(self, api='views/delete', params=None):
        _ = env.post('views/delete', ctxt=self.endpoint, params={'key': self.key})
        return True

    def _audit_empty(self, audit_settings):
        if not audit_settings['audit.portfolios.empty']:
            util.logger.debug("Auditing empty portfolios is disabled, skipping...")
            return []
        return self._audit_empty_aggregation(broken_rule=rules.RuleId.PORTFOLIO_EMPTY)

    def _audit_singleton(self, audit_settings):
        if not audit_settings['audit.portfolios.singleton']:
            util.logger.debug("Auditing singleton portfolios is disabled, skipping...")
            return []
        return self._audit_singleton_aggregation(broken_rule=rules.RuleId.PORTFOLIO_SINGLETON)

    def audit(self, audit_settings):
        util.logger.info("Auditing %s", str(self))
        return (
            self._audit_empty(audit_settings) + self._audit_singleton(audit_settings)
        )

    def get_measures(self, metrics_list):
        m = measures.get(self.key, metrics_list, endpoint=self.endpoint)
        if 'ncloc' in m:
            self._ncloc = 0 if m['ncloc'] is None else int(m['ncloc'])
        return m

    def dump_data(self, **opts):
        data = {
            'type': 'portfolio',
            'key': self.key,
            'name': self.name,
            'ncloc': self.ncloc(),
        }
        if opts.get(options.WITH_URL, False):
            data['url'] = self.url()
        if opts.get(options.WITH_LAST_ANALYSIS, False):
            data['lastAnalysis'] = self.last_analysis()
        return data


def count(endpoint=None):
    return aggregations.count(api=SEARCH_API, endpoint=endpoint)


def search(endpoint=None, params=None):
    portfolio_list = {}
    edition = env.edition(ctxt=endpoint)
    if edition not in ('enterprise', 'datacenter'):
        util.logger.info("No portfolios in %s edition", edition)
    else:
        portfolio_list = sq.search_objects(
            api='views/search', params=params,
            returned_field='components', key_field='key', object_class=Portfolio, endpoint=endpoint)
    return portfolio_list


def get(key, sqenv=None):
    if key not in _OBJECTS:
        _ = Portfolio(key=key, endpoint=sqenv)
    return _OBJECTS[key]


def audit(audit_settings, endpoint=None):
    if not audit_settings['audit.portfolios']:
        util.logger.debug("Auditing portfolios is disabled, skipping...")
        return []
    util.logger.info("--- Auditing portfolios ---")
    plist = search(endpoint)
    problems = []
    for _, p in plist.items():
        problems += p.audit(audit_settings)
    return problems


def loc_csv_header(**kwargs):
    arr = ["# Portfolio Key"]
    if kwargs[options.WITH_NAME]:
        arr.append("Portfolio name")
    arr.append('LoC')
    if kwargs[options.WITH_LAST_ANALYSIS]:
        arr.append("Last Recomputation")
    if kwargs[options.WITH_URL]:
        arr.append("URL")
    return arr
