#
# sonar-tools
# Copyright (C) 2022 Olivier Korach
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

    Abstraction of the SonarQube "background task" concept

"""

import time
import datetime
import json
import re
from sonar.audit import rules, problem
import sonar.sqobject as sq
import sonar.utilities as util

SUCCESS = "SUCCESS"
PENDING = "PENDING"
IN_PROGRESS = "IN_PROGRESS"
FAILED = "FAILED"
CANCELED = "CANCELED"

TIMEOUT = "TIMEOUT"

STATUSES = (SUCCESS, PENDING, IN_PROGRESS, FAILED, CANCELED)

__SUSPICIOUS_EXCLUSIONS = None
__SUSPICIOUS_EXCEPTIONS = None

SCANNER_VERSIONS = {
    "ScannerCLI": {
        "4.7.0": datetime.datetime(2022, 2, 22),
        "4.6.2": datetime.datetime(2021, 5, 7),
        "4.6.1": datetime.datetime(2021, 4, 30),
        "4.6.0": datetime.datetime(2021, 1, 13),
        "4.5.0": datetime.datetime(2020, 10, 5),
        "4.4.0": datetime.datetime(2020, 7, 3),
        "4.3.0": datetime.datetime(2019, 3, 9),
        "4.2.0": datetime.datetime(2019, 10, 1),
        "4.1.0": datetime.datetime(2019, 9, 9),
    },
    "ScannerMaven": {
        "3.9.1": datetime.datetime(2021, 11, 1),
        "3.9.0": datetime.datetime(2021, 4, 1),
        "3.8.0": datetime.datetime(2021, 1, 1),
        "3.7.0": datetime.datetime(2019, 10, 1),
        "3.6.1": datetime.datetime(2019, 8, 1),
        "3.6.0": datetime.datetime(2019, 1, 1),
        "3.5.0": datetime.datetime(2018, 9, 1),
        "3.4.1": datetime.datetime(2018, 6, 1),
        "3.4.0": datetime.datetime(2017, 11, 1),
        "3.3.0": datetime.datetime(2017, 3, 1),
        "3.2.0": datetime.datetime(2016, 9, 1),
        "3.1.1": datetime.datetime(2016, 9, 1),
        "3.1.0": datetime.datetime(2016, 9, 1),
        "3.0.2": datetime.datetime(2016, 4, 1),
        "3.0.1": datetime.datetime(2016, 1, 1),
        "3.0.0": datetime.datetime(2016, 1, 1),
    },
    "ScannerGradle": {
        "3.4.0": datetime.datetime(2022, 6, 8),
        "3.3.0": datetime.datetime(2021, 6, 10),
        "3.2.0": datetime.datetime(2021, 4, 30),
        "3.1.1": datetime.datetime(2021, 1, 25),
        "3.1.0": datetime.datetime(2021, 1, 13),
        "3.0.0": datetime.datetime(2020, 6, 20),
        "2.8.0": datetime.datetime(2019, 10, 1),
    },
    "ScannerMSBuild": {
        "5.7.1": datetime.datetime(2022, 6, 21),
        "5.7.0": datetime.datetime(2022, 6, 20),
        "5.6.0": datetime.datetime(2022, 5, 30),
        "5.5.3": datetime.datetime(2022, 2, 14),
        "5.5.2": datetime.datetime(2022, 2, 10),
        "5.5.1": datetime.datetime(2022, 2, 8),
        "5.5.0": datetime.datetime(2022, 2, 7),
        "5.4.1": datetime.datetime(2021, 12, 23),
        "5.4.0": datetime.datetime(2021, 11, 26),
        "5.3.2": datetime.datetime(2021, 10, 28),
        "5.3.1": datetime.datetime(2021, 9, 1),
        "5.2.2": datetime.datetime(2021, 6, 24),
        "5.2.1": datetime.datetime(2021, 4, 30),
        "5.2.0": datetime.datetime(2021, 4, 9),
        "5.1.0": datetime.datetime(2021, 3, 9),
        "5.0.4": datetime.datetime(2020, 11, 11),
        "5.0.3": datetime.datetime(2020, 11, 10),
        "5.0.0": datetime.datetime(2020, 11, 5),
        "4.10.0": datetime.datetime(2020, 6, 29),
        "4.9.0": datetime.datetime(2020, 5, 5),
        "4.8.0": datetime.datetime(2019, 11, 6),
        "4.7.1": datetime.datetime(2019, 9, 10),
        "4.7.0": datetime.datetime(2019, 9, 3),
    },
}


class Task(sq.SqObject):
    def __init__(self, task_id, endpoint, concerned_object=None, data=None):
        super().__init__(task_id, endpoint)
        self._json = data
        self.concerned_object = concerned_object
        self._context = None
        self._error = None
        self._submitted_at = None
        self._started_at = None
        self._ended_at = None

    def __str__(self):
        return f"background task '{self.key}'"

    def url(self):
        return f"{self.endpoint.url}/project/background_tasks?id={self.concerned_object.key}"

    def __load(self):
        if self._json is not None:
            return
        self.__load_context()

    def __load_context(self, force=False):
        if not force and self._json is not None and ("scannerContext" in self._json or not self.has_scanner_context()):
            # Context already retrieved or not available
            return
        params = {"id": self.key, "additionalFields": "scannerContext,stacktrace"}
        self._json.update(json.loads(self.get("ce/task", params=params).text)["task"])

    def id(self):
        return self.key

    def __json_field(self, field):
        self.__load()
        if field not in self._json:
            self.__load_context(force=True)
        return self._json[field]

    def type(self):
        return self.__json_field("type")

    def status(self):
        return self.__json_field("status")

    def component(self):
        return self.__json_field("componentKey")

    def execution_time(self):
        return self.__json_field("executionTimeMs")

    def submitter(self):
        self.__load()
        return self._json.get("submitterLogin", "anonymous")

    def has_scanner_context(self):
        self.__load()
        return self._json.get("hasScannerContext", False)

    def warnings(self):
        if not self._json.get("warnings", None):
            data = json.loads(self.get("ce/task", params={"id": self.key, "additionalFields": "warnings"}).text)
            self._json["warnings"] = []
            self._json.update(data["task"])
        return self._json["warnings"]

    def warning_count(self):
        return self.__json_field("warningCount")

    def wait_for_completion(self, timeout=180):
        wait_time = 0
        sleep_time = 0.5
        params = {"status": ",".join(STATUSES), "type": self.type()}
        if self.endpoint.version() >= (8, 0, 0):
            params["component"] = self.component()
        else:
            params["q"] = self.component()
        status = PENDING
        while status not in (SUCCESS, FAILED, CANCELED, TIMEOUT):
            time.sleep(sleep_time)
            wait_time += sleep_time
            sleep_time *= 2
            data = json.loads(self.get("ce/activity", params=params).text)
            for t in data["tasks"]:
                if t["id"] != self.key:
                    continue
                status = t["status"]
            if wait_time >= timeout and status not in (SUCCESS, FAILED, CANCELED):
                status = TIMEOUT
            util.logger.debug("%s is '%s'", str(self), status)
        return status

    def scanner_context(self):
        if not self.has_scanner_context():
            return None
        self.__load_context()
        context_line = self._json.get("scannerContext", None)
        if context_line is None:
            return None
        context = {}
        for line in context_line.split("\n  - "):
            if not line.startswith("sonar"):
                continue
            (prop, val) = line.split("=", 1)
            context[prop] = val
        return context

    def error_details(self):
        self.__load_context()
        return (
            self._json.get("errorMessage", None),
            self._json.get("errorStacktrace", None),
        )

    def error_message(self):
        self.__load_context()
        return self._json.get("errorMessage", None)

    def __audit_exclusions(self, exclusion_pattern, susp_exclusions, susp_exceptions):
        problems = []
        for susp in susp_exclusions:
            if not re.search(rf"{susp}", exclusion_pattern):
                continue
            is_exception = False
            for exception in susp_exceptions:
                if re.search(rf"{exception}", exclusion_pattern):
                    util.logger.debug(
                        "Exclusion %s matches exception %s, no audit problem will be raised",
                        exclusion_pattern,
                        exception,
                    )
                    is_exception = True
                    break
            if not is_exception:
                rule = rules.get_rule(rules.RuleId.PROJ_SUSPICIOUS_EXCLUSION)
                msg = rule.msg.format(str(self.concerned_object), exclusion_pattern)
                problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self.concerned_object))
                break  # Report only on the 1st suspicious match
        return problems

    def __audit_disabled_scm(self, audit_settings, scan_context):
        if not audit_settings.get("audit.project.scm.disabled", True):
            util.logger.info("Auditing disabled SCM integration is turned off, skipping...")
            return []

        if scan_context.get("sonar.scm.disabled", "false") == "false":
            return []
        rule = rules.get_rule(rules.RuleId.PROJ_SCM_DISABLED)
        return [problem.Problem(rule.type, rule.severity, rule.msg.format(str(self.concerned_object)), concerned_object=self)]

    def __audit_warnings(self, audit_settings):
        if not audit_settings.get("audit.projects.analysisWarnings", True):
            util.logger.info("Project analysis warnings auditing disabled, skipping...")
            return []
        warnings = self.warnings()
        if len(warnings) == 0:
            return []
        rule = rules.get_rule(rules.RuleId.PROJ_ANALYSIS_WARNING)
        msg = rule.msg.format(str(self.concerned_object), " --- ".join(warnings))
        return [problem.Problem(rule.type, rule.severity, msg, concerned_object=self)]

    def __audit_failed_task(self, audit_settings):
        if not audit_settings.get("audit.projects.failedTasks", True):
            util.logger.debug("Project failed background tasks auditing disabled, skipping...")
            return []
        if self._json["status"] != "FAILED":
            util.logger.debug("Last bg task of %s has status %s...", str(self.concerned_object), self._json["status"])
            return []
        rule = rules.get_rule(rules.RuleId.BG_TASK_FAILED)
        msg = rule.msg.format(str(self.concerned_object))
        return [problem.Problem(rule.type, rule.severity, msg, concerned_object=self)]

    def __audit_scanner_version(self, audit_settings):
        if not self.has_scanner_context():
            return []
        context = self.scanner_context()
        scanner_type = context.get("sonar.scanner.app", None)
        scanner_version = context.get("sonar.scanner.appVersion", None)
        util.logger.debug("Scanner type = %s, Scanner version = %s", scanner_type, scanner_version)
        if not scanner_version:
            return []

        if scanner_type in ("ScannerGradle", "ScannerMaven"):
            (scanner_version, build_tool_version) = scanner_version.split("/")
            scanner_version = scanner_version.replace("-SNAPSHOT", "")
        scanner_version = [int(n) for n in scanner_version.split(".")]
        if len(scanner_version) == 2:
            scanner_version.append(0)
        scanner_version = tuple(scanner_version[0:3])

        str_version = ".".join([str(n) for n in scanner_version])
        release_date = SCANNER_VERSIONS[scanner_type][str_version]
        delta_days = (datetime.datetime.today() - release_date).days
        versions_list = SCANNER_VERSIONS[scanner_type].keys()
        util.logger.debug("versions = %s", str(versions_list))
        tuple_version_list = []
        for v in versions_list:
            tuple_version_list.append(tuple([int(n) for n in v.split(".")]))

        tuple_version_list.sort(reverse=True)
        index = tuple_version_list.index(scanner_version)
        util.logger.debug("Scanner used is %d versions old", index)
        if delta_days > audit_settings["audit.projects.scannerMaxAge"]:
            rule = rules.get_rule(rules.RuleId.OBSOLETE_SCANNER) if index >= 3 else rules.get_rule(rules.RuleId.NOT_LATEST_SCANNER)
            msg = rule.msg.format(str(self.concerned_object), scanner_type, str_version, util.date_to_string(release_date, with_time=False))
            return [problem.Problem(rule.type, rule.severity, msg, concerned_object=self.concerned_object)]
        return []

    def audit(self, audit_settings):
        if not audit_settings.get("audit.projects.exclusions", True):
            util.logger.debug("Project exclusions auditing disabled, skipping...")
            return []
        util.logger.debug("Auditing %s", str(self))
        problems = []
        if self.has_scanner_context():
            problems = []
            context = self.scanner_context()
            susp_exclusions = _get_suspicious_exclusions(audit_settings.get("audit.projects.suspiciousExclusionsPatterns", ""))
            susp_exceptions = _get_suspicious_exceptions(audit_settings.get("audit.projects.suspiciousExclusionsExceptions", ""))
            for prop in ("sonar.exclusions", "sonar.global.exclusions"):
                if context.get(prop, None) is None:
                    continue
                for excl in util.csv_to_list(context[prop]):
                    util.logger.debug("Pattern = '%s'", excl)
                    problems += self.__audit_exclusions(excl, susp_exclusions, susp_exceptions)
            problems += self.__audit_disabled_scm(audit_settings, context)
        elif type(self.concerned_object).__name__ == "Project":
            util.logger.debug("Last background task of %s has no scanner context, can't audit it", str(self.concerned_object))

        problems += self.__audit_warnings(audit_settings)
        problems += self.__audit_failed_task(audit_settings)
        problems += self.__audit_scanner_version(audit_settings)

        return problems


def search(endpoint, only_current=False, component_key=None):
    params = {"status": ",".join(STATUSES), "additionalFields": "warnings"}
    if only_current:
        params["onlyCurrents"] = "true"
    if component_key is not None:
        params["component"] = component_key
    data = json.loads(endpoint.get("ce/activity", params=params).text)
    task_list = []
    for t in data["tasks"]:
        task_list.append(Task(t["id"], endpoint, data=t))
    return task_list


def search_all_last(component_key=None, endpoint=None):
    return search(only_current=True, component_key=component_key, endpoint=endpoint)


def search_last(component_key, endpoint=None):
    bg_tasks = search(only_current=True, component_key=component_key, endpoint=endpoint)
    if bg_tasks is None or not bg_tasks:
        # No bgtask was found
        return None
    return bg_tasks[0]


def search_all(component_key, endpoint=None):
    return search(component_key=component_key, endpoint=endpoint)


def _get_suspicious_exclusions(patterns):
    global __SUSPICIOUS_EXCLUSIONS
    if __SUSPICIOUS_EXCLUSIONS is not None:
        return __SUSPICIOUS_EXCLUSIONS
    # __SUSPICIOUS_EXCLUSIONS = [x.strip().replace('*', '\\*').replace('.', '\\.').replace('?', '\\?')
    __SUSPICIOUS_EXCLUSIONS = util.csv_to_list(patterns)
    return __SUSPICIOUS_EXCLUSIONS


def _get_suspicious_exceptions(patterns):
    global __SUSPICIOUS_EXCEPTIONS
    if __SUSPICIOUS_EXCEPTIONS is not None:
        return __SUSPICIOUS_EXCEPTIONS
    #    __SUSPICIOUS_EXCEPTIONS = [x.strip().replace('*', '\\*').replace('.', '\\.').replace('?', '\\?')
    __SUSPICIOUS_EXCEPTIONS = util.csv_to_list(patterns)
    return __SUSPICIOUS_EXCEPTIONS
