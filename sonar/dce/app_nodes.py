#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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
import sonar.utilities as util
from sonar.audit import rules, severities, types
import sonar.audit.problem as pb
import sonar.dce.nodes as dce_nodes

_RELEASE_DATE_6_7 = datetime.datetime(2017, 11, 8) + relativedelta(months=+6)
_RELEASE_DATE_7_9 = datetime.datetime(2019, 7, 1) + relativedelta(months=+6)
_RELEASE_DATE_8_9 = datetime.datetime(2021, 5, 4) + relativedelta(months=+6)

_SYSTEM = "System"
_SETTINGS = "Settings"
_VERSION = "Version"


class AppNode(dce_nodes.DceNode):
    def __str__(self):
        return f"App Node '{self.name()}'"

    def plugins(self):
        self.json.get("Plugins", None)

    def health(self):
        return self.json.get("Health", "RED")

    def node_type(self):
        return "APPLICATION"

    def version(self, digits=3, as_string=False):
        if _SETTINGS in self.json:
            split_version = self.json[_SETTINGS][_VERSION].split(".")
        elif _SYSTEM in self.json and _VERSION in self.json[_SYSTEM]:
            split_version = self.json[_SYSTEM][_VERSION].split(".")
        else:
            return None
        try:
            if as_string:
                return ".".join(split_version[0:digits])
            else:
                return tuple(int(n) for n in split_version[0:digits])
        except ValueError:
            return None

    def log_level(self):
        if "Web Logging" in self.json:
            return self.json["Web Logging"]["Logs Level"]
        else:
            return None

    def name(self):
        return self.json["Name"]

    def audit(self):
        util.logger.info("Auditing %s", str(self))
        return (
            self.__audit_log_level()
            + self.__audit_official()
            + self.__audit_health()
            + self.__audit_version()
            + self.__audit_ce_settings()
            + self.__audit_background_tasks()
        )

    def __audit_log_level(self):
        util.logger.debug("Auditing log level")
        log_level = self.log_level()
        if log_level is None:
            util.logger.warning("%s: log level is missing, audit of log level is skipped...", str(self))
            return []
        if log_level not in ("DEBUG", "TRACE"):
            util.logger.info("Log level of '%s' is '%s', all good...", str(self), log_level)
            return []
        if log_level == "TRACE":
            return [
                pb.Problem(
                    types.Type.PERFORMANCE,
                    severities.Severity.CRITICAL,
                    f"Log level of {str(self)} set to TRACE, this does very negatively affect platform performance, " "reverting to INFO is required",
                )
            ]
        if log_level == "DEBUG":
            return [
                pb.Problem(
                    types.Type.PERFORMANCE,
                    severities.Severity.HIGH,
                    f"Log level of {str(self)} is set to DEBUG, this may affect platform performance, " "reverting to INFO is recommended",
                )
            ]
        util.logger.debug("%s: Node log level is %s", str(self), log_level)
        return []

    def __audit_health(self):
        if self.health() != dce_nodes.HEALTH_GREEN:
            rule = rules.get_rule(rules.RuleId.DCE_APP_NODE_NOT_GREEN)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(str(self), self.health()))]
        else:
            util.logger.debug("%s: Node health is %s", str(self), dce_nodes.HEALTH_GREEN)
            return []

    def __audit_official(self):
        if _SYSTEM not in self.json:
            util.logger.warning(
                "%s: Official distribution information missing, audit skipped...",
                str(self),
            )
            return []
        elif not self.json[_SYSTEM]["Official Distribution"]:
            rule = rules.get_rule(rules.RuleId.DCE_APP_NODE_UNOFFICIAL_DISTRO)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(str(self)))]
        else:
            util.logger.debug("%s: Node is official distribution", str(self))
            return []

    def __audit_version(self):
        sq_version = self.version()
        if sq_version is None:
            util.logger.warning("%s: Version information is missing, audit on node vresion is skipped...")
            return []
        st_time = self.sif.start_time()
        if (
            (st_time > _RELEASE_DATE_6_7 and sq_version < (6, 7, 0))
            or (st_time > _RELEASE_DATE_7_9 and sq_version < (7, 9, 0))
            or (st_time > _RELEASE_DATE_8_9 and sq_version < (8, 9, 0))
        ):
            rule = rules.get_rule(rules.RuleId.BELOW_LTS)
            return [pb.Problem(rule.type, rule.severity, rule.msg)]
        else:
            util.logger.debug(
                "%s: Version %s is correct wrt LTS",
                str(self),
                self.version(as_string=True),
            )
            return []

    def __audit_ce_settings(self):
        util.logger.info("Auditing CE settings")
        try:
            ce_workers = self.json["Compute Engine Tasks"]["Worker Count"]
        except KeyError:
            util.logger.warning(
                "%s: CE section missing from SIF, CE workers audit skipped...",
                str(self),
            )
            return []
        MAX_WORKERS = 2
        if ce_workers > MAX_WORKERS:
            rule = rules.get_rule(rules.RuleId.SETTING_CE_TOO_MANY_WORKERS)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(ce_workers, MAX_WORKERS))]
        else:
            util.logger.debug(
                "%s: %d CE workers configured, correct compared to the max %d recommended",
                str(self),
                ce_workers,
                MAX_WORKERS,
            )
            return []

    def __audit_background_tasks(self):
        util.logger.debug("Auditing CE background tasks")
        problems = []
        try:
            ce_tasks = self.json["Compute Engine Tasks"]
        except KeyError:
            util.logger.warning(
                "%s: CE section missing from SIF, background tasks audit skipped...",
                str(self),
            )
            return []

        ce_success = ce_tasks["Processed With Success"]
        ce_error = ce_tasks["Processed With Error"]
        failure_rate = 0
        if ce_success != 0 or ce_error != 0:
            failure_rate = ce_error / (ce_success + ce_error)
        if ce_error > 10 and failure_rate > 0.01:
            rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_FAILURE_RATE_HIGH)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(int(failure_rate * 100))))
        else:
            util.logger.debug(
                "Number of failed background tasks (%d), and failure rate %d%% is OK",
                ce_error,
                int(failure_rate * 100),
            )

        ce_pending = ce_tasks["Pending"]
        if ce_pending > 100:
            rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_PENDING_QUEUE_VERY_LONG)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_pending)))
        elif ce_pending > 20 and ce_pending > (10 * ce_tasks["Worker Count"]):
            rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_PENDING_QUEUE_LONG)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_pending)))
        else:
            util.logger.debug("Number of pending background tasks (%d) is OK", ce_pending)
        return problems


def audit(sub_sif, sif):
    nodes = []
    problems = []
    for n in sub_sif:
        nodes.append(AppNode(n, sif))
    if len(nodes) == 1:
        rule = rules.get_rule(rules.RuleId.DCE_APP_CLUSTER_NOT_HA)
        return [pb.Problem(rule.type, rule.severity, rule.msg)]
    for i in range(len(nodes)):
        problems += nodes[i].audit()
        for j in range(i, len(nodes)):
            v1 = nodes[i].version()
            v2 = nodes[j].version()
            if v1 is not None and v2 is not None and v1 != v2:
                rule = rules.get_rule(rules.RuleId.DCE_DIFFERENT_APP_NODES_VERSIONS)
                problems.append(
                    pb.Problem(
                        rule.type,
                        rule.severity,
                        rule.msg.format(str(nodes[i]), str(nodes[j])),
                    )
                )
            if nodes[i].plugins() != nodes[j].plugins():
                rule = rules.get_rule(rules.RuleId.DCE_DIFFERENT_APP_NODES_PLUGINS)
                problems.append(
                    pb.Problem(
                        rule.type,
                        rule.severity,
                        rule.msg.format(str(nodes[i]), str(nodes[j])),
                    )
                )
    return problems
