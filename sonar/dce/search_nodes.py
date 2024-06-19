#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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
"""

    Abstraction of the Search Node concept

"""

from typing import Union

import sonar.logging as log
import sonar.utilities as util
from sonar.audit import rules
import sonar.audit.problem as pb
from sonar.dce import nodes


_STORE_SIZE = "Store Size"
_ES_STATE = "Search State"


class SearchNode(nodes.DceNode):
    def __str__(self):
        return f"Search Node '{self.name()}'"

    def store_size(self):
        return util.int_memory(self.json[_ES_STATE][_STORE_SIZE])

    def name(self):
        return self.json["Name"]

    def node_type(self):
        return "SEARCH"

    def audit(self):
        log.info("%s: Auditing...", str(self))
        return self.__audit_store_size() + self.__audit_available_disk()

    def max_heap(self) -> Union[int, None]:
        if self.sif.edition() != "datacenter" and self.sif.version() < (9, 0, 0):
            return util.jvm_heap(self.sif.search_jvm_cmdline())
        try:
            sz = self.json[_ES_STATE]["JVM Heap Max"]
        except KeyError:
            log.warning("%s: Can't retrieve heap allocated, skipping this check", str(self))
            return None
        return int(float(sz.split(" ")[0]) * 1024)

    def __audit_store_size(self):
        log.info("%s: Auditing store size", str(self))
        es_heap = self.max_heap()
        if es_heap is None:
            log.warning("%s: No ES heap found, audit of ES head is skipped", str(self))
            rule = rules.get_rule(rules.RuleId.SETTING_ES_NO_HEAP)
            return [pb.Problem(broken_rule=rule, msg=rule.msg)]

        index_size = self.store_size()

        es_min = min(2 * index_size, es_heap < index_size + 1000)
        es_max = 32 * 1024
        es_pb = []
        if index_size is None:
            log.warning("%s: Search server store size missing, audit of ES index vs heap skipped...", str(self))
        elif index_size == 0:
            rule = rules.get_rule(rules.RuleId.DCE_ES_INDEX_EMPTY)
            es_pb = [pb.Problem(broken_rule=rule, msg=rule.msg.format(str(self)))]
        elif es_heap < es_min:
            rule = rules.get_rule(rules.RuleId.ES_HEAP_TOO_LOW)
            es_pb = [pb.Problem(broken_rule=rule, msg=rule.msg.format(str(self), es_heap, index_size))]
        elif es_heap > es_max:
            rule = rules.get_rule(rules.RuleId.ES_HEAP_TOO_HIGH)
            es_pb = [pb.Problem(broken_rule=rule, msg=rule.msg.format(str(self), es_heap, 32 * 1024))]
        else:
            log.info("%s: Search server memory %d MB is correct wrt to store size of %d MB", str(self), es_heap, index_size)
        return es_pb

    def __audit_available_disk(self) -> list[pb.Problem]:
        log.info("%s: Auditing available disk space", str(self))
        try:
            space_avail = util.int_memory(self.json[_ES_STATE]["Disk Available"])
        except ValueError:
            log.warning("%s: disk space available not found in SIF, skipping this check", str(self))
            return []
        store_size = self.store_size()
        log.info(
            "%s: Search server available disk size of %d MB and store size is %d MB",
            str(self),
            space_avail,
            store_size,
        )
        if space_avail < 10000:
            rule = rules.get_rule(rules.RuleId.LOW_FREE_DISK_SPACE_2)
            return [pb.Problem(broken_rule=rule, msg=rule.msg.format(str(self), space_avail // 1024))]
        elif store_size * 2 > space_avail:
            rule = rules.get_rule(rules.RuleId.LOW_FREE_DISK_SPACE_1)
            return [pb.Problem(broken_rule=rule, msg=rule.msg.format(str(self), space_avail // 1024, store_size // 1024))]

        return []


def __audit_index_balance(searchnodes):
    log.info("Auditing search nodes store size balance")
    nbr_search_nodes = len(searchnodes)
    for i in range(nbr_search_nodes):
        size_i = searchnodes[i].store_size()
        if size_i is None:
            continue
        for j in range(i + 1, nbr_search_nodes):
            size_j = searchnodes[j].store_size()
            if size_j is None or size_j == 0:
                continue
            store_ratio = size_i / size_j
            if store_ratio >= 0.5 or store_ratio <= 2:
                continue
            rule = rules.get_rule(rules.RuleId.DCE_ES_UNBALANCED_INDEX)
            return [pb.Problem(broken_rule=rule, msg=rule.msg.format())]
    log.info("Search nodes store size balance acceptable")
    return []


def audit(sub_sif, sif):
    log.info("Auditing search node(s)")
    searchnodes = []
    problems = []
    for n in sub_sif:
        searchnodes.append(SearchNode(n, sif))
    nbr_search_nodes = len(searchnodes)
    log.info("Auditing number of search nodes")
    if nbr_search_nodes < 3:
        rule = rules.get_rule(rules.RuleId.DCE_ES_CLUSTER_NOT_HA)
        problems.append(pb.Problem(broken_rule=rule, msg=rule.msg.format()))
    elif nbr_search_nodes > 3:
        if nbr_search_nodes % 2 == 0:
            rule = rules.get_rule(rules.RuleId.DCE_ES_CLUSTER_EVEN_NUMBER_OF_NODES)
        else:
            rule = rules.get_rule(rules.RuleId.DCE_ES_CLUSTER_WRONG_NUMBER_OF_NODES)
        problems.append(pb.Problem(broken_rule=rule, msg=rule.msg.format(nbr_search_nodes)))
    else:
        log.info("%d search nodes found, all OK", nbr_search_nodes)
    for i in range(nbr_search_nodes):
        problems += searchnodes[i].audit()
    problems += __audit_index_balance(searchnodes)
    return problems
