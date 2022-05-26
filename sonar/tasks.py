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
import json
import re
from sonar import env
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


class Task(sq.SqObject):
    def __init__(self, task_id, endpoint, data=None):
        super().__init__(task_id, endpoint)
        self._json = data
        self._context = None
        self._error = None
        self._submitted_at = None
        self._started_at = None
        self._ended_at = None

    def __str__(self):
        return f"background task '{self.key}'"

    def __load(self):
        if self._json is not None:
            return
        self.__load_context()

    def __load_context(self, force=False):
        if not force and self._json is not None and ("scannerContext" in self._json or not self.has_scanner_context()):
            # Context already retrieved or not available
            return
        params = {"id": self.key, "additionalFields": "scannerContext,stacktrace"}
        resp = env.get("ce/task", params=params, ctxt=self.endpoint)
        self._json.update(json.loads(resp.text)["task"])

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
            resp = env.get("ce/activity", params=params, ctxt=self.endpoint)
            for t in json.loads(resp.text)["tasks"]:
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
                msg = rule.msg.format(f"project key '{self.component()}'", exclusion_pattern)
                problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))
                break  # Report only on the 1st suspicious match
        return problems

    def __audit_disabled_scm(self, audit_settings, scan_context):
        if not audit_settings.get("audit.project.scm.disabled", True):
            util.logger.info("Auditing disabled SCM integration is turned off, skipping...")
            return []

        if scan_context.get("sonar.scm.disabled", "false") == "false":
            return []
        rule = rules.get_rule(rules.RuleId.PROJ_SCM_DISABLED)
        proj = self.component()
        return [
            problem.Problem(
                rule.type,
                rule.severity,
                rule.msg.format(f"{str(proj)}'"),
                concerned_object=proj,
            )
        ]

    def audit(self, audit_settings):
        if not audit_settings["audit.projects.exclusions"]:
            util.logger.info("Project exclusions auditing disabled, skipping...")
            return []
        util.logger.debug("Auditing %s", str(self))
        if not self.has_scanner_context():
            util.logger.info(
                "Last background task of project key '%s' has no scanner context, can't audit scanner context",
                self.component(),
            )
            return []
        problems = []
        context = self.scanner_context()
        susp_exclusions = _get_suspicious_exclusions(audit_settings["audit.projects.suspiciousExclusionsPatterns"])
        susp_exceptions = _get_suspicious_exceptions(audit_settings["audit.projects.suspiciousExclusionsExceptions"])
        for prop in ("sonar.exclusions", "sonar.global.exclusions"):
            if context.get(prop, None) is None:
                continue
            for excl in util.csv_to_list(context[prop]):
                util.logger.debug("Pattern = '%s'", excl)
                problems += self.__audit_exclusions(excl, susp_exclusions, susp_exceptions)
        problems += self.__audit_disabled_scm(audit_settings, context)
        return problems


def search(only_current=False, component_key=None, endpoint=None):
    params = {"status": ",".join(STATUSES)}
    if only_current:
        params["onlyCurrents"] = "true"
    if component_key is not None:
        params["component"] = component_key
    resp = env.get("ce/activity", params=params, ctxt=endpoint)
    data = json.loads(resp.text)
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
