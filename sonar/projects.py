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

Abstraction of the SonarQube "project" concept

"""

from __future__ import annotations

import os
import re
import json
import concurrent.futures
from datetime import datetime

from typing import Optional, Union
from http import HTTPStatus
from threading import Lock
from requests import HTTPError, RequestException

import sonar.logging as log
import sonar.platform as pf

from sonar.util import types, cache
from sonar.util import project_utils as putils

from sonar import exceptions, errcodes
from sonar import sqobject, components, qualitygates, qualityprofiles, tasks, settings, webhooks, devops
import sonar.permissions.permissions as perms
from sonar import pull_requests, branches
import sonar.utilities as util
import sonar.permissions.project_permissions as pperms

from sonar.audit import severities
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem
import sonar.util.constants as c

_CLASS_LOCK = Lock()

MAX_PAGE_SIZE = 500
_TREE_API = "components/tree"
_CONTAINS_AI_CODE = "containsAiCode"
_BIND_SEP = ":::"
_AUDIT_BRANCHES_PARAM = "audit.projects.branches"

ZIP_ZERO_LOC = "ZERO_LOC"
ZIP_ASYNC_SUCCESS = "ASYNC_SUCCESS"
ZIP_ERR_403 = "FAILED/INSUFFICIENT_PERMISSIONS"
ZIP_CONFLICT = "FAILED/ZIP_CONFLICT"
ZIP_PROJ_EXISTS = "FAILED/PROJECT_ALREADY_EXISTS"
ZIP_TIMEOUT = "FAILED/TIMEOUT"
ZIP_EXCEPTION = "FAILED/EXCEPTION"

_IMPORTABLE_PROPERTIES = (
    "key",
    "name",
    "binding",
    settings.NEW_CODE_PERIOD,
    "qualityProfiles",
    "links",
    "permissions",
    "branches",
    "tags",
    "visibility",
    "qualityGate",
    "webhooks",
    "aiCodeFix",
)

_PROJECT_QUALIFIER = "qualifier=TRK"

_UNNEEDED_CONTEXT_DATA = (
    "sonar.announcement.message",
    "sonar.auth.github.allowUsersToSignUp",
    "sonar.auth.github.apiUrl",
    "sonar.auth.github.appId",
    "sonar.auth.github.enabled",
    "sonar.auth.github.groupsSync",
    "sonar.auth.github.organizations",
    "sonar.auth.github.webUrl",
    "sonar.builtInQualityProfiles.disableNotificationOnUpdate",
    "sonar.core.id",
    "sonar.core.serverBaseURL",
    "sonar.core.startTime",
    "sonar.dbcleaner.branchesToKeepWhenInactive",
    "sonar.forceAuthentication",
    "sonar.host.url",
    "sonar.java.jdkHome",
    "sonar.links.ci",
    "sonar.links.homepage",
    "sonar.links.issue",
    "sonar.links.scm",
    "sonar.links.scm_dev",
    "sonar.plugins.risk.consent",
)

_UNNEEDED_TASK_DATA = (
    "analysisId",
    "componentId",
    "hasScannerContext",
    "id",
    "warningCount",
    "componentQualifier",
    "nodeName",
    "componentName",
    "componentKey",
    "submittedAt",
    "executedAt",
    "type",
)

# Keys to exclude when applying settings in update()
_SETTINGS_WITH_SPECIFIC_IMPORT = (
    "permissions",
    "tags",
    "links",
    "qualityGate",
    "qualityProfiles",
    "binding",
    "name",
    "visibility",
)


class Project(components.Component):
    """Abstraction of the SonarQube project concept"""

    CACHE = cache.Cache()
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "components"
    API = {
        c.CREATE: "projects/create",
        c.READ: "components/show",
        c.DELETE: "projects/delete",
        c.LIST: "components/search_projects",
        c.SET_TAGS: "project_tags/set",
        c.GET_TAGS: "components/show",
    }

    def __init__(self, endpoint: pf.Platform, key: str) -> None:
        """
        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: The project key
        """
        super().__init__(endpoint=endpoint, key=key)
        self._last_analysis: Optional[datetime] = None
        self._branches_last_analysis: Optional[datetime] = None
        self._permissions: Optional[object] = None
        self._branches: Optional[dict[str, branches.Branch]] = None
        self._pull_requests: Optional[dict[str, pull_requests.PullRequest]] = None
        self._ncloc_with_branches: Optional[int] = None
        self._binding: Optional[dict[str, str]] = None
        self._new_code: Optional[str] = None
        self._ci: Optional[str] = None
        self._revision: Optional[str] = None
        Project.CACHE.put(self)
        log.debug("Created object %s", str(self))

    @classmethod
    def get_object(cls, endpoint: pf.Platform, key: str) -> Project:
        """Creates a project from a search in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Project key to search
        :raises ObjectNotFound: if project key not found
        :return: The Project
        """
        if o := Project.CACHE.get(key, endpoint.local_url):
            return o
        data = json.loads(endpoint.get(Project.API[c.READ], params={"component": key}).text)
        return cls.load(endpoint, data["component"])

    @classmethod
    def load(cls, endpoint: pf.Platform, data: types.ApiPayload) -> Project:
        """Creates a project loaded with JSON data coming from api/components/search request

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Project key to search
        :param dict data: Project data entry in the search results
        :return: The Project
        :rtype: Project
        """
        key = data["key"]
        if not (o := Project.CACHE.get(key, endpoint.local_url)):
            o = cls(endpoint, key)
        o.reload(data)
        return o

    @classmethod
    def create(cls, endpoint: pf.Platform, key: str, name: str) -> Project:
        """Creates a Project object after creating it in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Project key to create
        :param str name: Project name
        :return: The Project
        :rtype: Project
        """
        endpoint.post(Project.API[c.CREATE], params={"project": key, "name": name})
        o = cls(endpoint, key)
        o.name = name
        return o

    def __str__(self) -> str:
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"project '{self.key}'"

    def project(self) -> Project:
        """Returns the project"""
        return self

    def refresh(self) -> Project:
        """Refresh a project from SonarQube

        :raises ObjectNotFound: if project key not found
        :return: self
        """
        try:
            data = json.loads(self.get(Project.api_for(c.READ, self.endpoint), params=self.api_params(c.READ)).text)
        except exceptions.ObjectNotFound:
            Project.CACHE.pop(self)
            raise
        return self.reload(data["component"])

    def reload(self, data: types.ApiPayload) -> Project:
        """Reloads a project with JSON data coming from api/components/search request

        :param dict data: Data to load
        :return: self
        """
        """Loads a project object with contents of an api/projects/search call"""
        super().reload(data)
        self.name = data["name"]
        self._visibility = data["visibility"]
        key = next((k for k in ("lastAnalysisDate", "analysisDate") if k in data), None)
        self._last_analysis = util.string_to_date(data[key]) if key else None
        self._revision = data.get("revision", self._revision)
        return self

    def url(self) -> str:
        """
        :return: the SonarQube permalink to the project
        :rtype: str
        """
        return f"{self.base_url(local=False)}/dashboard?id={self.key}"

    def last_analysis(self, include_branches: bool = False) -> Optional[datetime]:
        """
        :param include_branches: Take into account branch to determine last analysis, defaults to False
        :type include_branches: bool, optional
        :returns: Project last analysis date or None if never analyzed
        """
        if not self._last_analysis:
            self.reload(self.get_navigation_data())
        if not include_branches:
            return self._last_analysis
        if self._branches_last_analysis:
            return self._branches_last_analysis

        self._branches_last_analysis = self._last_analysis
        if self.endpoint.version() >= (9, 2, 0):
            # Starting from 9.2 project last analysis date takes into account branches and PR
            return self._branches_last_analysis

        self._branches_last_analysis = max(
            b.last_analysis() for b in list(self.branches().values()) + list(self.pull_requests().values()) if b.last_analysis()
        )
        return self._branches_last_analysis

    def loc(self) -> int:
        """
        :return: Number of LoCs of the project, taking into account branches and pull requests, if any
        :rtype: int
        """
        if self._ncloc_with_branches is not None:
            return self._ncloc_with_branches
        if self.endpoint.edition() == c.CE:
            self._ncloc_with_branches = super().loc()
        else:
            self._ncloc_with_branches = max(b.loc() for b in list(self.branches().values()) + list(self.pull_requests().values()))
        return self._ncloc_with_branches

    def branches(self, use_cache: bool = True) -> dict[str, branches.Branch]:
        """
        :return: Dict of branches of the project
        :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
        :type use_cache: bool
        :rtype: dict{<branchName>: <Branch>}
        """
        if not self._branches or not use_cache:
            try:
                self._branches = branches.get_list(self)
            except exceptions.UnsupportedOperation:
                self._branches = {}
        return self._branches

    def main_branch_name(self) -> str:
        """
        :return: Project main branch name
        """
        if self.endpoint.edition() == c.CE:
            return self.sq_json.get("branch", "main")
        b = self.main_branch()
        return b.name if b else ""

    def main_branch(self) -> Optional[branches.Branch]:
        """
        :return: Main branch of the project
        """
        if self.endpoint.edition() == c.CE:
            raise exceptions.UnsupportedOperation("Main branch is not supported in Community Edition")
        try:
            return next(b for b in self.branches().values() if b.is_main())
        except StopIteration:
            log.warning("Could not find main branch for %s", str(self))
        return None

    def pull_requests(self, use_cache: bool = True) -> dict[str, pull_requests.PullRequest]:
        """
        :return: List of pull requests of the project
        :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
        :type use_cache: bool
        :rtype: dict{PR_ID: PullRequest}
        """
        if self._pull_requests is None or not use_cache:
            try:
                self._pull_requests = pull_requests.get_list(self)
            except exceptions.UnsupportedOperation:
                self._pull_requests = {}
        return self._pull_requests

    def delete(self) -> bool:
        """Deletes a project in SonarQube

        :raises ObjectNotFound: If object to delete was not found in SonarQube
        :raises request.HTTPError: In all other cases of HTTP Errors
        :return: Whether the operation succeeded
        """
        loc = int(self.get_measure("ncloc", fallback="0"))
        log.info("Deleting %s, name '%s' with %d LoCs", str(self), self.name, loc)
        return super().delete()

    def has_binding(self) -> bool:
        """Whether the project has a DevOps platform binding"""
        if not self._binding:
            self.binding()
        return self._binding.get("has_binding", False)

    def binding(self) -> Optional[dict[str, str]]:
        """
        :return: The project DevOps platform binding
        :rtype: dict
        """
        if not self._binding:
            try:
                resp = self.get("alm_settings/get_binding", params={"project": self.key}, mute=(HTTPStatus.NOT_FOUND,))
                self._binding = {"has_binding": True, "binding": json.loads(resp.text)}
            except exceptions.SonarException:
                # Hack: 8.9 returns 404, 9.x returns 400
                self._binding = {"has_binding": False}
        log.debug("%s binding = %s", str(self), str(self._binding.get("binding", None)))
        return self._binding.get("binding", None)

    def binding_key(self) -> Optional[str]:
        """Computes a unique project binding key"""
        if not self.has_binding():
            return None
        p_bind = self.binding()
        log.debug("%s binding_key = %s", str(self), str(p_bind))
        key = f'{p_bind["alm"]}{_BIND_SEP}{p_bind["repository"]}'
        if p_bind["alm"] in ("azure", "bitbucket"):
            key += f'{_BIND_SEP}{p_bind["slug"]}'
        return key

    def is_part_of_monorepo(self) -> bool:
        """
        :return: From the DevOps binding, Whether the project is part of a monorepo
        :rtype: bool
        """
        bind = self.binding()
        return bind is not None and bind.get("has_binding", False) and bind.get("monorepo", False)

    def __audit_last_analysis(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits whether the last analysis of the project is too old or not

        :param audit_settings: Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        log.debug("Auditing %s last analysis date", str(self))
        problems = []
        age = util.age(self.last_analysis(include_branches=True), True)
        if age is None:
            if audit_settings.get(c.AUDIT_MODE_PARAM, "") == "housekeeper":
                return problems
            if not audit_settings.get("audit.projects.neverAnalyzed", True):
                log.debug("Auditing of never analyzed projects is disabled, skipping")
            else:
                problems.append(Problem(get_rule(RuleId.PROJ_NOT_ANALYZED), self, str(self)))
            return problems

        max_age = audit_settings.get("audit.projects.maxLastAnalysisAge", 180)
        if max_age == 0:
            log.debug("Auditing of projects with old analysis date is disabled, skipping")
        elif age > max_age:
            rule = get_rule(RuleId.PROJ_LAST_ANALYSIS)
            severity = severities.Severity.HIGH if age > 365 else rule.severity
            problems.append(Problem(rule, self, str(self), self.get_measure("ncloc", fallback="0"), age, severity=severity))

        log.debug("%s last analysis is %d days old", str(self), age)
        return problems

    def __audit_branches(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits project branches

        :param audit_settings: Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        if not audit_settings.get(_AUDIT_BRANCHES_PARAM, True):
            log.debug("Auditing of branchs is disabled, skipping...")
            return []
        log.debug("Auditing %s branches", str(self))
        problems = []
        main_br_count = 0
        for branch in self.branches().values():
            problems += branch.audit(audit_settings)
            if audit_settings.get(c.AUDIT_MODE_PARAM, "") != "housekeeper" and branch.name in ("main", "master"):
                main_br_count += 1
                if main_br_count > 1:
                    problems.append(Problem(get_rule(RuleId.PROJ_MAIN_AND_MASTER), self, str(self)))
        return problems

    def __audit_pull_requests(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits project pull requests

        :param ConfigSettings audit_settings: Settings (thresholds) to raise problems
        :return: List of problems found
        """
        problems = []
        for pr in self.pull_requests().values():
            problems += pr.audit(audit_settings)
        return problems

    def audit_languages(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits project utility languages and returns problems if too many LoCs of these

        :param audit_settings: Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        if audit_settings.get(c.AUDIT_MODE_PARAM, "") == "housekeeper":
            return []
        if not audit_settings.get("audit.projects.utilityLocs", False):
            log.debug("Utility LoCs audit disabled by configuration, skipping")
            return []
        log.debug("Auditing %s utility LoC count", str(self))

        total_locs = 0
        languages = {}
        resp = self.get_measure("ncloc_language_distribution")
        if resp is None:
            return []
        for lang in self.get_measure("ncloc_language_distribution").split(";"):
            (lang, ncloc) = lang.split("=")
            languages[lang] = int(ncloc)
            total_locs += int(ncloc)
        utility_locs = sum(lcount for lang, lcount in languages.items() if lang in ("xml", "json"))
        if total_locs > 100000 and (utility_locs / total_locs) > 0.5:
            return [Problem(get_rule(RuleId.PROJ_UTILITY_LOCS), self, str(self), utility_locs)]
        log.debug("%s utility LoCs count (%d) seems reasonable", str(self), utility_locs)
        return []

    def __audit_binding_valid(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        if audit_settings.get(c.AUDIT_MODE_PARAM, "") == "housekeeper":
            return []
        if self.endpoint.edition() == c.CE:
            log.info("Community edition, skipping binding validation...")
            return []
        elif not audit_settings.get("audit.projects.bindings", True):
            log.info("%s binding validation disabled, skipped", str(self))
            return []
        elif not self.has_binding():
            log.info("%s has no binding, skipping binding validation...", str(self))
            return []
        try:
            self.get("alm_settings/validate_binding", params={"project": self.key})
            log.debug("%s binding is valid", str(self))
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"auditing binding of {str(self)}", catch_all=True)
            # Hack: 8.9 returns 404, 9.x returns 400
            if isinstance(e, HTTPError) and e.response.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
                return [Problem(get_rule(RuleId.PROJ_INVALID_BINDING), self, str(self))]
        return []

    def get_type(self) -> str:
        """Returns the project type (MAVEN, GRADLE, DOTNET, OTHER, UNKNOWN)"""
        data = json.loads(self.get(api=_TREE_API, params={"component": self.key, "ps": 500, "q": "pom.xml"}).text)
        for comp in data["components"]:
            if comp["name"] == "pom.xml":
                log.info("%s is a MAVEN project", str(self))
                return "MAVEN"
        data = json.loads(self.get(api=_TREE_API, params={"component": self.key, "ps": 500, "q": "gradle"}).text)
        for comp in data["components"]:
            if "gradle" in comp["name"]:
                return "GRADLE"
        data = json.loads(self.get(api=_TREE_API, params={"component": self.key, "ps": 500}).text)
        projtype = "UNKNOWN"
        for comp in data["components"]:
            if re.match(r".*\.(cs|csx|vb)$", comp["name"]):
                projtype = "DOTNET"
                break
            if re.match(r".*\.(java)$", comp["name"]):
                projtype = "JAVA"
                break
            if re.match(r".*\.(py|rb|cbl|vbs|go|js|ts)$", comp["name"]):
                projtype = "CLI"
                break
        log.info("%s is a %s project", str(self), projtype)
        return projtype

    def last_task(self) -> Optional[tasks.Task]:
        """Returns the last analysis background task of a problem, or none if not found"""
        if task := tasks.search_last(component_key=self.key, endpoint=self.endpoint, type="REPORT"):
            task.concerned_object = self
        return task

    def task_history(self) -> Optional[tasks.Task]:
        """Returns the last analysis background task of a problem, or none if not found"""
        return tasks.search_all(component_key=self.key, endpoint=self.endpoint, type="REPORT")

    def scanner(self) -> str:
        """Returns the project type (MAVEN, GRADLE, DOTNET, OTHER, UNKNOWN)"""
        last_task = self.last_task()
        if not last_task:
            return "UNKNOWN"
        last_task.concerned_object = self
        return last_task.scanner()

    def ci(self) -> str:
        """Returns the detected CI tool used, or undetected, or unknown if HTTP request fails"""
        log.debug("Collecting detected CI")
        if not self._ci or not self._revision:
            self._ci, self._revision = "unknown", "unknown"
            try:
                data = json.loads(self.get("project_analyses/search", params={"project": self.key, "ps": 1}).text)["analyses"]
                if len(data) > 0:
                    self._ci, self._revision = data[0].get("detectedCI", "unknown"), data[0].get("revision", "unknown")
            except exceptions.SonarException:
                pass
            except KeyError:
                log.warning("KeyError, can't retrieve CI tool and revision")
        return self._ci

    def revision(self) -> str:
        """Returns the last analysis commit, or unknown if HTTP request fails or no revision"""
        log.debug("Collecting revision")
        if not self._revision:
            self.ci()
        return self._revision

    def project_key(self) -> str:
        """Returns the project key"""
        return self.key

    def ai_code_fix(self) -> Optional[str]:
        """Returns whether this project is enabled for AI Code Fix (if only enabled per project)"""
        log.debug("Getting project AI Code Fix suggestion flag for %s", str(self))
        global_setting = settings.Setting.read(key=settings.AI_CODE_FIX, endpoint=self.endpoint)
        if not global_setting or global_setting.value != "ENABLED_FOR_SOME_PROJECTS":
            return None
        if "isAiCodeFixEnabled" not in self.sq_json:
            data = self.endpoint.get_paginated(api=Project.API[c.LIST], return_field="components", filter=_PROJECT_QUALIFIER)
            p_data = next((p for p in data["components"] if p["key"] == self.key), None)
            if p_data:
                self.sq_json.update(p_data)
        return self.sq_json.get("isAiCodeFixEnabled", None)

    def __audit_scanner(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits whether the project is analyzed with the right scanner"""
        if audit_settings.get(c.AUDIT_MODE_PARAM, "") == "housekeeper":
            return []
        if not audit_settings.get("audit.projects.scanner", True):
            log.debug("%s: Background task audit disabled, audit skipped", str(self))
            return []
        proj_type, scanner = self.get_type(), self.scanner()
        log.debug("%s is of type %s and uses scanner %s", str(self), proj_type, scanner)
        if proj_type == "UNKNOWN":
            log.info("%s project type can't be identified, skipping check", str(self))
            return []
        if scanner == "UNKNOWN":
            log.info("%s project type or scanner used can't be identified, skipping check", str(self))
            return []
        if proj_type == scanner:
            return []
        return [Problem(get_rule(RuleId.PROJ_WRONG_SCANNER), self, str(self), proj_type, scanner)]

    def __audit_key_pattern(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits whether the project key matches the desired pattern"""
        if audit_settings.get("audit.projects.keyPattern", None) is None:
            log.debug("%s: audit project key pattern is disabled, audit skipped", str(self))
            return []
        if not re.match(rf"^{audit_settings['audit.projects.keyPattern']}$", self.key):
            return [Problem(get_rule(RuleId.PROJ_NON_COMPLIANT_KEY_PATTERN), self, str(self), audit_settings["audit.projects.keyPattern"])]
        else:
            log.debug("%s: matches the desired project key pattern '%s'", str(self), f"^{audit_settings['audit.projects.keyPattern']}$")
            return []

    def audit(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits a project and returns the list of problems found

        :param dict audit_settings: Options of what to audit and thresholds to raise problems
        :return: List of problems found, or empty list
        """
        log.debug("Auditing %s with settings %s", str(self), util.json_dump(audit_settings))
        problems = []
        try:
            problems = self.__audit_last_analysis(audit_settings)
            if audit_settings.get(c.AUDIT_MODE_PARAM, "") != "housekeeper":
                problems += self.audit_visibility(audit_settings)
                problems += self.__audit_binding_valid(audit_settings)
                # Skip language audit, as this can be problematic
                # problems += self.__audit_languages(audit_settings)
                problems += self.permissions().audit(audit_settings)

                problems += self.__audit_scanner(audit_settings)
                problems += self._audit_component(audit_settings)
                problems += self.__audit_key_pattern(audit_settings)
            if self.endpoint.edition() != c.CE and audit_settings.get("audit.project.branches", True):
                problems += self.__audit_branches(audit_settings)
                problems += self.__audit_pull_requests(audit_settings)

        except exceptions.ObjectNotFound:
            Project.CACHE.pop(self)
            raise

        return problems

    def export_zip(self, asynchronous: bool = False, timeout: int = 180) -> tuple[str, Optional[str]]:
        """Exports project as zip file, synchronously

        :param bool asynchronous: Whether to export the project asynchronously or not (if async, export_zip returns immediately)
        :param int timeout: timeout in seconds to complete the export operation
        :returns: export status (success/failure/timeout), and zip file path
        """
        log.info("Exporting %s (%s)", str(self), "asynchronously" if asynchronous else "synchronously")
        if self.endpoint.version() < (9, 2, 0) and self.endpoint.edition() not in (c.EE, c.DCE):
            raise exceptions.UnsupportedOperation(
                "Project export is only available with Enterprise and Datacenter Edition, or with SonarQube 9.2 or higher for any Edition"
            )
        try:
            resp = self.post("project_dump/export", params={"key": self.key})
        except exceptions.ObjectNotFound as e:
            Project.CACHE.pop(self)
            raise
        except exceptions.SonarException as e:
            return f"FAILED/{e.message}", None
        except RequestException as e:
            util.handle_error(e, f"exporting zip of {str(self)}", catch_all=True)
            return f"FAILED/{util.http_error_string(e.response.status_code)}", None
        except ConnectionError as e:
            return str(e), None
        if asynchronous:
            return ZIP_ASYNC_SUCCESS, None
        data = json.loads(resp.text)
        status = tasks.Task(endpoint=self.endpoint, task_id=data["taskId"], concerned_object=self, data=data).wait_for_completion(timeout=timeout)
        if status != tasks.SUCCESS:
            log.error("%s export %s", str(self), status)
            return status, None
        dump_file = json.loads(self.get("project_dump/status", params={"key": self.key}).text)["exportedDump"]
        log.debug("%s export %s, dump file %s", str(self), status, dump_file)
        if self.loc() == 0:
            return f"{tasks.SUCCESS}/{ZIP_ZERO_LOC}", dump_file
        return tasks.SUCCESS, dump_file

    def import_zip(self, asynchronous: bool = False, timeout: int = 180) -> str:
        """Imports a project zip file in SonarQube

        :param bool asynchronous: Whether to export the project asynchronously or not (if async, import_zip returns immediately)
        :param int timeout: timeout in seconds to complete the export operation
        :return: SUCCESS or FAILED with reason
        """
        mode = "asynchronously" if asynchronous else "synchronously"
        log.info("Importing %s (%s)", str(self), mode)
        if self.endpoint.edition() not in (c.EE, c.DCE):
            raise exceptions.UnsupportedOperation("Project import is only available with Enterprise and Datacenter Edition")
        try:
            resp = self.post("project_dump/import", params={"key": self.key})
        except exceptions.ObjectNotFound as e:
            if "Dump file does not exist" in e.message:
                return f"FAILED/{tasks.ZIP_MISSING}"
            Project.CACHE.pop(self)
            raise
        except exceptions.SonarException as e:
            if "Dump file does not exist" in e.message:
                return f"FAILED/{tasks.ZIP_MISSING}"
            return f"FAILED/{e.message}"
        except ConnectionError as e:
            return f"FAILED/{str(e)}"

        if asynchronous:
            return ZIP_ASYNC_SUCCESS

        data = json.loads(resp.text)
        import_task = tasks.Task(endpoint=self.endpoint, task_id=data["taskId"], concerned_object=self, data=data)
        status = import_task.wait_for_completion(timeout=timeout)
        log.log(log.INFO if status == tasks.SUCCESS else log.ERROR, "%s import background task %s", str(self), status)
        return status if status == tasks.SUCCESS else f"FAILED/BACKGROUND_TASK_{status}/{import_task.short_error()}"

    def get_branches_and_prs(self, filters: dict[str, str]) -> Optional[dict[str, object]]:
        """Get lists of branches and PR objects"""
        if not filters:
            return None
        f = filters.copy()
        br = f.pop("branch", None)
        pr = f.pop("pullRequest", None)
        if not br and not pr:
            return None
        objects = {}
        if br:
            if "*" in br:
                objects = self.branches()
            else:
                try:
                    objects = {b: branches.Branch.get_object(concerned_object=self, branch_name=b) for b in br}
                except exceptions.SonarException as e:
                    log.error(e.message)
        if pr:
            if "*" in pr:
                objects.update(self.pull_requests())
            else:
                try:
                    objects.update({p: pull_requests.get_object(project=self, pull_request_key=p) for p in pr})
                except exceptions.SonarException as e:
                    log.error(e.message)
        return objects

    def get_findings(self, branch: Optional[str] = None, pr: Optional[str] = None) -> dict[str, object]:
        """Returns a project list of findings (issues and hotspots)

        :param str branch: optional branch name to consider, if any
        :param str pr: optional PR key to consider, if any
        :return: JSON of all findings, with finding key as key
        :rtype: dict{key: Finding}
        """
        from sonar import issues, hotspots

        if self.endpoint.version() < (9, 1, 0) or self.endpoint.edition() not in (c.EE, c.DCE):
            log.warning("export_findings only available in EE and DCE starting from SonarQube 9.1, returning no issues")
            return {}
        log.info("Exporting findings for %s", str(self))
        findings_list = {}
        params = util.remove_nones({"project": self.key, "branch": branch, "pullRequest": pr})

        data = json.loads(self.get("projects/export_findings", params=params).text)["export_findings"]
        findings_conflicts = {"SECURITY_HOTSPOT": 0, "BUG": 0, "CODE_SMELL": 0, "VULNERABILITY": 0}
        nbr_findings = {"SECURITY_HOTSPOT": 0, "BUG": 0, "CODE_SMELL": 0, "VULNERABILITY": 0}
        for i in data:
            key = i["key"]
            if key in findings_list:
                log.warning("Finding %s (%s) already in past findings", i["key"], i["type"])
                findings_conflicts[i["type"]] += 1
            # FIXME(okorach) - Hack for wrong projectKey returned in PR
            # m = re.search(r"(\w+):PULL_REQUEST:(\w+)", i['projectKey'])
            i["projectKey"] = self.key
            i["branch"] = branch
            i["pullRequest"] = pr
            nbr_findings[i["type"]] += 1
            if i["type"] == "SECURITY_HOTSPOT":
                if i.get("status", "") != "CLOSED":
                    findings_list[key] = hotspots.get_object(endpoint=self.endpoint, key=key, data=i, from_export=True)
            else:
                findings_list[key] = issues.get_object(endpoint=self.endpoint, key=key, data=i, from_export=True)
        for t in ("SECURITY_HOTSPOT", "BUG", "CODE_SMELL", "VULNERABILITY"):
            if findings_conflicts[t] > 0:
                log.warning("%d %s findings missed because of JSON conflict", findings_conflicts[t], t)
        log.info("%d findings exported for %s branch %s PR %s", len(findings_list), str(self), branch, pr)
        for t in ("SECURITY_HOTSPOT", "BUG", "CODE_SMELL", "VULNERABILITY"):
            log.info("%d %s exported", nbr_findings[t], t)

        return findings_list

    def get_hotspots(self, filters: Optional[dict[str, str]] = None) -> dict[str, object]:
        branches_or_prs = self.get_branches_and_prs(filters)
        if branches_or_prs is None:
            return super().get_hotspots(filters)
        findings_list = {}
        for component in [comp for comp in branches_or_prs.values() if comp]:
            findings_list |= component.get_hotspots()
        return findings_list

    def get_issues(self, filters: Optional[dict[str, str]] = None) -> dict[str, object]:
        branches_or_prs = self.get_branches_and_prs(filters)
        if branches_or_prs is None:
            return super().get_issues(filters)
        findings_list = {}
        for component in [comp for comp in branches_or_prs.values() if comp]:
            findings_list |= component.get_issues()
        return findings_list

    def count_third_party_issues(self, filters: Optional[dict[str, str]] = None) -> dict[str, int]:
        if filters:
            filters = {k: [v] for k, v in filters.items() if k in ("branch", "pullRequest")}
        branches_or_prs = self.get_branches_and_prs(filters)
        if branches_or_prs is None:
            return super().count_third_party_issues(filters)
        log.debug("Getting 3rd party issues on branches/PR")
        issue_counts = {}
        for comp in [co for co in branches_or_prs.values() if co]:
            log.debug("Getting 3rd party issues for %s", str(comp))
            for k, total in comp.count_third_party_issues(filters).items():
                if k not in issue_counts:
                    issue_counts[k] = 0
                issue_counts[k] += total
        log.debug("Issues count = %s", str(issue_counts))
        return issue_counts

    def sync(
        self, another_project: Union[Project, branches.Branch], sync_settings: types.ConfigSettings
    ) -> tuple[list[dict[str, str]], dict[str, int]]:
        """Syncs project findings with another project

        :param Project|Branch another_project: other project to sync findings into
        :param dict sync_settings: Parameters to configure the sync
        :return: sync report as tuple, with counts of successful and unsuccessful issue syncs
        :rtype: tuple(report, counters)
        """
        from sonar import syncer

        log.info("Syncing %s with %s", str(self), str(another_project))
        if self.endpoint.edition() == c.CE or another_project.endpoint.edition() == c.CE or isinstance(another_project, branches.Branch):
            # Sync the project main branch only
            return syncer.sync_objects(self, another_project, sync_settings=sync_settings)

        src_branches = self.branches()
        tgt_branches = another_project.branches()
        src_branches_list = list(src_branches.keys())
        tgt_branches_list = list(tgt_branches.keys())
        diff = list(set(src_branches_list) - set(tgt_branches_list))
        if len(diff) > 0:
            log.warning(
                "Source %s has branches that do not exist for target %s, these branches will be ignored: %s",
                str(self),
                str(another_project),
                ", ".join(diff),
            )
        diff = list(set(tgt_branches_list) - set(src_branches_list))
        if len(diff) > 0:
            log.warning(
                "Target %s has branches that do not exist for source %s, these branches will be ignored: %s",
                str(another_project),
                str(self),
                ", ".join(diff),
            )
        report, counters = [], {}
        intersect = list(set(src_branches_list) & set(tgt_branches_list))
        for branch_name in intersect:
            (tmp_report, tmp_counts) = src_branches[branch_name].sync(tgt_branches[branch_name], sync_settings=sync_settings)
            report += tmp_report
            counters = util.dict_add(counters, tmp_counts)
        return (report, counters)

    def sync_branches(self, sync_settings: types.ConfigSettings) -> tuple[list[dict[str, str]], dict[str, int]]:
        """Syncs project issues across all its branches

        :param dict sync_settings: Parameters to configure the sync
        :return: sync report as tuple, with counts of successful and unsuccessful issue syncs
        :rtype: tuple(report, counters)
        """
        my_branches = self.branches().values()
        report, counters = [], {}
        for b_src in my_branches:
            for b_tgt in [b for b in my_branches if b.name != b_src.name]:
                (tmp_report, tmp_counts) = b_src.sync(b_tgt, sync_settings=sync_settings)
                report += tmp_report
                counters = util.dict_add(counters, tmp_counts)
        return (report, counters)

    def quality_profiles(self) -> dict[str, qualityprofiles.QualityProfile]:
        """Returns the project quality profiles

        :return: dict of quality profiles indexed by language
        :rtype: dict{language: QualityProfile}
        """
        log.debug("Getting %s quality profiles", str(self))
        qp_list = qualityprofiles.get_list(self.endpoint)
        return {qp.language: qp for qp in qp_list.values() if qp.used_by_project(self)}

    def quality_gate(self) -> Optional[tuple[str, bool]]:
        """Returns the project quality gate

        :return: name of quality gate and whether it's the default
        :rtype: tuple(name, is_default)
        """
        data = json.loads(self.get(api="qualitygates/get_by_project", params={"project": self.key}).text)
        return data["qualityGate"]["name"], data["qualityGate"]["default"]

    def webhooks(self) -> dict[str, webhooks.WebHook]:
        """
        :return: Project webhooks indexed by their key
        :rtype: dict{key: WebHook}
        """
        log.debug("Getting %s webhooks", str(self))
        return webhooks.get_list(endpoint=self.endpoint, project_key=self.key)

    def links(self) -> Optional[list[dict[str, str]]]:
        """
        :return: list of project links
        :rtype: list[{type, name, url}]
        """
        try:
            data = json.loads(self.get(api="project_links/search", params={"projectKey": self.key}).text)
        except exceptions.SonarException:
            return None
        link_list = None
        for link in data["links"]:
            if link_list is None:
                link_list = []
            link_list.append({"type": link["type"], "name": link.get("name", link["type"]), "url": link["url"]})
        return link_list

    def __export_get_binding(self) -> Optional[types.ObjectJsonRepr]:
        """Exports a binding as JSON"""
        binding = self.binding()
        if binding:
            binding = binding.copy()
            # Remove redundant fields
            binding.pop("alm", None)
            binding.pop("url", None)
            if not binding.get("monorepo", False):
                binding.pop("monorepo", None)
        return binding

    def __export_get_qp(self) -> Optional[types.ObjectJsonRepr]:
        """Exports a QP as JSON"""
        qp_json = {qp.language: f"{qp.name}" for qp in self.quality_profiles().values()}
        if len(qp_json) == 0:
            return None
        return qp_json

    def __get_branch_export(self, export_settings: types.ConfigSettings) -> Optional[types.ObjectJsonRepr]:
        """Export project branches as JSON"""
        branch_data = {name: branch.export(export_settings=export_settings) for name, branch in self.branches().items()}
        # If there is only 1 branch with no specific config except being main, don't return anything
        if len(branch_data) == 0 or (len(branch_data) == 1 and "main" in branch_data and len(branch_data["main"]) <= 1):
            return None
        return util.sort_list_by_key(list(branch_data.values()), "name", "isMain")

    def migration_export(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """Produces the data that is exported for SQ to SC migration"""
        json_data = super().migration_export(export_settings)
        json_data["detectedCi"] = self.ci()
        json_data["revision"] = self.revision()
        last_task = self.last_task()
        json_data["backgroundTasks"] = {}
        if last_task:
            ctxt = last_task.scanner_context()
            if ctxt:
                ctxt = {k: v for k, v in ctxt.items() if k not in _UNNEEDED_CONTEXT_DATA}
            t_hist = []
            for t in self.task_history():
                t_hist.append({k: v for k, v in t.sq_json.items() if k not in _UNNEEDED_TASK_DATA})
            json_data["backgroundTasks"] = {
                "lastTaskScannerContext": ctxt,
                # "lastTaskWarnings": last_task.warnings(),
                "taskHistory": t_hist,
            }
        log.debug("Returning %s migration data %s", str(self), util.json_dump(json_data))
        return json_data

    def export(self, export_settings: types.ConfigSettings, settings_list: Optional[dict[str, str]] = None) -> types.ObjectJsonRepr:
        """Exports the entire project configuration as JSON

        :return: All project configuration settings
        :rtype: dict
        """
        log.info("Exporting %s", str(self))
        json_data = self.sq_json.copy()
        json_data.update({"key": self.key, "name": self.name})
        try:
            json_data["binding"] = self.__export_get_binding()
            nc = self.new_code()
            if nc != "":
                json_data[settings.NEW_CODE_PERIOD] = nc
            json_data["qualityProfiles"] = self.__export_get_qp()
            json_data["links"] = self.links()
            json_data["permissions"] = self.permissions().to_json()
            if self.endpoint.version() >= (10, 7, 0):
                json_data["aiCodeFix"] = self.ai_code_fix()
            json_data["branches"] = self.__get_branch_export(export_settings)
            [b.pop("project") for b in json_data["branches"]]
            json_data["tags"] = self.get_tags()
            json_data["visibility"] = self.visibility()
            (json_data["qualityGate"], qg_is_default) = self.quality_gate()
            if qg_is_default:
                json_data.pop("qualityGate")

            try:
                hooks = webhooks.export(self.endpoint, self.key)
            except exceptions.SonarException:
                hooks = None
            if hooks is not None:
                json_data["webhooks"] = hooks
            json_data = util.filter_export(json_data, _IMPORTABLE_PROPERTIES, export_settings.get("FULL_EXPORT", False))

            if export_settings.get("MODE", "") == "MIGRATION":
                json_data.update(self.migration_export(export_settings))

            with_inherited = export_settings.get("FULL_EXPORT", False)
            settings_list = settings.get_bulk(
                endpoint=self.endpoint, component=self, settings_list=settings_list, include_not_set=with_inherited
            ).values()
            settings_list = [s for s in settings_list if not s.is_global()]
            settings_list = [s for s in settings_list if s.key not in ("visibility", settings.NEW_CODE_PERIOD)]
            if not with_inherited:
                settings_list = [s for s in settings_list if not s.inherited]

            # json_data.update({s.to_json() for s in settings_dict.values() if include_inherited or not s.inherited})
            contains_ai = False
            try:
                ai = self.get_ai_code_assurance()
                contains_ai = ai is not None and ai != "NONE"
            except exceptions.UnsupportedOperation:
                pass
            if contains_ai:
                json_data[_CONTAINS_AI_CODE] = contains_ai
            json_data["settings"] = util.sort_list_by_key([s.to_json() for s in settings_list], "key")
            if not with_inherited:
                [s.pop("isDefault", None) for s in json_data["settings"]]

        except Exception as e:
            util.handle_error(e, f"exporting {str(self)}, export of this project interrupted", catch_all=True)
            json_data["error"] = f"{util.error_msg(e)} while exporting project"
        log.debug("Exporting %s done, returning %s", str(self), util.json_dump(json_data))
        return json_data

    def new_code(self) -> str:
        """
        :return: The project new code definition
        :rtype: str
        """
        if self._new_code is None:
            new_code = settings.Setting.read(settings.NEW_CODE_PERIOD, self.endpoint, component=self)
            self._new_code = new_code.value if new_code else ""
        return self._new_code

    def permissions(self) -> pperms.ProjectPermissions:
        """
        :return: The project permissions
        :rtype: ProjectPermissions
        """
        if self._permissions is None:
            self._permissions = pperms.ProjectPermissions(self)
        return self._permissions

    def set_permissions(self, desired_permissions: types.ObjectJsonRepr) -> bool:
        """Sets project permissions

        :param desired_permissions: dict describing permissions
        :type desired_permissions: dict
        :return: Nothing
        """
        self.permissions().set(desired_permissions)

    def set_links(self, desired_links: types.ObjectJsonRepr) -> bool:
        """Sets project links

        :param desired_links: dict describing links
        :type desired_links: dict
        :return: Whether the operation was successful
        """
        params = {"projectKey": self.key}
        ok = True
        for link in desired_links.get("links", {}):
            if link.get("type", "") != "custom":
                continue
            params.update(link)
            ok = ok and self.post("project_links/create", params=params).ok
        return ok

    def set_quality_gate(self, quality_gate: str) -> bool:
        """Sets project quality gate

        :param quality_gate: quality gate name
        :return: Whether the operation was successful
        """
        if quality_gate is None:
            return False
        qualitygates.QualityGate.get_object(self.endpoint, quality_gate)
        return self.post("qualitygates/select", params={"projectKey": self.key, "gateName": quality_gate}).ok

    def set_contains_ai_code(self, contains_ai_code: bool) -> bool:
        """Sets whether a project contains AI code

        :param contains_ai_code: Whether the project contains AI code
        :return: Whether the operation succeeded
        """
        if self.endpoint.version() < (10, 7, 0) or self.endpoint.edition() == c.CE:
            return False
        api = "projects/set_contains_ai_code"
        if self.endpoint.version() == (10, 7, 0):
            api = "projects/set_ai_code_assurance"
        return self.post(api, params={"project": self.key, "contains_ai_code": str(contains_ai_code).lower()}).ok

    def set_quality_profile(self, language: str, quality_profile: str) -> bool:
        """Sets project quality profile for a given language

        :param language: Language key, following SonarQube convention
        :param quality_profile: Name of the quality profile in the language
        :return: Whether the operation was successful
        """
        if not qualityprofiles.exists(endpoint=self.endpoint, language=language, name=quality_profile):
            log.warning("Quality profile '%s' in language '%s' does not exist, can't set it for %s", quality_profile, language, str(self))
            return False
        log.debug("Setting quality profile '%s' of language '%s' for %s", quality_profile, language, str(self))
        return self.post("qualityprofiles/add_project", params={"project": self.key, "qualityProfile": quality_profile, "language": language}).ok

    def rename_main_branch(self, main_branch_name: str) -> bool:
        """Renames the project main branch

        :param str main_branch_name: New main branch name
        :return: Whether the operation was successful
        """
        br = self.main_branch()
        if br:
            return br.rename(main_branch_name)
        log.warning("No main branch to rename found for %s", str(self))
        return False

    def set_webhooks(self, webhook_data: types.ObjectJsonRepr) -> None:
        """Sets project webhooks

        :param dict webhook_data: JSON describing the webhooks
        :return: Nothing
        """
        webhooks.import_config(self.endpoint, webhook_data, self.key)

    def set_settings(self, data: types.ObjectJsonRepr) -> None:
        """Sets project settings (webhooks, settings, new code period)

        :param dict data: JSON describing the settings
        :return: Nothing
        """
        log.debug("Setting %s settings with %s", str(self), util.json_dump(data))
        for key, value in data.items():
            if key in ("branches", settings.NEW_CODE_PERIOD):
                continue
            if key == "webhooks":
                self.set_webhooks(value)
            else:
                settings.set_setting(endpoint=self.endpoint, key=key, value=value, component=self)

        nc = data.get(settings.NEW_CODE_PERIOD, None)
        if nc is not None:
            (nc_type, nc_val) = settings.decode(settings.NEW_CODE_PERIOD, nc)
            settings.set_new_code_period(self.endpoint, nc_type, nc_val, project_key=self.key)
        # TODO: Update branches (main, new code definition, keepWhenInactive)
        # log.debug("Checking main branch")
        # for branch, branch_data in data.get("branches", {}).items():
        #    if branches.exists(branch_name=branch, project_key=self.key, endpoint=self.endpoint):
        #        branches.get_object(branch, self, endpoint=self.endpoint).update(branch_data)()

    def set_devops_binding(self, data: types.ObjectJsonRepr) -> bool:
        """Sets project devops binding settings

        :param dict data: JSON describing the devops binding
        :return: Nothing
        """
        log.debug("Setting devops binding of %s to %s", str(self), util.json_dump(data))
        if self.endpoint.edition() == c.CE:
            raise exceptions.UnsupportedOperation(f"{str(self)}: Can't set project binding on Community Edition")
        alm_key = data["key"]
        if not devops.exists(endpoint=self.endpoint, key=alm_key):
            log.warning("DevOps platform '%s' does not exists, can't set it for %s", alm_key, str(self))
            return False
        alm_type = devops.devops_type(endpoint=self.endpoint, key=alm_key)
        mono = data.get("monorepo", False)
        repo = data["repository"]
        try:
            if alm_type == "github":
                self.set_binding_github(alm_key, repository=repo, monorepo=mono, summary_comment=data.get("summaryComment", True))
            elif alm_type == "gitlab":
                self.set_binding_gitlab(alm_key, repository=repo, monorepo=mono)
            elif alm_type == "azure":
                self.set_binding_azure_devops(alm_key, repository=repo, monorepo=mono, slug=data["slug"])
            elif alm_type == "bitbucket":
                self.set_binding_bitbucket_server(alm_key, repository=repo, monorepo=mono, slug=data["slug"])
            elif alm_type == "bitbucketcloud":
                self.set_binding_bitbucket_cloud(alm_key, repository=repo, monorepo=mono)
            else:
                log.error("Invalid devops platform type '%s' for %s, setting skipped", alm_key, str(self))
                return False
        except exceptions.UnsupportedOperation as e:
            log.warning(e.message)
        return True

    def __std_binding_params(self, alm_key: str, repo: str, monorepo: bool) -> types.ApiParams:
        return {"almSetting": alm_key, "project": self.key, "repository": repo, "monorepo": str(monorepo).lower()}

    def _check_binding_supported(self) -> bool:
        if self.endpoint.edition() == c.CE:
            raise exceptions.UnsupportedOperation(f"{str(self)}: Can't set project binding on Community Edition")
        return True

    def set_binding_github(self, devops_platform_key: str, repository: str, monorepo: bool = False, summary_comment: bool = True) -> bool:
        """Sets project devops binding for github

        :param str devops_platform_key: key of the platform in the global admin devops configuration
        :param str repository: project repository name in github
        :param monorepo: Whether the project is part of a monorepo, defaults to False
        :type monorepo: bool, optional
        :param summary_comment: Whether summary comments should be posted, defaults to True
        :type summary_comment: bool, optional
        :return: Nothing
        """
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        params["summaryCommentEnabled"] = str(summary_comment).lower()
        return self.post("alm_settings/set_github_binding", params=params).ok

    def set_binding_gitlab(self, devops_platform_key: str, repository: str, monorepo: bool = False) -> bool:
        """Sets project devops binding for gitlab

        :param str devops_platform_key: key of the platform in the global admin devops configuration
        :param str repository: project repository name in gitlab
        :param monorepo: Whether the project is part of a monorepo, defaults to False
        :type monorepo: bool, optional
        :return: Nothing
        """
        self._check_binding_supported()
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        return self.post("alm_settings/set_gitlab_binding", params=params).ok

    def set_binding_bitbucket_server(self, devops_platform_key: str, repository: str, slug: str, monorepo: bool = False) -> bool:
        """Sets project devops binding for bitbucket server

        :param str devops_platform_key: key of the platform in the global admin devops configuration
        :param str repository: project repository name in bitbucket server
        :param str slug: project repository SLUG
        :param monorepo: Whether the project is part of a monorepo, defaults to False
        :type monorepo: bool, optional
        :return: Nothing
        """
        self._check_binding_supported()
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        params["slug"] = slug
        return self.post("alm_settings/set_bitbucket_binding", params=params).ok

    def set_binding_bitbucket_cloud(self, devops_platform_key: str, repository: str, monorepo: bool = False) -> bool:
        """Sets project devops binding for bitbucket cloud

        :param str devops_platform_key: key of the platform in the global admin devops configuration
        :param str repository: project repository name in bitbucket cloud
        :param str slug: project repository SLUG
        :param monorepo: Whether the project is part of a monorepo, defaults to False
        :type monorepo: bool, optional
        :return: Nothing
        """
        self._check_binding_supported()
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        return self.post("alm_settings/set_bitbucketcloud_binding", params=params).ok

    def set_binding_azure_devops(self, devops_platform_key: str, slug: str, repository: str, monorepo: bool = False) -> bool:
        """Sets project devops binding for azure devops

        :param str devops_platform_key: key of the platform in the global admin devops configuration
        :param str slug: project SLUG in Azure DevOps
        :param str repository: project repository name in azure devops
        :param Optional[bool] monorepo: Whether the project is part of a monorepo, defaults to False
        :return: Whether the operation succeeded
        """
        self._check_binding_supported()
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        params["projectName"] = slug
        params["repositoryName"] = params.pop("repository")
        return self.post("alm_settings/set_azure_binding", params=params).ok

    def update(self, config: types.ObjectJsonRepr) -> None:
        """Updates a project with a whole configuration set

        :param config: JSON of configuration settings
        """
        if visi := config.get("visibility", None):
            self.set_visibility(visi)
        if "permissions" in config:
            decoded_perms = {
                p: {u: perms.decode(v) for u, v in config["permissions"][p].items()} for p in perms.PERMISSION_TYPES if p in config["permissions"]
            }
            self.set_permissions(decoded_perms)
        self.set_links(config)
        self.set_tags(util.csv_to_list(config.get("tags", None)))
        self.set_quality_gate(config.get("qualityGate", None))

        for lang, qp_name in config.get("qualityProfiles", {}).items():
            self.set_quality_profile(language=lang, quality_profile=qp_name)
        if branch_config := config.get("branches", None):
            try:
                bname = next(bname for bname, bdata in branch_config.items() if bdata.get("isMain", False))
                self.rename_main_branch(bname)
            except StopIteration:
                log.warning("No main branch defined in %s configuration", self)
            for branch_name, branch_data in branch_config.items():
                try:
                    branch = branches.Branch.get_object(self, branch_name)
                    branch.import_config(branch_data)
                except exceptions.ObjectNotFound:
                    log.warning("Branch '%s' of %s does not exists, can't update its configuuration", branch_name, str(self))
        if "binding" in config:
            try:
                self.set_devops_binding(config["binding"])
            except exceptions.UnsupportedOperation as e:
                log.warning(e.message)
        else:
            log.debug("%s has no devops binding, skipped", str(self))
        settings_to_apply = {k: v for k, v in config.items() if k not in _SETTINGS_WITH_SPECIFIC_IMPORT}
        self.set_settings(settings_to_apply)
        if "aiCodeAssurance" in config:
            log.warning("'aiCodeAssurance' project setting is deprecated, please use '%s' instead", _CONTAINS_AI_CODE)
        self.set_contains_ai_code(config.get(_CONTAINS_AI_CODE, config.get("aiCodeAssurance", False)))
        # TODO: Set branch settings See https://github.com/okorach/sonar-tools/issues/1828

    def api_params(self, op: Optional[str] = None) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {c.READ: {"component": self.key}, c.DELETE: {"project": self.key}, c.SET_TAGS: {"project": self.key}}
        return ops[op] if op and op in ops else {"project": self.key}


def count(endpoint: pf.Platform, params: types.ApiParams = None) -> int:
    """Counts projects

    :param params: list of parameters to filter projects to search
    :type params: dict
    :return: Count of projects
    :rtype: int
    """
    new_params = {} if params is None else params.copy()
    new_params.update({"ps": 1, "p": 1})
    if not endpoint.is_sonarcloud():
        new_params["filter"] = _PROJECT_QUALIFIER
    return util.nbr_total_elements(json.loads(endpoint.get(Project.API[c.LIST], params=params).text))


def search(endpoint: pf.Platform, params: types.ApiParams = None, threads: int = 8) -> dict[str, Project]:
    """Searches projects in SonarQube

    :param Platform endpoint: Reference to the SonarQube platform
    :param ApiParams params: list of filter parameters to narrow down the search
    :param int threads: Number of threads to use for the search
    """
    new_params = {} if params is None else params.copy()
    if not endpoint.is_sonarcloud() and not new_params.get("filter", None):
        new_params["filter"] = _PROJECT_QUALIFIER
    try:
        log.info("Searching projects with parameters: %s", str(new_params))
        return sqobject.search_objects(endpoint=endpoint, object_class=Project, params=new_params, threads=threads)
    except exceptions.TooManyResults as e:
        log.warning(e.message)
        filter_1, filter_2 = putils.split_loc_filter(new_params["filter"])
        return search(endpoint, params={**new_params, "filter": filter_1}, threads=threads) | search(
            endpoint, params={**new_params, "filter": filter_2}, threads=threads
        )


def get_list(endpoint: pf.Platform, key_list: types.KeyList = None, threads: int = 8, use_cache: bool = True) -> dict[str, Project]:
    """
    :param Platform endpoint: Reference to the SonarQube platform
    :param KeyList key_list: List of portfolios keys to get, if None or empty all portfolios are returned
    :param bool use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :return: the list of all projects
    :rtype: dict{key: Project}
    """
    if key_list is None or len(key_list) == 0 or not use_cache:
        with _CLASS_LOCK:
            log.info("Listing projects")
            p_list = dict(sorted(search(endpoint=endpoint, threads=threads).items()))
            return p_list
    return {key: Project.get_object(endpoint, key) for key in sorted(key_list)}


def get_matching_list(endpoint: pf.Platform, pattern: str, threads: int = 8) -> dict[str, Project]:
    """Returns the list of projects whose keys are matching the pattern

    :param Platform endpoint: Reference to the SonarQube platform
    :param str pattern: Regular expression to match project keys
    :return: the list of all projects matching the pattern
    """
    pattern = pattern or ".+"
    log.info("Listing projects matching regexp '%s'", pattern)
    matches = {k: v for k, v in get_list(endpoint, threads=threads).items() if re.match(rf"^{pattern}$", k)}
    log.info("%d project key matching regexp '%s'", len(matches), pattern)
    return matches


def __audit_duplicates(projects_list: dict[str, Project], audit_settings: types.ConfigSettings) -> list[Problem]:
    """Audits for suspected duplicate projects"""
    if audit_settings.get(c.AUDIT_MODE_PARAM, "") == "housekeeper":
        return []
    if not audit_settings.get("audit.projects.duplicates", True):
        log.info("Project duplicates auditing was disabled by configuration")
        return []
    log.info("Auditing for potential duplicate projects")
    duplicates = []
    pair_set = set()
    for key1, p in projects_list.items():
        for key2 in projects_list:
            pair = " ".join(sorted([key1, key2]))
            if util.similar_strings(key1, key2, audit_settings.get("audit.projects.duplicates.maxDifferences", 4)) and pair not in pair_set:
                duplicates.append(Problem(get_rule(RuleId.PROJ_DUPLICATE), p, str(p), key2))
            pair_set.add(pair)
    return duplicates


def __audit_bindings(projects_list: dict[str, Project], audit_settings: types.ConfigSettings) -> list[Problem]:
    """Audits for duplicate project bindings"""
    if audit_settings.get(c.AUDIT_MODE_PARAM, "") == "housekeeper":
        return []
    if not audit_settings.get("audit.projects.bindings", True):
        log.info("Project bindings auditing was disabled by configuration")
        return []

    log.info("Auditing for duplicate project bindings")
    bindings = {}
    problems = []
    for project in projects_list.values():
        if (bindkey := project.binding_key()) is not None and bindkey in bindings:
            problems.append(Problem(get_rule(RuleId.PROJ_DUPLICATE_BINDING), project, str(project), str(bindings[bindkey])))
        bindings[bindkey] = project
    return problems


def audit(endpoint: pf.Platform, audit_settings: types.ConfigSettings, **kwargs) -> list[Problem]:
    """Audits all or a list of projects

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings audit_settings: Configuration of audit
    :return: list of problems found
    """
    if not audit_settings.get("audit.projects", True):
        log.info("Auditing projects is disabled, audit skipped...")
        return []
    log.info("--- Auditing projects: START ---")
    key_regexp = kwargs.get("key_list", ".+")
    threads = audit_settings.get("threads", 4)
    plist = {k: v for k, v in get_list(endpoint, threads=threads).items() if not key_regexp or re.match(key_regexp, v.key)}
    write_q = kwargs.get("write_q", None)
    total, current = len(plist), 0
    problems = []
    futures, futures_map = [], {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix="ProjectAudit") as executor:
        for project in plist.values():
            futures.append(future := executor.submit(Project.audit, project, audit_settings))
            futures_map[future] = project
        for future in concurrent.futures.as_completed(futures):
            try:
                problems += (proj_pbs := future.result(timeout=60))
                write_q and write_q.put(proj_pbs)
            except (TimeoutError, RequestException, exceptions.SonarException) as e:
                log.error(f"Exception {str(e)} when auditing {str(futures_map[future])}.")
            current += 1
            lvl = log.INFO if current % 10 == 0 or total - current < 10 else log.DEBUG
            log.log(lvl, "%d/%d projects audited (%d%%)", current, total, (current * 100) // total)
    log.debug("Projects audit complete, auditing bindings and duplicates")
    for audit_func in __audit_bindings, __audit_duplicates:
        problems += (more_pbs := audit_func(plist, audit_settings))
        write_q and write_q.put(more_pbs)
    log.info("--- Auditing projects: END ---")
    return problems


def export(endpoint: pf.Platform, export_settings: types.ConfigSettings, **kwargs) -> types.ObjectJsonRepr:
    """Exports all or a list of projects configuration as dict

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings export_settings: Export parameters
    :return: list of projects settings
    """

    write_q = kwargs.get("write_q", None)
    key_regexp = kwargs.get("key_list", ".+")
    nb_threads = export_settings.get("threads", 8)
    for qp in qualityprofiles.get_list(endpoint).values():
        qp.projects()
    proj_list = {k: v for k, v in get_list(endpoint=endpoint, threads=nb_threads).items() if not key_regexp or re.match(rf"^{key_regexp}$", k)}
    total, current = len(proj_list), 0
    log.info("Exporting %d projects", total)
    results = {}
    futures, futures_map = [], {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=nb_threads, thread_name_prefix="ProjectExport") as executor:
        for project in proj_list.values():
            futures.append(future := executor.submit(Project.export, project, export_settings, None))
            futures_map[future] = project
        for future in concurrent.futures.as_completed(futures):
            try:
                exp_json = future.result(timeout=60)
                write_q and write_q.put(exp_json)
                results[futures_map[future].key] = exp_json
            except (TimeoutError, RequestException, exceptions.SonarException) as e:
                log.error(f"Exception {str(e)} when exporting {str(futures_map[future])}.")
            current += 1
            lvl = log.INFO if current % 10 == 0 or total - current < 10 else log.DEBUG
            log.log(lvl, "%d/%d projects exported (%d%%)", current, total, (current * 100) // total)
    log.debug("Projects export complete")
    write_q and write_q.put(util.WRITE_END)
    return list(dict(sorted(results.items())).values())


def exists(endpoint: pf.Platform, key: str) -> bool:
    """Returns whether a project exists

    :param Platform endpoint: reference to the SonarQube platform
    :param str key: project key to check
    :return: whether the project exists
    """
    try:
        Project.get_object(endpoint, key)
        return True
    except exceptions.ObjectNotFound:
        return False


def import_config(endpoint: pf.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> None:
    """Imports a configuration in SonarQube

    :param Platform endpoint: reference to the SonarQube platform
    :param ObjectJsonRepr config_data: the configuration to import
    :param KeyList key_list: List of project keys to be considered for the import, defaults to None (all projects)
    :returns: Nothing
    """
    if "projects" not in config_data:
        log.info("No projects to import")
        return
    log.info("Importing projects")
    get_list(endpoint=endpoint)
    nb_projects = len(config_data["projects"])
    i = 0
    new_key_list = util.csv_to_list(key_list)
    for key, data in config_data["projects"].items():
        if new_key_list and key not in new_key_list:
            continue
        log.info("Importing project key '%s'", key)
        try:
            o = Project.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            try:
                o = Project.create(endpoint, key, data["name"])
            except exceptions.ObjectAlreadyExists as e:
                log.warning("Can't create project with key '%s', %s", key, e.message)
                continue
        o.update(data)
        i += 1
        if i % 20 == 0 or i == nb_projects:
            log.info("Imported %d/%d projects (%d%%)", i, nb_projects, (i * 100 // nb_projects))


def __export_zip_thread(project: Project, export_timeout: int) -> dict[str, str]:
    """Thread callable for project zip export"""
    try:
        status, file = project.export_zip(timeout=export_timeout)
    except exceptions.UnsupportedOperation:
        util.final_exit(errcodes.UNSUPPORTED_OPERATION, "Zip export unsupported on your SonarQube version")
    log.debug("Exporting thread for %s done, status: %s", str(project), status)
    data = {"key": project.key, "exportProjectUrl": project.url(), "exportStatus": status}
    if status.startswith(tasks.SUCCESS):
        data["file"] = os.path.basename(file)
        data["exportPath"] = file
        data["exportDate"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log.debug("Exporting thread for %s returns %s", str(project), str(data))
    return data


def export_zips(
    endpoint: pf.Platform, key_regexp: Optional[str] = None, threads: int = 8, export_timeout: int = 30, skip_zero_loc: bool = False
) -> list[dict[str, str]]:
    """Export as zip all or a list of projects

    :param Platform endpoint: reference to the SonarQube platform
    :param str key_regexp: Regexp to filter projects to export, defaults to None (all projects)
    :param int threads: Number of parallel threads for export, defaults to 8
    :param int export_timeout: Timeout to export the project, defaults to 30
    :return: list of exported projects with export result
    """
    statuses, results = {"SUCCESS": 0}, []
    projects_list = {k: p for k, p in get_list(endpoint, threads=threads).items() if not key_regexp or re.match(rf"^{key_regexp}$", p.key)}
    nbr_projects = len(projects_list)
    if skip_zero_loc:
        results = [
            {"key": p.key, "exportProjectUrl": p.url(), "exportStatus": f"SKIPPED/{ZIP_ZERO_LOC}"} for p in projects_list.values() if p.loc() == 0
        ]
        statuses[f"SKIPPED/{ZIP_ZERO_LOC}"] = len(results)
        projects_list = {k: v for k, v in projects_list.items() if v.loc() > 0}
        log.info("Skipping export of %d projects with 0 LoC", nbr_projects - len(projects_list))
        nbr_projects = len(projects_list)
    log.info("Exporting %d projects", nbr_projects)
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix="ProjZipExport") as executor:
        futures, futures_map = [], {}
        for proj in projects_list.values():
            future = executor.submit(__export_zip_thread, proj, export_timeout)
            futures.append(future)
            futures_map[future] = proj
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result(timeout=export_timeout + 10)  # Retrieve result or raise an exception
                status = result["exportStatus"]
            except TimeoutError as e:
                status = f"{ZIP_TIMEOUT}({export_timeout}s)"
                result = {"key": futures_map[future].key, "exportProjectUrl": futures_map[future].url(), "exportStatus": status}
                log.error(f"Project Zip export timed out after {export_timeout} seconds for {str(future)}.")
            except Exception as e:
                status = f"{ZIP_EXCEPTION}({e})"
                result = {"key": futures_map[future].key, "exportProjectUrl": futures_map[future].url(), "exportStatus": status}

            if re.match(r"\d\d\d .*", status):
                status = f"FAILED/HTTP_ERROR {status[0:3]}"
            elif status.startswith("TIMEOUT"):
                status = ZIP_TIMEOUT
            elif status.startswith("EXCEPTION"):
                status = ZIP_EXCEPTION
            try:
                conflict = next(proj for proj in results if proj.get("file", "") == result.get("file", " "))
                conflict["exportStatus"] = ZIP_CONFLICT
                statuses[tasks.SUCCESS] -= 1
                log.critical("Zip file export conflict detected between project keys '%s' and '%s'", result["key"], conflict["key"])
                statuses[ZIP_CONFLICT] = 1 if ZIP_CONFLICT not in statuses else statuses[ZIP_CONFLICT] + 1
            except StopIteration:
                pass
            results.append(result)
            statuses[status] = 1 if status not in statuses else statuses[status] + 1
            log.info("%s", ", ".join([f"{k}:{v}" for k, v in statuses.items()]))

    return results


def import_zip(endpoint: pf.Platform, project_key: str, import_timeout: int = 30) -> tuple[Project, str]:
    """Imports a project zip file"""
    try:
        o_proj = Project.create(key=project_key, endpoint=endpoint, name=project_key)
    except exceptions.ObjectAlreadyExists:
        o_proj = Project.get_object(key=project_key, endpoint=endpoint)
    if o_proj.last_analysis() is None:
        s = o_proj.import_zip(asynchronous=False, timeout=import_timeout)
    else:
        s = ZIP_PROJ_EXISTS
    return o_proj, s


def import_zips(endpoint: pf.Platform, project_list: list[str], threads: int = 2, import_timeout: int = 60) -> dict[str, Project]:
    """Imports as zip all or a list of projects

    :param Platform endpoint: reference to the SonarQube platform
    :param int threads: Number of parallel threads for export, defaults to 2
    :param int import_timeout: Timeout to import the project, defaults to 60 s
    :return: import results
    """

    if endpoint.edition() not in (c.EE, c.DCE):
        raise exceptions.UnsupportedOperation(f"Zip import unsupported on {endpoint.edition()} edition")
    nb_projects = len(project_list)
    log.info("Importing zip of %d projects", nb_projects)
    i = 0
    statuses_count = {tasks.SUCCESS: 0}
    statuses = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix="ProjZipImport") as executor:
        futures, futures_map = [], {}
        for proj in project_list:
            future = executor.submit(import_zip, endpoint, proj, import_timeout)
            futures.append(future)
            futures_map[future] = proj
        for future in concurrent.futures.as_completed(futures):
            o_proj = None
            try:
                o_proj, status = future.result(timeout=import_timeout + 10)  # Retrieve result or raise an exception
            except TimeoutError as e:
                status = f"TIMEOUT Exception {e}"
                log.error(f"Project Zip import timed out after {import_timeout} seconds for {str(future)}.")
            except Exception as e:
                status = f"EXCEPTION {e}"
            statuses_count[status] = statuses_count[status] + 1 if status in statuses_count else 1
            if o_proj is None:
                proj_key = futures_map[future]
                statuses[proj_key] = {"importStatus": status}
            else:
                proj_key = o_proj.key
                statuses[proj_key] = {
                    "importDate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "importProjectUrl": o_proj.url(),
                    "importStatus": status,
                }

            i += 1
            log.info("%d/%d imports (%d%%) - Latest: %s - %s", i, nb_projects, int(i * 100 / nb_projects), proj_key, status)
            log.info("%s", ", ".join([f"{k}:{v}" for k, v in statuses_count.items()]))
    return statuses


def convert_proj_for_yaml(proj_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    if "branches" in proj_json:
        proj_json["branches"] = util.dict_to_list(proj_json["branches"], "name")
    if "qualityProfiles" in proj_json:
        proj_json["qualityProfiles"] = util.dict_to_list(proj_json["qualityProfiles"], "language", "name")
    if "permissions" in proj_json:
        proj_json["permissions"] = perms.convert_for_yaml(proj_json["permissions"])
    return proj_json


def convert_for_yaml(original_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    return original_json
