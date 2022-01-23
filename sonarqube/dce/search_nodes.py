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

    Abstraction of the Search Node concept

'''

import sonarqube.utilities as util
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb
import sonarqube.dce.nodes as dce_nodes

_STORE_SIZE = 'Store Size'
_ES_STATE = 'Search State'

class SearchNode(dce_nodes.DceNode):

    def __str__(self):
        return f"Search Node '{self.name()}'"

    def store_size(self):
        return self.json[_ES_STATE][_STORE_SIZE]

    def name(self):
        return self.json['Name']

    def node_type(self):
        return 'SEARCH'

    def __audit_store_size(self):
        es_ram = self.sif.get_memory(self.node_type())
        index_size = self.store_size()

        if es_ram is None:
            rule = rules.get_rule(rules.RuleId.SETTING_ES_NO_HEAP)
            return [pb.Problem(rule.type, rule.severity, rule.msg)]
        elif index_size is not None and es_ram < 2 * index_size and es_ram < index_size + 1000:
            rule = rules.get_rule(rules.RuleId.SETTING_ES_HEAP)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(es_ram, index_size))]
        else:
            util.logger.debug("Search server memory %d MB is correct wrt to index size of %d MB", es_ram, index_size)
            return []


    def audit(self):
        util.logger.info("Auditing %s", str(self))
        return (
            self.__audit_store_size()
        )


def audit(sub_sif, sif):
    nodes = []
    problems = []
    for n in sub_sif:
        nodes.append(SearchNode(n, sif))
    if len(nodes) < 3:
        rule = rules.get_rule(rules.RuleId.DCE_ES_CLUSTER_NOT_HA)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format()))
    for i in range(len(nodes)):
        problems += nodes[i].audit()
        for j in range(i+1, len(nodes)):
            store_ratio = nodes[i].store_size() / nodes[j].store_size()
            if store_ratio < 0.5 or store_ratio > 2:
                rule = rules.get_rule(rules.RuleId.DCE_ES_UNBALANCED_STORE)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(str(nodes[i]), str(nodes[j]))))
    return problems