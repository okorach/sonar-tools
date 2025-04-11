#
# sonar-tools
# Copyright (C) 2022-2025 Olivier Korach
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

"""Abstraction of the SonarQube background task concept"""
from typing import Optional
import time
import datetime
import json
import re

from requests import RequestException

import sonar.logging as log
import sonar.sqobject as sq
import sonar.platform as pf

import sonar.utilities as util
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem
from sonar.config import get_scanners_versions
from sonar.util import types, cache

SUCCESS = "SUCCESS"
PENDING = "PENDING"
IN_PROGRESS = "IN_PROGRESS"
FAILED = "FAILED"
CANCELED = "CANCELED"

TIMEOUT = "TIMEOUT"

STATUSES = (SUCCESS, PENDING, IN_PROGRESS, FAILED, CANCELED)

__SUSPICIOUS_EXCLUSIONS = None
__SUSPICIOUS_EXCEPTIONS = None

SCANNER_VERSIONS = get_scanners_versions()


class Task(sq.SqObject):
    """
    Abstraction of the SonarQube "background task" concept
    """

    CACHE = cache.Cache()

    def __init__(self, endpoint: pf.Platform, task_id: str, concerned_object: object = None, data: types.ApiPayload = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=task_id)
        self.sq_json = data
        self.concerned_object = concerned_object
        if data is not None:
            self.component_key = data.get("componentKey", None)
        self._context = None
        self._error = None
        self._submitted_at = None
        self._started_at = None
        self._ended_at = None

    def __str__(self) -> str:
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"background task '{self.key}'"

    def url(self) -> str:
        """
        :return: the SonarQube permalink URL to the background task
        :rtype: str
        """
        u = f"{self.endpoint.url}/project/background_tasks"
        if self.component_key:
            u += f"?id={self.component_key}"
        return u

    def project(self) -> object:
        """Returns the project of the background task"""
        return self.concerned_object

    def _load(self) -> None:
        """Loads a task context"""
        if self.sq_json is not None:
            return
        self._load_context()

    def _load_context(self, force: bool = False) -> None:
        """Loads a task context"""
        if not force and self.sq_json is not None and ("scannerContext" in self.sq_json or not self.has_scanner_context()):
            # Context already retrieved or not available
            return
        params = {"id": self.key, "additionalFields": "scannerContext,stacktrace"}
        if self.sq_json is None:
            self.sq_json = {}
        self.sq_json.update(json.loads(self.get("ce/task", params=params).text)["task"])

    def id(self) -> str:
        """
        :return: the background task id
        :rtype: str
        """
        return self.key

    def __json_field(self, field: str) -> str:
        """Returns a background task scanner context field"""
        self._load()
        if field not in self.sq_json:
            self._load_context(force=True)
        return self.sq_json[field]

    def type(self) -> str:
        """
        :return: the background task type
        :rtype: str
        """
        return self.__json_field("type")

    def status(self) -> str:
        """
        :return: the background task status
        :rtype: str
        """
        return self.__json_field("status")

    def component(self) -> Optional[str]:
        """
        :return: the background task component key or None
        :rtype: str or None
        """
        return self.__json_field("componentKey")

    def execution_time(self) -> int:
        """
        :return: the background task execution time in millisec
        :rtype: int
        """
        return int(self.__json_field("executionTimeMs"))

    def submitter(self) -> str:
        """
        :return: the background task submitter
        :rtype: str
        """
        self._load()
        return self.sq_json.get("submitterLogin", "anonymous")

    def has_scanner_context(self) -> bool:
        """
        :return: Whether the background task has a scanner context
        :rtype: bool
        """
        self._load()
        return self.sq_json.get("hasScannerContext", False)

    def warnings(self) -> list[str]:
        """
        :return: the background task warnings, if any
        :rtype: list
        """
        if not self.sq_json.get("warnings", None):
            data = json.loads(self.get("ce/task", params={"id": self.key, "additionalFields": "warnings"}).text)
            self.sq_json["warnings"] = []
            self.sq_json.update(data["task"])
        return self.sq_json["warnings"]

    def warning_count(self) -> int:
        """
        :return: the number of warnings in the background
        :rtype: int
        """
        return self.__json_field("warningCount")

    def wait_for_completion(self, timeout: int = 180) -> str:
        """Waits for a background task to complete

        :param timeout: Timeout to wait in seconds, defaults to 180
        :type timeout: int, optional
        :return: the background task status
        :rtype: str
        """
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
            log.debug("%s is '%s'", str(self), status)
        return status

    def scanner_context(self) -> Optional[dict[str, str]]:
        """
        :return: the background task scanner context
        :rtype: dict
        """
        if not self.has_scanner_context():
            return None
        self._load_context()
        context_line = self.sq_json.get("scannerContext", None)
        if context_line is None:
            return None
        context = {}
        for line in context_line.split("\n  - "):
            if not line.startswith("sonar"):
                continue
            (prop, val) = line.split("=", 1)
            context[prop] = val
        return context

    def scanner(self) -> str:
        """Returns the project type (MAVEN, GRADLE, DOTNET, OTHER, UNKNOWN)"""
        if not self.has_scanner_context():
            return "UNKNOWN"
        ctxt = self.scanner_context()
        return ctxt.get("sonar.scanner.app", "UNKNOWN").upper().replace("SCANNER", "").replace("MSBUILD", "DOTNET").replace("NPM", "CLI")

    def error_details(self) -> tuple[str, str]:
        """
        :return: The background task error details
        :rtype: tuple (errorMsg (str), stackTrace (str)
        """
        self._load_context()
        return (self.sq_json.get("errorMessage", None), self.sq_json.get("errorStacktrace", None))

    def error_message(self) -> Optional[str]:
        """
        :return: The background task error message
        :rtype: str
        """
        self._load_context()
        return self.sq_json.get("errorMessage", None)

    def __audit_exclusions(self, exclusion_pattern: str, susp_exclusions: str, susp_exceptions: str) -> list[Problem]:
        """Audits a task exclusion patterns are returns found problems"""
        problems = []
        for susp in susp_exclusions:
            if not re.search(rf"{susp}", exclusion_pattern):
                continue
            is_exception = False
            for exception in susp_exceptions:
                if re.search(rf"{exception}", exclusion_pattern):
                    log.debug("Exclusion %s matches exception %s, no audit problem will be raised", exclusion_pattern, exception)
                    is_exception = True
                    break
            if not is_exception:
                rule = get_rule(RuleId.PROJ_SUSPICIOUS_EXCLUSION)
                problems.append(Problem(rule, self.concerned_object, str(self.concerned_object), exclusion_pattern))
                break  # Report only on the 1st suspicious match
        return problems

    def __audit_disabled_scm(self, audit_settings: types.ConfigSettings, scan_context: dict[str, str]) -> list[Problem]:
        """Audits a bg task for eventual SCM disabled and reports the problem if found"""
        if not audit_settings.get("audit.project.scm.disabled", True):
            log.info("Auditing disabled SCM integration is turned off, skipping...")
            return []

        if scan_context.get("sonar.scm.disabled", "false") == "false":
            return []
        return [Problem(get_rule(RuleId.PROJ_SCM_DISABLED), self, str(self.concerned_object))]

    def __audit_warnings(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits for warning in background tasks and reports found problems"""
        if not audit_settings.get("audit.projects.analysisWarnings", True):
            log.info("Project analysis warnings auditing disabled, skipping...")
            return []
        pbs = []
        warnings = self.warnings()
        warnings_left = []
        for w in warnings:
            if w.find("SCM provider autodetection failed") >= 0:
                pbs.append(Problem(get_rule(RuleId.PROJ_SCM_UNDETECTED), self.concerned_object, str(self.concerned_object)))
            else:
                warnings_left.append(w)
        if len(warnings_left) > 0:
            rule = get_rule(RuleId.PROJ_ANALYSIS_WARNING)
            pbs.append(Problem(rule, self, str(self.concerned_object), " --- ".join(warnings_left)))
        return pbs

    def __audit_failed_task(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        if not audit_settings.get("audit.projects.failedTasks", True):
            log.debug("Project failed background tasks auditing disabled, skipping...")
            return []
        if self.sq_json["status"] != "FAILED":
            log.debug("Last bg task of %s has status %s...", str(self.concerned_object), self.sq_json["status"])
            return []
        return [Problem(get_rule(RuleId.BG_TASK_FAILED), self, str(self.concerned_object))]

    def __audit_scanner_version(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        if not self.has_scanner_context():
            return []
        context = self.scanner_context()
        scanner_type = context.get("sonar.scanner.app", None)
        scanner_version = context.get("sonar.scanner.appVersion", None)
        proj = self.concerned_object
        log.debug("Scanner type = %s, Scanner version = %s", scanner_type, scanner_version)
        if not scanner_version:
            log.warning(
                "%s has been scanned with scanner '%s' with no version, skipping check scanner version obsolescence",
                str(proj),
                scanner_type,
            )
            return []
        if scanner_type not in SCANNER_VERSIONS:
            log.warning(
                "%s has been scanned with scanner '%s' which is not inventoried, skipping check on scanner obsolescence",
                str(proj),
                scanner_type,
            )
            return []

        if scanner_type == "Ant":
            return [Problem(get_rule(RuleId.ANT_SCANNER_DEPRECATED), proj, str(proj))]

        problems = []
        if scanner_type in ("ScannerGradle", "ScannerMaven"):
            scanner_version = scanner_version.split("/")[0].replace("-SNAPSHOT", "")
        scanner_version = [int(n) for n in scanner_version.split(".")]
        if len(scanner_version) == 2:
            scanner_version.append(0)
        scanner_version = tuple(scanner_version[0:3])
        str_version = util.version_to_string(scanner_version)
        versions_list = SCANNER_VERSIONS[scanner_type].keys()
        log.debug("versions = %s", str(versions_list))
        try:
            release_date = SCANNER_VERSIONS[scanner_type][str_version]
        except KeyError:
            log.warning(
                "Scanner '%s' version '%s' is not referenced in sonar-tools. "
                "Scanner obsolescence check skipped. "
                "Please report to author at https://github.com/okorach/sonar-tools/issues",
                scanner_type,
                str_version,
            )
            return []

        tuple_version_list = [tuple(int(n) for n in v.split(".")) for v in versions_list]
        tuple_version_list.sort(reverse=True)
        delta_days = (datetime.datetime.today() - release_date).days
        index = tuple_version_list.index(scanner_version)

        log.debug("Auditing Scanner for .NET v9.2.x")
        if scanner_type == "ScannerMSBuild" and scanner_version[0:2] == (9, 2):
            problems.append(Problem(get_rule(RuleId.VULNERABLE_DOTNET_SCANNER), proj, str(proj), str_version))

        log.debug("Scanner used is %d versions old", index)
        if delta_days > audit_settings.get("audit.projects.scannerMaxAge", 730):
            rule = get_rule(RuleId.OBSOLETE_SCANNER) if index >= 3 else get_rule(RuleId.NOT_LATEST_SCANNER)
            release_date = util.date_to_string(release_date, with_time=False)
            problems.append(Problem(rule, proj, str(proj), scanner_type, str_version, release_date))

        return problems

    def audit(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits a background task and returns the list of found problems"""
        if not audit_settings.get("audit.projects.exclusions", True):
            log.debug("Project exclusions auditing disabled, skipping...")
            return []
        log.debug("Auditing %s", str(self))
        problems = []
        if self.has_scanner_context():
            if audit_settings.get("audit.projects.exclusions", True):
                context = self.scanner_context()
                susp_exclusions = util.csv_to_list(audit_settings.get("audit.projects.suspiciousExclusionsPatterns", ""))
                susp_exceptions = util.csv_to_list(audit_settings.get("audit.projects.suspiciousExclusionsExceptions", ""))
                for prop in ("sonar.exclusions", "sonar.global.exclusions"):
                    if context.get(prop, None) is None:
                        continue
                    for excl in util.csv_to_list(context[prop]):
                        log.debug("Pattern = '%s'", excl)
                        problems += self.__audit_exclusions(excl, susp_exclusions, susp_exceptions)
            problems += self.__audit_disabled_scm(audit_settings, context)
        elif type(self.concerned_object).__name__ == "Project":
            log.debug("Last background task of %s has no scanner context, can't audit it", str(self.concerned_object))

        problems += self.__audit_warnings(audit_settings)
        problems += self.__audit_failed_task(audit_settings)
        problems += self.__audit_scanner_version(audit_settings)

        return problems


def search(endpoint: pf.Platform, only_current: bool = False, component_key: str = None, **kwargs) -> list[Task]:
    """Searches background tasks

    :param Platform endpoint: Reference to the SonarQube platform
    :param only_current: only the most recent background task of each object, defaults to False
    :param component_key: filter for a given component key only, defaults to None
    :param component_key: str, optional
    :return: The list of found background tasks
    :rtype: list[Task]
    """
    params = {"status": ",".join(STATUSES), "additionalFields": "warnings"}
    params.update(**kwargs)
    if only_current:
        params["onlyCurrents"] = "true"
    if component_key is not None:
        params["component"] = component_key
    try:
        data = json.loads(endpoint.get("ce/activity", params=params).text)
        return [Task(endpoint=endpoint, task_id=t["id"], data=t) for t in data["tasks"]]
    except (ConnectionError, RequestException) as e:
        util.handle_error(e, f"getting background tasks of component {component_key}", catch_all=True)
    return []


def search_all_last(endpoint: pf.Platform) -> list[Task]:
    """Searches for last background task of all found components"""
    return search(endpoint=endpoint, only_current=True)


def search_last(endpoint: pf.Platform, component_key: str, **params) -> Optional[Task]:
    """Searches for last background task of a component"""
    branch = params.pop("branch", None)
    bg_tasks = search(endpoint=endpoint, only_current=branch is None, component_key=component_key, **params)
    if branch:
        bg_tasks = [t for t in bg_tasks if t.sq_json.get("branch", "") == branch]
    if len(bg_tasks) == 0:
        # No bgtask was found
        log.debug("No background task found for component key '%s'%s", component_key, f" branch '{branch}'" if branch else "")
        return None
    return bg_tasks[0]


def search_all(endpoint: pf.Platform, component_key: str, **params) -> list[Task]:
    """Search all background tasks of a given component"""
    return search(endpoint=endpoint, component_key=component_key, **params)
