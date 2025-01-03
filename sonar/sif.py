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

    Abstraction of the SonarQube System Info File (or Support Info File) concept

"""

import datetime
import re
from typing import Optional

import sonar.logging as log
import sonar.utilities as util
from sonar.util import types
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem
import sonar.sif_node as sifn

import sonar.dce.app_nodes as appnodes
import sonar.dce.search_nodes as searchnodes

_APP_NODES = "Application Nodes"
_ES_NODES = "Search Nodes"
_SYSTEM = "System"
_SETTINGS = "Settings"
_STATS = "Statistics"
_STORE_SIZE = "Store Size"
_SEARCH_STATE = "Search State"

_MIN_DATE_LOG4SHELL = datetime.datetime(2021, 12, 1)


class NotSystemInfo(Exception):
    """Exception for JSON not being a SIF"""

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message


class Sif(object):
    """Abstraction of SIF file"""

    def __init__(self, json_sif: dict[str, str], concerned_object: object = None) -> None:
        if not is_sysinfo(json_sif):
            log.critical("Provided JSON does not seem to be a system info")
            raise NotSystemInfo("JSON is not a system info nor a support info")
        self.json = json_sif
        self.concerned_object = concerned_object
        self._url = None

    def __str__(self) -> str:
        """str() implementation"""
        return str(self.concerned_object)

    def url(self) -> str:
        """Returns the SQ URL of the SQ instance represented by the SIF"""
        if not self._url:
            if self.concerned_object:
                self._url = self.concerned_object.url
            else:
                self._url = self.json.get("Settings", {}).get("sonar.core.serverBaseURL", "")
        return self._url

    def edition(self) -> Optional[str]:
        """Returns the edition of the SQ instance represented by the SIF"""
        ed = None
        for section in (_STATS, _SYSTEM, "License"):
            for subsection in ("edition", "Edition"):
                try:
                    ed = self.json[section][subsection]
                except KeyError:
                    pass
        if "Application Nodes" in self.json:
            log.debug("DCE edition detected from the presence in SIF of the 'Application Nodes' key")
            ed = "datacenter"
        if ed is None:
            log.warning("Could not find edition in SIF")
            return None

        # Old SIFs could return "Enterprise Edition"
        return util.edition_normalize(ed)

    def database(self) -> str:
        """Returns the databse engine of the SQ instance represented by the SIF"""
        if self.version() < (9, 7, 0):
            return self.json[_STATS]["database"]["name"]
        else:
            return self.json["Database"]["Database"]

    def plugins(self) -> dict[str, str]:
        """Returns plugins installed on the SQ instance represented by the SIF"""
        if self.version() < (9, 7, 0):
            return self.json[_STATS]["plugins"]
        else:
            return self.json["Plugins"]

    def license_type(self) -> Optional[str]:
        """Returns the SIF SQ license type (prod or test)"""
        if "License" not in self.json:
            return None
        elif "type" in self.json["License"]:
            return self.json["License"]["type"]
        return None

    def version(self) -> Optional[tuple[int, ...]]:
        """Returns the version of the SQ instance represented by the SIF"""
        try:
            return util.string_to_version(self.json["System"]["Version"])
        except KeyError:
            return None

    def server_id(self) -> Optional[str]:
        """Returns the Server ID of teh SQ instance represented by the SIF"""
        return self.__get_field("Server ID")

    def start_time(self) -> Optional[datetime.datetime]:
        """Returns the last start time of the SQ instance represented by the SIF"""
        try:
            return util.string_to_date(self.json[_SETTINGS]["sonar.core.startTime"]).replace(tzinfo=None)
        except KeyError:
            pass
        try:
            return util.string_to_date(self.json[_SYSTEM]["Start Time"]).replace(tzinfo=None)
        except KeyError:
            return None

    def store_size(self) -> Optional[int]:
        """Returns the store size (ES index size) of the SQ instance represented by the SIF"""
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

    def audit(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits a SIF"""
        log.info("Auditing System Info")
        problems = self.__audit_jdbc_url()
        log.debug("Edition = %s", self.edition())
        if self.edition() == "datacenter":
            log.info("DCE SIF audit")
            problems += self.__audit_dce_settings(audit_settings)
        else:
            problems += (
                sifn.audit_web(self, "Web process")
                + sifn.audit_ce(self, "CE process")
                + sifn.audit_plugins(self, "WebApp", audit_settings)
                + self.__audit_es_settings()
                + self.__audit_branch_use()
                + self.__audit_undetected_scm()
            )
        return problems

    def __audit_branch_use(self) -> list[Problem]:
        """Audits whether branch analysis is used or not"""
        if self.edition() == "community":
            return []
        log.info("Auditing usage of branch analysis")
        try:
            use_br = self.json[_STATS]["usingBranches"]
            if use_br:
                return []
            return [Problem(get_rule(RuleId.NOT_USING_BRANCH_ANALYSIS), self)]
        except KeyError:
            log.info("Branch usage information not in SIF, ignoring audit...")
            return []

    def __audit_undetected_scm(self) -> list[Problem]:
        """Audits a SIF for presence of projects with undetected SCM"""
        log.info("Auditing SCM integration")
        try:
            undetected_scm_count = sum([scm["count"] for scm in self.json[_STATS]["projectCountByScm"] if scm["scm"] == "undetected"])
            if undetected_scm_count > 0:
                return [Problem(get_rule(RuleId.SIF_UNDETECTED_SCM), self, undetected_scm_count)]
        except KeyError:
            log.info("SCM information not in SIF, ignoring audit...")
        return []

    def __get_field(self, name: str, node_type: str = _APP_NODES) -> Optional[str]:
        """Returns a particular field of the JSON"""
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

    def __process_cmdline(self, sq_process_name: str) -> Optional[str]:
        opts = [x.format(sq_process_name) for x in ("sonar.{}.javaOpts", "sonar.{}.javaAdditionalOpts")]
        if _SETTINGS in self.json:
            return f"{self.json[_SETTINGS][opts[1]].strip()} {self.json[_SETTINGS][opts[0]].strip()}".strip()
        return None

    def web_jvm_cmdline(self) -> Optional[str]:
        """Returns the web JVM cmd line"""
        return self.__process_cmdline("web")

    def ce_jvm_cmdline(self) -> Optional[str]:
        """Returns the CE JVM cmd line"""
        return self.__process_cmdline("ce")

    def search_jvm_cmdline(self) -> Optional[str]:
        """Returns the search JVM cmd line"""
        return self.__process_cmdline("search")

    def __audit_log4shell(self, jvm_settings: str, broken_rule: RuleId) -> list[Problem]:
        """Audits for the log4shell vulnerability"""
        # If SIF is older than 2022 don't audit for log4shell to avoid noise
        st_time = self.start_time()
        if not st_time or st_time > _MIN_DATE_LOG4SHELL:
            return []
        log.info("Auditing log4shell vulnerability fix")
        sq_version = self.version()
        if sq_version < (8, 9, 6) or ((9, 0, 0) <= sq_version < (9, 2, 4)):
            try:
                _ = jvm_settings.split(" ").index("-Dlog4j2.formatMsgNoLookups=true")
            except ValueError:
                return [Problem(get_rule(broken_rule), self)]
        return []

    def __audit_jdbc_url(self) -> list[Problem]:
        """Audits if JDBC URL points on another machine than localhost"""
        log.info("Auditing JDBC settings")
        stats = self.json.get(_SETTINGS)
        if stats is None:
            log.error("Can't verify Database settings in System Info File, was it corrupted or redacted ?")
            return []
        jdbc_url = stats.get("sonar.jdbc.url", None)
        if jdbc_url is None:
            return [Problem(get_rule(RuleId.SETTING_JDBC_URL_NOT_SET), self)]
        if re.search(r":(postgresql://|sqlserver://|oracle:thin:@)(localhost|127\.0+\.0+\.1)[:;/]", jdbc_url):
            lic = self.license_type()
            if lic == "PRODUCTION":
                return [Problem(get_rule(RuleId.DB_ON_SAME_HOST), self, jdbc_url)]
            log.info("JDBC URL %s is on localhost but this is not a production license. So be it!", jdbc_url)
        else:
            log.info("JDBC URL %s does not use localhost, all good!", jdbc_url)
        return []

    def __audit_dce_settings(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits DCE settings"""
        log.info("Auditing DCE settings")
        problems = []
        sq_edition = self.edition()
        if sq_edition is None:
            log.error("Can't verify edition in System Info File (2_), was it corrupted or redacted ?")
            return problems
        if sq_edition != "datacenter":
            log.info("Not a Data Center Edition, skipping DCE checks")
            return problems
        if _APP_NODES in self.json:
            problems += appnodes.audit(self.json[_APP_NODES], self, audit_settings=audit_settings)
        else:
            log.info("Sys Info too old (pre-8.9), can't check plugins")

        if _ES_NODES in self.json:
            problems += searchnodes.audit(self.json[_ES_NODES], self, audit_settings)
        else:
            log.info("Sys Info too old (pre-8.9), can't check plugins")
        return problems

    def __audit_es_settings(self) -> list[Problem]:
        """Audits ES settings"""
        log.info("Auditing Search Server settings")
        problems = []
        jvm_cmdline = self.search_jvm_cmdline()
        if jvm_cmdline is None:
            log.warning("Can't retrieve search JVM command line, heap and logshell checks skipped")
            return []
        es_ram = util.jvm_heap(jvm_cmdline)
        index_size = self.store_size()

        if index_size is None:
            log.warning("Search server index size is missing. Audit of ES heap vs index size is skipped...")
        elif es_ram is None:
            problems.append(Problem(get_rule(RuleId.SETTING_ES_NO_HEAP), self))
        elif es_ram < 2 * index_size and es_ram < index_size + 1000:
            problems.append(Problem(get_rule(RuleId.ES_HEAP_TOO_LOW), self, "ES", es_ram, index_size))
        elif es_ram > 32 * 1024:
            problems.append(Problem(get_rule(RuleId.ES_HEAP_TOO_HIGH), self, "ES", es_ram, 32 * 1024))
        else:
            log.debug("Search server memory %d MB is correct wrt to index size of %d MB", es_ram, index_size)
        problems += self.__audit_log4shell(jvm_cmdline, RuleId.LOG4SHELL_ES)
        return problems


def is_sysinfo(sysinfo: dict[str, str]) -> bool:
    """Returns whether a JSON is a system info file or support info file"""
    return sum(1 for key in (_SETTINGS, _SYSTEM, "Database", "License") if key in sysinfo) >= 2
