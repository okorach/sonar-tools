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

    Abstraction of the SonarQube System Info File (or Support Info File) concept

'''

import datetime
from dateutil.relativedelta import relativedelta
import sonarqube.utilities as util
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb

_RELEASE_DATE_6_7 = datetime.datetime(2017, 11, 8) + relativedelta(months=+6)
_RELEASE_DATE_7_9 = datetime.datetime(2019, 7, 1) + relativedelta(months=+6)
_RELEASE_DATE_8_9 = datetime.datetime(2021, 5, 4) + relativedelta(months=+6)

_APP_NODES = 'Application Nodes'
_ES_NODES = 'Search Nodes'
_SYSTEM = 'System'
_STORE_SIZE = 'Store Size'
_ES_STATE = 'Search State'

_JVM_OPTS = ('sonar.{}.javaOpts', 'sonar.{}.javaAdditionalOpts')

class Sif:

    def __init__(self, json_sif):
        self.json_sif = json_sif

    def edition(self):
        return self.json_sif['Statistics']['edition']

    def database(self):
        return self.json_sif['Statistics']['database']['name']

    def plugins(self):
        return self.json_sif['Statistics']['plugins']

    def get_field(self, name, node_type=_APP_NODES):
        if _SYSTEM in self.json_sif and name in self.json_sif[_SYSTEM]:
            return self.json_sif[_SYSTEM][name]
        elif 'SonarQube' in self.json_sif and name in self.json_sif['SonarQube']:
            return self.json_sif['SonarQube'][name]
        elif node_type in self.json_sif:
            for node in self.json_sif[node_type]:
                try:
                    return node[_SYSTEM][name]
                except KeyError:
                    pass
        return None

    def get_first_live_node(self, node_type=_APP_NODES):
        #til.logger.debug('Searching LIVE node %s in %s', node_type, util.json_dump(sif))
        if node_type not in self.json_sif:
            return None
        i = 0
        for node in self.json_sif[node_type]:
            if (node_type == _APP_NODES and _SYSTEM in node) or \
            (node_type == _ES_NODES and _ES_STATE in node):
                return i
            i += 1
        return None

    def server_id(self):
        return self.get_field('Server ID')

    def start_time(self):
        try:
            return util.string_to_date(self.json_sif['Settings']['sonar.core.startTime']).replace(tzinfo=None)
        except KeyError:
            pass
        try:
            return util.string_to_date(self.json_sif[_SYSTEM]['Start Time']).replace(tzinfo=None)
        except KeyError:
            return None

    def license(self):
        if 'License' not in self.json_sif:
            return None
        elif 'type' in self.json_sif['License']:
            return self.json_sif['License']['type']
        return None

    def version(self, digits=3, as_string=False):
        sif_v = self.get_field('Version')
        if sif_v is None:
            return None

        split_version = sif_v.split('.')
        if as_string:
            return '.'.join(split_version[0:digits])
        else:
            return tuple(int(n) for n in split_version[0:digits])

    def process_settings(self, process):
        opts = [x.format(process) for x in _JVM_OPTS]
        return self.json_sif['Settings'][opts[1]] + " " + self.json_sif['Settings'][opts[0]]

    def web_settings(self):
        return self.process_settings('web')

    def ce_settings(self):
        return self.process_settings('ce')

    def search_settings(self):
        return self.process_settings('search')

    def _audit_version(self):
        st_time = self.start_time()
        sq_version = self.version()
        if st_time > _RELEASE_DATE_6_7 and sq_version < (6, 7, 0) or \
        st_time > _RELEASE_DATE_7_9 and sq_version < (7, 9, 0) or \
        st_time > _RELEASE_DATE_8_9 and sq_version < (8, 9, 0):
            rule = rules.get_rule(rules.RuleId.BELOW_LTS)
            return [pb.Problem(rule.type, rule.severity, rule.msg)]
        return []

    def audit(self):
        return (
            self._audit_version()
        )