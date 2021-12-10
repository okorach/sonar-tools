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
import sonarqube.aggregations as aggr
import sonarqube.utilities as util
import sonarqube.audit_rules as rules

_OBJECTS = {}

class Application(aggr.Aggregation):

    def __init__(self, key, endpoint, data=None):
        global _OBJECTS
        super().__init__(key=key, endpoint=endpoint)
        self._nbr_projects = None
        self._load(data)
        _OBJECTS[key] = self

    def __str__(self):
        return f"Application key '{self.key}'"

    def delete(self, api='applications/delete', params=None):
        _ = env.post('applications/delete', ctxt=self.env, params={'application': self.key})
        return True

    def _audit_empty(self, audit_settings):
        if not audit_settings['audit.applications'] or not audit_settings['audit.applications.empty']:
            util.logger.debug("Auditing applications is disabled, skipping...")
            return []
        return super()._audit_empty_aggregation(broken_rule=rules.RuleId.APPLICATION_EMPTY)

    def audit(self, audit_settings):
        util.logger.info("Auditing %s", str(self))
        return (
            self._audit_empty(audit_settings)
        )


def count(endpoint=None):
    resp = env.get('api/components/search_projects',
        params={'ps': 1, 'filter': 'qualifier%20=%20APP'}, ctxt=endpoint)
    data = json.loads(resp.text)
    return data['paging']['total']


def search(endpoint=None):
    app_list = {}
    edition = env.edition(ctxt=endpoint)
    if edition == 'community':
        util.logger.info("No applications in %s edition", edition)
    else:
        app_list = comp.search_objects('api/components/search_projects', params={'filter': 'qualifier = APP'},
        returned_field='components', object_class=Application, endpoint=endpoint)
    return app_list


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
