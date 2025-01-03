#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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

from typing import Optional

import sonar.logging as log
from sonar.util import types
import sonar.utilities as util
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem
from sonar.dce import nodes


_STORE_SIZE = "Store Size"
_ES_STATE = "Search State"


class SearchNode(nodes.DceNode):
    """Abstraction of SonarQube DCE Search Node concept"""

    def __str__(self) -> str:
        """str() implementation"""
        return f"Search Node '{self.name()}'"

    def store_size(self) -> int:
        """Returns the store size in MB"""
        return util.int_memory(self.json[_ES_STATE][_STORE_SIZE])

    def name(self) -> str:
        """Returns the node name"""
        return self.json["Name"]

    def node_type(self) -> str:
        """Returns the node type"""
        return "SEARCH"

    def audit(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audit a DCE search node"""
        log.info("%s: Auditing...", str(self))
        return self.__audit_store_size() + self.__audit_available_disk()

    def max_heap(self) -> Optional[int]:
        """Returns the node max heap or None if not found"""
        if self.sif.edition() != "datacenter" and self.sif.version() < (9, 0, 0):
            return util.jvm_heap(self.sif.search_jvm_cmdline())
        try:
            sz = self.json[_ES_STATE]["JVM Heap Max"]
        except KeyError:
            log.warning("%s: Can't retrieve heap allocated, skipping this check", str(self))
            return None
        return int(float(sz.split(" ")[0]) * 1024)

    def __audit_store_size(self) -> list[Problem]:
        """Audits the search node store size vs heap allocated to ES"""
        log.info("%s: Auditing store size", str(self))
        es_heap = self.max_heap()
        if es_heap is None:
            log.warning("%s: No ES heap found, audit of ES head is skipped", str(self))
            return [Problem(get_rule(RuleId.SETTING_ES_NO_HEAP), self)]

        index_size = self.store_size()

        es_min = min(2 * index_size, es_heap < index_size + 1000)
        es_max = 32 * 1024
        es_pb = []
        if index_size is None:
            log.warning("%s: Search server store size missing, audit of ES index vs heap skipped...", str(self))
        elif index_size == 0:
            es_pb = [Problem(get_rule(RuleId.DCE_ES_INDEX_EMPTY), self, str(self))]
        elif es_heap < es_min:
            es_pb = [Problem(get_rule(RuleId.ES_HEAP_TOO_LOW), self, str(self), es_heap, index_size)]
        elif es_heap > es_max:
            es_pb = [Problem(get_rule(RuleId.ES_HEAP_TOO_HIGH), self, str(self), es_heap, 32 * 1024)]
        else:
            log.info("%s: Search server memory %d MB is correct wrt to store size of %d MB", str(self), es_heap, index_size)
        return es_pb

    def __audit_available_disk(self) -> list[Problem]:
        """Audits whether the node has enough free disk space"""
        log.info("%s: Auditing available disk space", str(self))
        try:
            space_avail = util.int_memory(self.json[_ES_STATE]["Disk Available"])
        except ValueError:
            log.warning("%s: disk space available not found in SIF, skipping this check", str(self))
            return []
        store_size = self.store_size()
        log.info("%s: Search server available disk size of %d MB and store size is %d MB", str(self), space_avail, store_size)
        if space_avail < 10000:
            return [Problem(get_rule(RuleId.LOW_FREE_DISK_SPACE_2), self, str(self), space_avail // 1024)]
        elif store_size * 2 > space_avail:
            return [Problem(get_rule(RuleId.LOW_FREE_DISK_SPACE_1), self, str(self), space_avail // 1024, store_size // 1024)]

        return []


def __audit_index_balance(searchnodes: list[SearchNode]) -> list[Problem]:
    """Audits whether ES index is decently balanced across search nodes"""
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
            return [Problem(get_rule(RuleId.DCE_ES_UNBALANCED_INDEX), "SearchNodes")]
    log.info("Search nodes store size balance acceptable")
    return []


def audit(sub_sif: dict[str, any], sif: dict[str, any], audit_settings: types.ConfigSettings) -> list[Problem]:
    """Audits search nodes of a DCE"""
    log.info("Auditing search node(s)")
    searchnodes = []
    problems = []
    for n in sub_sif:
        searchnodes.append(SearchNode(n, sif))
    nbr_search_nodes = len(searchnodes)
    log.info("Auditing number of search nodes")
    if nbr_search_nodes < 3:
        problems.append(Problem(get_rule(RuleId.DCE_ES_CLUSTER_NOT_HA), "ES Cluster"))
    elif nbr_search_nodes > 3:
        if nbr_search_nodes % 2 == 0:
            rule = get_rule(RuleId.DCE_ES_CLUSTER_EVEN_NUMBER_OF_NODES)
        else:
            rule = get_rule(RuleId.DCE_ES_CLUSTER_WRONG_NUMBER_OF_NODES)
        problems.append(Problem(rule, "ES Cluster", nbr_search_nodes))
    else:
        log.info("%d search nodes found, all OK", nbr_search_nodes)
    for i in range(nbr_search_nodes):
        problems += searchnodes[i].audit(audit_settings)
    problems += __audit_index_balance(searchnodes)
    return problems
