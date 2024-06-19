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

    Abstraction of the App Node concept

"""

import datetime
from dateutil.relativedelta import relativedelta

import sonar.logging as log
import sonar.utilities as util
from sonar.audit import rules
import sonar.sif_node as sifn
import sonar.audit.problem as pb
import sonar.dce.nodes as dce_nodes

_RELEASE_DATE_6_7 = datetime.datetime(2017, 11, 8) + relativedelta(months=+6)
_RELEASE_DATE_7_9 = datetime.datetime(2019, 7, 1) + relativedelta(months=+6)
_RELEASE_DATE_8_9 = datetime.datetime(2021, 5, 4) + relativedelta(months=+6)

_SYSTEM = "System"


class AppNode(dce_nodes.DceNode):
    def __str__(self):
        return f"App Node '{self.name()}'"

    def plugins(self):
        self.json.get("Plugins", None)

    def health(self):
        return self.json.get("Health", "RED")

    def node_type(self):
        return "APPLICATION"

    def start_time(self) -> datetime.datetime:
        return self.sif.start_time()

    def version(self, digits=3, as_string=False):
        try:
            return util.string_to_version(self.json[_SYSTEM]["Version"], digits, as_string)
        except KeyError:
            return None

    def edition(self) -> str:
        self.sif.edition()

    def name(self):
        return self.json["Name"]

    def audit(self, audit_settings: dict[str, str] = None):
        log.info("Auditing %s", str(self))
        return (
            self.__audit_official()
            + self.__audit_health()
            + sifn.audit_web(self, f"{str(self)} Web process", self.json)
            + sifn.audit_ce(self, f"{str(self)} CE process", self.json)
        )

    def __audit_health(self):
        log.info("%s: Auditing node health", str(self))
        if self.health() != dce_nodes.HEALTH_GREEN:
            rule = rules.get_rule(rules.RuleId.DCE_APP_NODE_NOT_GREEN)
            return [pb.Problem(broken_rule=rule, msg=rule.msg.format(str(self), self.health()))]

        log.info("%s: Node health is %s", str(self), dce_nodes.HEALTH_GREEN)
        return []

    def __audit_official(self):
        if _SYSTEM not in self.json:
            log.warning(
                "%s: Official distribution information missing, audit skipped...",
                str(self),
            )
            return []
        elif not self.json[_SYSTEM]["Official Distribution"]:
            rule = rules.get_rule(rules.RuleId.DCE_APP_NODE_UNOFFICIAL_DISTRO)
            return [pb.Problem(broken_rule=rule, msg=rule.msg.format(str(self)))]
        else:
            log.debug("%s: Node is official distribution", str(self))
            return []


def audit(sub_sif: dict[str, str], sif_object: object, audit_settings: dict[str, str] = None) -> list[pb.Problem]:
    """Audits application nodes of a DCE instance

    :param dict sub_sif: The JSON subsection of the SIF pertaining to the App Nodes
    :param Sif sif: The Sif object
    :param dict audit_settings: Config settings for audit
    :return: List of Problems
    :rtype: list
    """
    if audit_settings is None:
        audit_settings = {}
    nodes = []
    problems = []
    for n in sub_sif:
        nodes.append(AppNode(n, sif_object))
    if len(nodes) == 1:
        rule = rules.get_rule(rules.RuleId.DCE_APP_CLUSTER_NOT_HA)
        return [pb.Problem(broken_rule=rule, msg=rule.msg)]
    for node_1 in nodes:
        problems += node_1.audit(audit_settings)
        for node_2 in nodes:
            v1 = node_1.version()
            v2 = node_2.version()
            if v1 is not None and v2 is not None and v1 != v2:
                rule = rules.get_rule(rules.RuleId.DCE_DIFFERENT_APP_NODES_VERSIONS)
                problems.append(pb.Problem(broken_rule=rule, msg=rule.msg.format(str(node_1), str(node_2))))
            if node_1.plugins() != node_2.plugins():
                rule = rules.get_rule(rules.RuleId.DCE_DIFFERENT_APP_NODES_PLUGINS)
                problems.append(pb.Problem(broken_rule=rule, msg=rule.msg.format(str(node_1), str(node_2))))
    return problems
