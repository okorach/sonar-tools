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

    Abstraction of the SonarQube System Info File (or Support Info File) concept

"""

import datetime
import re
from dateutil.relativedelta import relativedelta
import sonar.utilities as util

from sonar.audit import rules, types, severities
import sonar.audit.problem as pb

import sonar.dce.app_nodes as appnodes
import sonar.dce.search_nodes as searchnodes

_RELEASE_DATE_6_7 = datetime.datetime(2017, 11, 8) + relativedelta(months=+6)
_RELEASE_DATE_7_9 = datetime.datetime(2019, 7, 1) + relativedelta(months=+6)
_RELEASE_DATE_8_9 = datetime.datetime(2021, 5, 4) + relativedelta(months=+6)

_APP_NODES = "Application Nodes"
_ES_NODES = "Search Nodes"
_SYSTEM = "System"
_SETTINGS = "Settings"
_STATS = "Statistics"
_STORE_SIZE = "Store Size"
_SEARCH_STATE = "Search State"

_JVM_OPTS = ("sonar.{}.javaOpts", "sonar.{}.javaAdditionalOpts")

_MIN_DATE_LOG4SHELL = datetime.datetime(2021, 12, 1)


class NotSystemInfo(Exception):
    def __init__(self, message):
        super().__init__()
        self.message = message


class Sif:
    def __init__(self, json_sif, concerned_object=None):
        if not is_sysinfo(json_sif):
            util.logger.critical("Provided JSON does not seem to be a system info")
            raise NotSystemInfo("JSON is not a system info nor a support info")
        self.json = json_sif
        self.concerned_object = concerned_object
        self._url = None

    def url(self):
        if not self._url:
            if self.concerned_object:
                self._url = self.concerned_object.url
            else:
                self._url = self.json.get("Settings", {}).get("sonar.core.serverBaseURL", "")
        return self._url

    def edition(self):
        try:
            ed = self.json[_STATS]["edition"]
        except KeyError:
            try:
                ed = self.json["License"]["edition"]
            except KeyError:
                try:
                    # FIXME: Can't get edition in SIF of SonarQube 9.7+, this is an unsolvable problem
                    ed = self.json["edition"]
                except KeyError:
                    return ""
        # Old SIFs could return "Enterprise Edition"
        return ed.split(" ")[0].lower()

    def database(self):
        if self.version() < (9, 7, 0):
            return self.json[_STATS]["database"]["name"]
        else:
            return self.json["Database"]["Database"]

    def plugins(self):
        if self.version() < (9, 7, 0):
            return self.json[_STATS]["plugins"]
        else:
            return self.json["Plugins"]

    def license_type(self):
        if "License" not in self.json:
            return None
        elif "type" in self.json["License"]:
            return self.json["License"]["type"]
        return None

    def version(self, digits=3, as_string=False):
        sif_v = self.__get_field("Version")
        if sif_v is None:
            return None

        split_version = sif_v.split(".")
        if as_string:
            return ".".join(split_version[0:digits])
        else:
            return tuple(int(n) for n in split_version[0:digits])

    def server_id(self):
        return self.__get_field("Server ID")

    def start_time(self):
        try:
            return util.string_to_date(self.json[_SETTINGS]["sonar.core.startTime"]).replace(tzinfo=None)
        except KeyError:
            pass
        try:
            return util.string_to_date(self.json[_SYSTEM]["Start Time"]).replace(tzinfo=None)
        except KeyError:
            return None

    def store_size(self):
        setting = None
        try:
            setting = self.json[_SEARCH_STATE][_STORE_SIZE]
        except KeyError:
            try:
                for v in self.json["Elasticsearch"]["Nodes"].values():
                    if _STORE_SIZE in v:
                        setting = v[_STORE_SIZE]
                        break
            except KeyError:
                pass
        if setting is None:
            return None
        return util.int_memory(setting)

    def audit(self, audit_settings):
        util.logger.info("Auditing System Info")
        problems = self.__audit_jdbc_url() + self.__audit_web_settings(audit_settings)
        if self.edition() == "datacenter":
            problems += self.__audit_dce_settings()
        else:
            problems += (
                self.__audit_ce_settings()
                + self.__audit_background_tasks()
                + self.__audit_es_settings()
                + self.__audit_log_level()
                + self.__audit_version()
                + self.__audit_branch_use()
                + self.__audit_undetected_scm()
            )
        return problems

    def __audit_branch_use(self):
        if self.edition() == "community":
            return []
        util.logger.info("Auditing usage of branch analysis")
        try:
            use_br = self.json[_STATS]["usingBranches"]
            if use_br:
                return []
            rule = rules.get_rule(rules.RuleId.NOT_USING_BRANCH_ANALYSIS)
            return [pb.Problem(rule.type, rule.severity, rule.msg, concerned_object=self)]
        except KeyError:
            util.logger.info("Branch usage information not in SIF, ignoring audit...")
            return []

    def __audit_undetected_scm(self):
        util.logger.info("Auditing SCM integration")
        try:
            scm_count, undetected_scm_count = 0, 0
            for scm in self.json[_STATS]["projectCountByScm"]:
                scm_count += scm["count"]
                if scm["scm"] == "undetected":
                    undetected_scm_count = scm["count"]
            if undetected_scm_count == 0:
                return []
            rule = rules.get_rule(rules.RuleId.UNDETECTED_SCM)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(undetected_scm_count), concerned_object=self)]
        except KeyError:
            util.logger.info("SCM information not in SIF, ignoring audit...")
            return []

    def __get_field(self, name, node_type=_APP_NODES):
        if _SYSTEM in self.json and name in self.json[_SYSTEM]:
            return self.json[_SYSTEM][name]
        elif "SonarQube" in self.json and name in self.json["SonarQube"]:
            return self.json["SonarQube"][name]
        elif node_type in self.json:
            for node in self.json[node_type]:
                try:
                    return node[_SYSTEM][name]
                except KeyError:
                    pass
        return None

    def __process_cmdline(self, process):
        opts = [x.format(process) for x in _JVM_OPTS]
        if _SETTINGS in self.json:
            return self.json[_SETTINGS][opts[1]] + " " + self.json[_SETTINGS][opts[0]]
        else:
            return None

    def web_jvm_cmdline(self):
        return self.__process_cmdline("web")

    def ce_jvm_cmdline(self):
        return self.__process_cmdline("ce")

    def search_jvm_cmdline(self):
        return self.__process_cmdline("search")

    def __eligible_to_log4shell_check(self):
        st_time = self.start_time()
        if st_time is None:
            return False
        return st_time > _MIN_DATE_LOG4SHELL

    def __audit_log4shell(self, jvm_settings, broken_rule):
        # If SIF is older than 2022 don't audit for log4shell to avoid noise
        if not self.__eligible_to_log4shell_check():
            return []

        util.logger.debug("Auditing log4shell vulnerability fix")
        sq_version = self.version()
        if sq_version < (8, 9, 6) or ((9, 0, 0) <= sq_version < (9, 2, 4)):
            for s in jvm_settings.split(" "):
                if s == "-Dlog4j2.formatMsgNoLookups=true":
                    return []
            rule = rules.get_rule(broken_rule)
            return [pb.Problem(rule.type, rule.severity, rule.msg, concerned_object=self)]
        return []

    def __audit_jdbc_url(self):
        util.logger.info("Auditing JDBC settings")
        problems = []
        stats = self.json.get(_SETTINGS)
        if stats is None:
            util.logger.error("Can't verify Database settings in System Info File, was it corrupted or redacted ?")
            return problems
        jdbc_url = stats.get("sonar.jdbc.url", None)
        util.logger.debug("JDBC URL = %s", str(jdbc_url))
        if jdbc_url is None:
            rule = rules.get_rule(rules.RuleId.SETTING_JDBC_URL_NOT_SET)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg, concerned_object=self))
        elif re.search(
            r":(postgresql://|sqlserver://|oracle:thin:@)(localhost|127\.0+\.0+\.1)[:;/]",
            jdbc_url,
        ):
            lic = self.license_type()
            if lic == "PRODUCTION":
                rule = rules.get_rule(rules.RuleId.SETTING_DB_ON_SAME_HOST)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(jdbc_url), concerned_object=self))
        return problems

    def __audit_dce_settings(self):
        util.logger.info("Auditing DCE settings")
        problems = []
        if self.version() < (9, 7, 0):
            stats = self.json.get(_STATS)
        else:
            stats = self.json
        if stats is None:
            util.logger.error("Can't verify edition in System Info File, was it corrupted or redacted ?")
            return problems
        sq_edition = stats.get("edition", None)
        if sq_edition is None:
            util.logger.error("Can't verify edition in System Info File, was it corrupted or redacted ?")
            return problems
        if sq_edition != "datacenter":
            util.logger.info("Not a Data Center Edition, skipping DCE checks")
            return problems
        if _APP_NODES in self.json:
            problems += appnodes.audit(self.json[_APP_NODES], self)
        else:
            util.logger.info("Sys Info too old (pre-8.9), can't check plugins")

        if _ES_NODES in self.json:
            problems += searchnodes.audit(self.json[_ES_NODES], self)
        else:
            util.logger.info("Sys Info too old (pre-8.9), can't check plugins")
        return problems

    def __audit_log_level(self):
        util.logger.debug("Auditing log levels")
        log_level = self.__get_field("Web Logging")
        if log_level is None:
            return []
        log_level = log_level["Logs Level"]
        if log_level not in ("DEBUG", "TRACE"):
            return []
        if log_level == "TRACE":
            return [
                pb.Problem(
                    types.Type.PERFORMANCE,
                    severities.Severity.CRITICAL,
                    "Log level set to TRACE, this does very negatively affect platform performance, reverting to INFO is required",
                    concerned_object=self,
                )
            ]
        if log_level == "DEBUG":
            return [
                pb.Problem(
                    types.Type.PERFORMANCE,
                    severities.Severity.HIGH,
                    "Log level is set to DEBUG, this may affect platform performance, reverting to INFO is recommended",
                    concerned_object=self,
                )
            ]
        return []

    def __audit_version(self):
        st_time = self.start_time()
        if st_time is None:
            util.logger.warning("SIF date is not available, skipping audit on SonarQube version (aligned with LTS)...")
            return []
        sq_version = self.version()
        if (
            (st_time > _RELEASE_DATE_6_7 and sq_version < (6, 7, 0))
            or (st_time > _RELEASE_DATE_7_9 and sq_version < (7, 9, 0))
            or (st_time > _RELEASE_DATE_8_9 and sq_version < (8, 9, 0))
        ):
            rule = rules.get_rule(rules.RuleId.BELOW_LTS)
            return [pb.Problem(rule.type, rule.severity, rule.msg, concerned_object=self)]
        return []

    def __audit_web_settings(self, audit_settings):
        util.logger.debug("Auditing Web settings")
        problems = []
        jvm_cmdline = self.web_jvm_cmdline()
        if jvm_cmdline is None:
            util.logger.warning("Can't retrieve web JVM command line, skipping heap and log4shell audits...")
            return []
        web_ram = util.jvm_heap(jvm_cmdline)
        min_heap = audit_settings.get("audit.web.heapMin", 1024)
        max_heap = audit_settings.get("audit.web.heapMax", 2048)
        if web_ram is None:
            rule = rules.get_rule(rules.RuleId.SETTING_WEB_NO_HEAP)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg, concerned_object=self))
        elif web_ram < min_heap or web_ram > max_heap:
            rule = rules.get_rule(rules.RuleId.SETTING_WEB_HEAP)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(web_ram, 1024, 2048), concerned_object=self))
        else:
            util.logger.debug(
                "sonar.web.javaOpts -Xmx memory setting value is %d MB, within the recommended range [1024-2048]",
                web_ram,
            )

        problems += self.__audit_log4shell(jvm_cmdline, rules.RuleId.LOG4SHELL_WEB)
        return problems

    def __audit_ce_settings(self):
        util.logger.info("Auditing CE settings")
        problems = []
        jvm_cmdline = self.ce_jvm_cmdline()
        if jvm_cmdline is None:
            util.logger.warning("Can't retrieve CE JVM command line, heap and logshell checks skipped")
            return []
        ce_ram = util.jvm_heap(jvm_cmdline)
        ce_tasks = self.__get_field("Compute Engine Tasks")
        if ce_tasks is None:
            return []
        ce_workers = ce_tasks["Worker Count"]
        MAX_WORKERS = 4
        if ce_workers > MAX_WORKERS:
            rule = rules.get_rule(rules.RuleId.SETTING_CE_TOO_MANY_WORKERS)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_workers, MAX_WORKERS), concerned_object=self))
        else:
            util.logger.debug(
                "%d CE workers configured, correct compared to the max %d recommended",
                ce_workers,
                MAX_WORKERS,
            )

        if ce_ram is None:
            rule = rules.get_rule(rules.RuleId.SETTING_CE_NO_HEAP)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg, concerned_object=self))
        elif ce_ram < 512 * ce_workers or ce_ram > 2048 * ce_workers:
            rule = rules.get_rule(rules.RuleId.SETTING_CE_HEAP)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_ram, 512, 2048, ce_workers), concerned_object=self))
        else:
            util.logger.debug(
                "sonar.ce.javaOpts -Xmx memory setting value is %d MB, within recommended range ([512-2048] x %d workers)",
                ce_ram,
                ce_workers,
            )

        problems += self.__audit_log4shell(jvm_cmdline, rules.RuleId.LOG4SHELL_CE)
        return problems

    def __audit_background_tasks(self):
        util.logger.debug("Auditing CE background tasks")
        problems = []
        ce_tasks = self.__get_field("Compute Engine Tasks")
        if ce_tasks is None:
            return []
        ce_success = ce_tasks["Processed With Success"]
        ce_error = ce_tasks["Processed With Error"]
        if ce_success == 0 and ce_error == 0:
            failure_rate = 0
        else:
            failure_rate = ce_error / (ce_success + ce_error)
        if ce_error > 10 and failure_rate > 0.01:
            rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_FAILURE_RATE_HIGH)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(int(failure_rate * 100)), concerned_object=self))
        else:
            util.logger.debug(
                "Number of failed background tasks (%d), and failure rate %d%% is OK",
                ce_error,
                int(failure_rate * 100),
            )

        ce_pending = ce_tasks["Pending"]
        if ce_pending > 100:
            rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_PENDING_QUEUE_VERY_LONG)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_pending), concerned_object=self))
        elif ce_pending > 20 and ce_pending > (10 * ce_tasks["Worker Count"]):
            rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_PENDING_QUEUE_LONG)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_pending), concerned_object=self))
        else:
            util.logger.debug("Number of pending background tasks (%d) is OK", ce_pending)
        return problems

    def __audit_es_settings(self):
        util.logger.info("Auditing Search Server settings")
        problems = []
        jvm_cmdline = self.search_jvm_cmdline()
        if jvm_cmdline is None:
            util.logger.warning("Can't retrieve search JVM command line, heap and logshell checks skipped")
            return []
        es_ram = util.jvm_heap(jvm_cmdline)
        index_size = self.store_size()

        if index_size is None:
            util.logger.warning("Search server index size is missing. Audit of ES heap vs index size is skipped...")
        elif es_ram is None:
            rule = rules.get_rule(rules.RuleId.SETTING_ES_NO_HEAP)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg, concerned_object=self))
        elif es_ram < 2 * index_size and es_ram < index_size + 1000:
            rule = rules.get_rule(rules.RuleId.SETTING_ES_HEAP)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(es_ram, index_size), concerned_object=self))
        else:
            util.logger.debug(
                "Search server memory %d MB is correct wrt to index size of %d MB",
                es_ram,
                index_size,
            )
        problems += self.__audit_log4shell(jvm_cmdline, rules.RuleId.LOG4SHELL_ES)
        return problems


def is_sysinfo(sysinfo):
    counter = 0
    for key in (_SETTINGS, _SYSTEM, "Database", "License"):
        if key in sysinfo:
            counter += 1
    return counter >= 2
