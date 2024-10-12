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

    Abstraction of the SonarQube "project" concept

"""

from __future__ import annotations

import os
import re
import json
from datetime import datetime

from typing import Union, Optional
from http import HTTPStatus
from threading import Thread, Lock
from queue import Queue
from requests import HTTPError, RequestException

import sonar.logging as log
import sonar.platform as pf

from sonar.util import types

from sonar import exceptions, errcodes
from sonar import sqobject, components, qualitygates, qualityprofiles, tasks, settings, webhooks, devops
import sonar.permissions.permissions as perms
from sonar import pull_requests, branches
import sonar.utilities as util
import sonar.permissions.project_permissions as pperms

from sonar.audit import severities
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem

_OBJECTS = {}
_CLASS_LOCK = Lock()

MAX_PAGE_SIZE = 500
_CREATE_API = "projects/create"
_NAV_API = "navigation/component"
_TREE_API = "components/tree"
PRJ_QUALIFIER = "TRK"
APP_QUALIFIER = "APP"

_BIND_SEP = ":::"
_AUDIT_BRANCHES_PARAM = "audit.projects.branches"

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
)

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


class Project(components.Component):
    """
    Abstraction of the SonarQube project concept
    """

    SEARCH_API = "projects/search"
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "components"

    def __init__(self, endpoint: pf.Platform, key: str) -> None:
        """
        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: The project key
        """
        super().__init__(endpoint=endpoint, key=key)
        self._last_analysis = "undefined"
        self._branches_last_analysis = "undefined"
        self._permissions = None
        self._branches = None
        self._pull_requests = None
        self._ncloc_with_branches = None
        self._binding = {"has_binding": True, "binding": None}
        self._new_code = None
        self._ci = None
        self._revision = None
        _OBJECTS[self.uuid()] = self
        log.debug("Created object %s", str(self))

    @classmethod
    def get_object(cls, endpoint: pf.Platform, key: str) -> Project:
        """Creates a project from a search in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Project key to search
        :raises ObjectNotFound: if project key not found
        :return: The Project
        :rtype: Project
        """
        uu = sqobject.uuid(key, endpoint.url)
        if uu in _OBJECTS:
            return _OBJECTS[uu]
        try:
            data = json.loads(endpoint.get(Project.SEARCH_API, params={"projects": key}, mute=(HTTPStatus.FORBIDDEN,)).text)
            if len(data["components"]) == 0:
                log.error("Project key '%s' not found", key)
                raise exceptions.ObjectNotFound(key, f"Project key '{key}' not found")
            return cls.load(endpoint, data["components"][0])
        except (ConnectionError, RequestException) as e:
            if not isinstance(e, HTTPError) or e.response.status_code != HTTPStatus.FORBIDDEN:
                log.error("%s while getting project '%s'", util.error_msg(e), key)
                raise
            data = json.loads(endpoint.get(_NAV_API, params={"component": key}).text)
            if "errors" in data:
                raise exceptions.ObjectNotFound(key, f"Project key '{key}' not found")
            return cls.load(endpoint, data)

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
        uu = sqobject.uuid(key, endpoint.url)
        if uu in _OBJECTS:
            o = _OBJECTS[uu]
        else:
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
        try:
            endpoint.post(_CREATE_API, params={"project": key, "name": name})
        except (ConnectionError, RequestException) as e:
            if isinstance(e, HTTPError) and e.response.status_code == HTTPStatus.BAD_REQUEST:
                raise exceptions.ObjectAlreadyExists(key, e.response.text)
            log.error("%s while creating project '%s'", util.error_msg(e), key)
            raise
        o = cls(endpoint, key)
        o.name = name
        return o

    def __str__(self) -> str:
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"project '{self.key}'"

    def refresh(self) -> Project:
        """Refresh a project from SonarQube

        :raises ObjectNotFound: if project key not found
        :return: self
        :rtype: Project
        """
        data = json.loads(self.get(Project.SEARCH_API, params={"projects": self.key}).text)
        if len(data["components"]) == 0:
            _OBJECTS.pop(self.uuid(), None)
            raise exceptions.ObjectNotFound(self.key, f"Project key {self.key} not found")
        return self.reload(data["components"][0])

    def reload(self, data: types.ApiPayload) -> Project:
        """Reloads a project with JSON data coming from api/components/search request

        :param dict data: Data to load
        :return: self
        :rtype: Project
        """
        """Loads a project object with contents of an api/projects/search call"""
        if self._json is None:
            self._json = data
        else:
            self._json.update(data)
        self.name = data["name"]
        self._visibility = data["visibility"]
        if "lastAnalysisDate" in data:
            self._last_analysis = util.string_to_date(data["lastAnalysisDate"])
        elif "analysisDate" in data:
            self._last_analysis = util.string_to_date(data["analysisDate"])
        else:
            self._last_analysis = None
        self._revision = data.get("revision", self._revision)
        return self

    def url(self) -> str:
        """
        :return: the SonarQube permalink to the project
        :rtype: str
        """
        return f"{self.endpoint.url}/dashboard?id={self.key}"

    def last_analysis(self, include_branches: bool = False) -> datetime:
        """
        :param include_branches: Take into account branch to determine last analysis, defaults to False
        :type include_branches: bool, optional
        :return: Project last analysis date
        :rtype: datetime
        """
        if self._last_analysis == "undefined":
            self.refresh()
        if not include_branches:
            return self._last_analysis
        if self._branches_last_analysis != "undefined":
            return self._branches_last_analysis

        self._branches_last_analysis = self._last_analysis
        if self.endpoint.version() >= (9, 2, 0):
            # Starting from 9.2 project last analysis date takes into account branches and PR
            return self._branches_last_analysis

        log.debug("Branches = %s", str(self.branches().values()))
        log.debug("PR = %s", str(self.pull_requests().values()))
        for b in list(self.branches().values()) + list(self.pull_requests().values()):
            if b.last_analysis() is None:
                continue
            b_ana_date = b.last_analysis()
            if self._branches_last_analysis is None or b_ana_date > self._branches_last_analysis:
                self._branches_last_analysis = b_ana_date
        return self._branches_last_analysis

    def loc(self):
        """
        :return: Number of LoCs of the project, taking into account branches and pull requests, if any
        :rtype: int
        """
        if self._ncloc_with_branches is not None:
            return self._ncloc_with_branches
        if self.endpoint.edition() == "community":
            self._ncloc_with_branches = super().loc()
        else:
            self._ncloc_with_branches = max([b.loc() for b in list(self.branches().values()) + list(self.pull_requests().values())])
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

    def main_branch(self):
        """
        :return: Main branch of the project
        :rtype: Branch
        """
        for b in self.branches().values():
            if b.is_main():
                return b
        if self.endpoint.edition() != "community":
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

    def delete(self):
        """Deletes a project in SonarQube

        :raises ObjectNotFound: If object to delete was not found in SonarQube
        :raises request.HTTPError: In all other cases of HTTP Errors
        :return: Nothing
        """
        loc = int(self.get_measure("ncloc", fallback="0"))
        log.info("Deleting %s, name '%s' with %d LoCs", str(self), self.name, loc)
        ok = sqobject.delete_object(self, "projects/delete", {"project": self.key}, _OBJECTS)
        log.info("Successfully deleted %s - %d LoCs", str(self), loc)
        return ok

    def has_binding(self):
        """
        :return: Whether the project has a DevOps platform binding
        :rtype: bool
        """
        _ = self.binding()
        return self._binding.get("has_binding", False)

    def binding(self):
        """
        :return: The project DevOps platform binding
        :rtype: dict
        """
        if self._binding["has_binding"] and self._binding["binding"] is None:
            try:
                resp = self.get("alm_settings/get_binding", params={"project": self.key}, mute=(HTTPStatus.NOT_FOUND,))
                self._binding["has_binding"] = True
                self._binding["binding"] = json.loads(resp.text)
            except (ConnectionError, RequestException) as e:
                if isinstance(e, HTTPError) and e.response.status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.BAD_REQUEST):
                    # Hack: 8.9 returns 404, 9.x returns 400
                    self._binding["has_binding"] = False
                else:
                    log.error("%s while getting '%s' bindinfs", util.error_msg(e), str(self))
                    raise e
        log.debug("Binding = %s", util.json_dump(self._binding["binding"]))
        return self._binding["binding"]

    def is_part_of_monorepo(self) -> bool:
        """
        :return: From the DevOps binding, Whether the project is part of a monorepo
        :rtype: bool
        """
        bind = self.binding()
        return bind is not None and bind.get("has_binding", False) and bind.get("monorepo", False)

    def binding_key(self) -> Union[str, None]:
        """Computes a unique project binding key

        :meta private:
        """
        p_bind = self.binding()
        if p_bind is None or not p_bind.get("has_binding", False):
            return None
        key = p_bind["alm"] + _BIND_SEP + p_bind["repository"]
        if p_bind["alm"] in ("azure", "bitbucket"):
            key += _BIND_SEP + p_bind["slug"]
        return key

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
            if branch.name in ("main", "master"):
                main_br_count += 1
                if main_br_count > 1:
                    problems.append(Problem(get_rule(RuleId.PROJ_MAIN_AND_MASTER), self, str(self)))
        return problems

    def __audit_pull_requests(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits project pul requests

        :param audit_settings: Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        max_age = audit_settings.get("audit.projects.pullRequests.maxLastAnalysisAge", 30)
        if max_age == 0:
            log.debug("Auditing of pull request last analysis age is disabled, skipping...")
            return []
        problems = []
        for pr in self.pull_requests().values():
            problems += pr.audit(audit_settings)
        return problems

    def __audit_visibility(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits project visibility and return problems if project is public

        :param audit_settings: Options and Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        if not audit_settings.get("audit.projects.visibility", True):
            log.debug("Project visibility audit is disabled by configuration, skipping...")
            return []
        log.debug("Auditing %s visibility", str(self))
        visi = self.visibility()
        if visi != "private":
            return [Problem(get_rule(RuleId.PROJ_VISIBILITY), self, str(self), visi)]
        log.debug("%s visibility is 'private'", str(self))
        return []

    def __audit_languages(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits project utility languages and returns problems if too many LoCs of these

        :param audit_settings: Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
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

    def __audit_zero_loc(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits project utility projects with 0 LoCs

        :param audit_settings: Settings (thresholds) to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        if (
            (not audit_settings.get(_AUDIT_BRANCHES_PARAM, True) or self.endpoint.edition() == "community")
            and self.last_analysis() is not None
            and self.loc() == 0
        ):
            return [Problem(get_rule(RuleId.PROJ_ZERO_LOC), self, str(self))]
        return []

    def __audit_binding_valid(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        if self.endpoint.edition() == "community":
            log.info("Community edition, skipping binding validation...")
            return []
        elif not audit_settings.get("audit.projects.bindings", True):
            log.info(
                "%s binding validation disabled, skipped",
                str(self),
            )
        elif not self.has_binding():
            log.info(
                "%s has no binding, skipping binding validation...",
                str(self),
            )
            return []
        try:
            _ = self.get("alm_settings/validate_binding", params={"project": self.key})
            log.debug("%s binding is valid", str(self))
        except (ConnectionError, RequestException) as e:
            # Hack: 8.9 returns 404, 9.x returns 400
            if isinstance(e, HTTPError) and e.response.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
                return [Problem(get_rule(RuleId.PROJ_INVALID_BINDING), self, str(self))]
            log.error("%s while auditing %s binding, skipped", util.error_msg(e), str(self))
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
        for comp in data["components"]:
            if re.match(r".*\.(cs|csx|vb)$", comp["name"]):
                log.info("%s is a DOTNET project", str(self))
                return "DOTNET"
        data = json.loads(self.get(api=_TREE_API, params={"component": self.key, "ps": 500}).text)
        for comp in data["components"]:
            if re.match(r".*\.(java)$", comp["name"]):
                log.info("%s is a JAVA project", str(self))
                return "JAVA"
        data = json.loads(self.get(api=_TREE_API, params={"component": self.key, "ps": 500}).text)
        for comp in data["components"]:
            if re.match(r".*\.(py|rb|cbl|vbs|go|js|ts)$", comp["name"]):
                log.info("%s is a DOTNET project", str(self))
                return "CLI"
        return "UNKNOWN"

    def last_task(self) -> Optional[tasks.Task]:
        """Returns the last analysis background task of a problem, or none if not found"""
        return tasks.search_last(component_key=self.key, endpoint=self.endpoint, type="REPORT")

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
            except (ConnectionError, RequestException) as e:
                log.warning("%s while getting %s CI tool", util.error_msg(e), str(self))
            except KeyError:
                log.warning("KeyError, can't retrieve CI tool and revision")
        return self._ci

    def revision(self) -> str:
        """Returns the last analysis commit, or unknown if HTTP request fails or no revision"""
        log.debug("Collecting revision")
        if not self._revision:
            self.ci()
        return self._revision

    def __audit_scanner(self, audit_settings: types.ConfigSettings) -> list[Problem]:
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

    def audit(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits a project and returns the list of problems found

        :param dict audit_settings: Options of what to audit and thresholds to raise problems
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        log.debug("Auditing %s", str(self))
        problems = []
        try:
            problems = self.__audit_last_analysis(audit_settings)
            problems += self.__audit_visibility(audit_settings)
            problems += self.__audit_zero_loc(audit_settings)
            # Skip language audit, as this can be problematic
            # problems += self.__audit_languages(audit_settings)
            problems += self.permissions().audit(audit_settings)
            problems += self.__audit_branches(audit_settings)
            problems += self.__audit_pull_requests(audit_settings)
            problems += self._audit_bg_task(audit_settings)
            problems += self.__audit_binding_valid(audit_settings)
            problems += self.__audit_scanner(audit_settings)
        except (ConnectionError, RequestException) as e:
            if isinstance(e, HTTPError) and e.response.status_code == HTTPStatus.FORBIDDEN:
                log.error("Not enough permission to fully audit %s", str(self))
            else:
                log.error("%s while auditing %s", util.error_msg(e), str(self))
        return problems

    def export_zip(self, timeout: int = 180) -> dict[str, str]:
        """Exports project as zip file, synchronously

        :param timeout: timeout in seconds to complete the export operation
        :type timeout: int
        :return: export status (success/failure/timeout), and zip file path
        :rtype: dict
        """
        log.info("Exporting %s (synchronously)", str(self))
        if self.endpoint.version() < (9, 2, 0) and self.endpoint.edition() not in ("enterprise", "datacenter"):
            raise exceptions.UnsupportedOperation(
                "Project export is only available with Enterprise and Datacenter Edition, or with SonarQube 9.2 or higher for any Edition"
            )
        try:
            resp = self.post("project_dump/export", params={"key": self.key})
        except HTTPError as e:
            return {"status": f"HTTP_ERROR {e.response.status_code}"}
        except (ConnectionError, RequestException) as e:
            return {"status": str(e)}
        data = json.loads(resp.text)
        status = tasks.Task(endpoint=self.endpoint, task_id=data["taskId"], concerned_object=self, data=data).wait_for_completion(timeout=timeout)
        if status != tasks.SUCCESS:
            log.error("%s export %s", str(self), status)
            return {"status": status}
        dump_file = json.loads(self.get("project_dump/status", params={"key": self.key}).text)["exportedDump"]
        log.debug("%s export %s, dump file %s", str(self), status, dump_file)
        return {"status": status, "file": dump_file}

    def export_async(self) -> Union[str, None]:
        """Export project as zip file, synchronously

        :return: export taskId or None if starting the export failed
        :rtype: str or None
        """
        log.info("Exporting %s (asynchronously)", str(self))
        try:
            return json.loads(self.post("project_dump/export", params={"key": self.key}).text)["taskId"]
        except (ConnectionError, RequestException) as e:
            log.error("%s while exporting zip of %s CI", util.error_msg(e), str(self))
        return None

    def import_zip(self) -> bool:
        """Imports a project zip file in SonarQube

        :raises http.HTTPError:
        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.info("Importing %s (asynchronously)", str(self))
        if self.endpoint.edition() not in ("enterprise", "datacenter"):
            raise exceptions.UnsupportedOperation("Project import is only available with Enterprise and Datacenter Edition")
        return self.post("project_dump/import", params={"key": self.key}).ok

    def get_branches_and_prs(self, filters: dict[str, str]) -> Union[None, dict[str, object]]:
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
                    for b in br:
                        objects[b] = branches.Branch.get_object(concerned_object=self, branch_name=b)
                except (exceptions.ObjectNotFound, exceptions.UnsupportedOperation) as e:
                    log.error(e.message)
        if pr:
            if "*" in pr:
                pr = self.pull_requests()
                objects = {**objects, **pr}
            else:
                for p in pr:
                    try:
                        objects[p] = pull_requests.get_object(project=self, pull_request_key=p)
                    except exceptions.ObjectNotFound as e:
                        log.error(e.message)
        return objects

    def get_findings(self, branch: str = None, pr: str = None) -> dict[str, object]:
        """Returns a project list of findings (issues and hotspots)

        :param branch: branch name to consider, if any
        :type branch: str, optional
        :param pr: PR key to consider, if any
        :type pr: str, optional
        :return: JSON of all findings, with finding key as key
        :rtype: dict{key: Finding}
        """
        from sonar import issues, hotspots

        if self.endpoint.version() < (9, 1, 0) or self.endpoint.edition() not in ("enterprise", "datacenter"):
            log.warning("export_findings only available in EE and DCE starting from SonarQube 9.1, returning no issues")
            return {}
        log.info("Exporting findings for %s", str(self))
        findings_list = {}
        params = {"project": self.key}
        if branch is not None:
            params["branch"] = branch
        elif pr is not None:
            params["pullRequest"] = pr

        data = json.loads(self.get("projects/export_findings", params=params).text)["export_findings"]
        findings_conflicts = {"SECURITY_HOTSPOT": 0, "BUG": 0, "CODE_SMELL": 0, "VULNERABILITY": 0}
        nbr_findings = {"SECURITY_HOTSPOT": 0, "BUG": 0, "CODE_SMELL": 0, "VULNERABILITY": 0}
        log.debug(util.json_dump(data))
        for i in data:
            key = i["key"]
            if key in findings_list:
                log.warning("Finding %s (%s) already in past findings", i["key"], i["type"])
                findings_conflicts[i["type"]] += 1
            # FIXME - Hack for wrong projectKey returned in PR
            # m = re.search(r"(\w+):PULL_REQUEST:(\w+)", i['projectKey'])
            i["projectKey"] = self.key
            i["branch"] = branch
            i["pullRequest"] = pr
            nbr_findings[i["type"]] += 1
            if i["type"] == "SECURITY_HOTSPOT":
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

    def get_hotspots(self, filters: dict[str, str] = None) -> dict[str, object]:
        branches_or_prs = self.get_branches_and_prs(filters)
        if branches_or_prs is None:
            return super().get_hotspots(filters)
        findings_list = {}
        for comp in branches_or_prs.values():
            if comp:
                findings_list = {**findings_list, **comp.get_hotspots()}
        return findings_list

    def get_issues(self, filters: dict[str, str] = None) -> dict[str, object]:
        branches_or_prs = self.get_branches_and_prs(filters)
        if branches_or_prs is None:
            return super().get_issues(filters)
        findings_list = {}
        for comp in branches_or_prs.values():
            if comp:
                findings_list = {**findings_list, **comp.get_issues()}
        return findings_list

    def count_third_party_issues(self, filters: dict[str, str] = None) -> dict[str, int]:
        branches_or_prs = self.get_branches_and_prs(filters)
        if branches_or_prs is None:
            return super().count_third_party_issues(filters)
        issue_counts = {}
        for comp in branches_or_prs.values():
            if not comp:
                continue
            for k, total in comp.count_third_party_issues(filters):
                if k not in issue_counts:
                    issue_counts[k] = 0
                issue_counts[k] += total
        return issue_counts

    def __sync_community(self, another_project: object, sync_settings: types.ConfigSettings) -> tuple[list[dict[str, str]], dict[str, int]]:
        """Syncs 2 projects findings on a community edition"""
        from sonar import syncer

        report, counters = [], {}
        log.info("Syncing %s and %s issues", str(self), str(another_project))
        (report, counters) = syncer.sync_lists(
            list(self.get_issues().values()),
            list(another_project.get_issues().values()),
            self,
            another_project,
            sync_settings=sync_settings,
        )
        log.info("Syncing %s and %s hotspots", str(self), str(another_project))
        (tmp_report, tmp_counts) = syncer.sync_lists(
            list(self.get_hotspots().values()),
            list(another_project.get_hotspots().values()),
            self,
            another_project,
            sync_settings=sync_settings,
        )
        report += tmp_report
        counters = util.dict_add(counters, tmp_counts)
        return report, counters

    def sync(self, another_project: Project, sync_settings: types.ConfigSettings) -> tuple[list[dict[str, str]], dict[str, int]]:
        """Syncs project findings with another project

        :param Project another_project: other project to sync findings into
        :param dict sync_settings: Parameters to configure the sync
        :return: sync report as tuple, with counts of successful and unsuccessful issue syncs
        :rtype: tuple(report, counters)
        """
        if self.endpoint.edition() == "community":
            return self.__sync_community(another_project, sync_settings)

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
                str(self),
                str(another_project),
                ", ".join(diff),
            )
        report = []
        counters = {}
        intersect = list(set(src_branches_list) & set(tgt_branches_list))
        for branch_name in intersect:
            (tmp_report, tmp_counts) = src_branches[branch_name].sync(tgt_branches[branch_name], sync_settings=sync_settings)
            report += tmp_report
            counters = util.dict_add(counters, tmp_counts)
        return (report, counters)

    def sync_branches(self, sync_settings: types.ConfigSettings) -> tuple[list[str], dict[str, int]]:
        """Syncs project issues across all its branches

        :param dict sync_settings: Parameters to configure the sync
        :return: sync report as tuple, with counts of successful and unsuccessful issue syncs
        :rtype: tuple(report, counters)
        """
        my_branches = self.branches()
        report = []
        counters = {}
        for b_src in my_branches.values():
            for b_tgt in my_branches.values():
                if b_src.name == b_tgt.name:
                    continue
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

    def quality_gate(self) -> tuple[str, bool]:
        """Returns the project quality gate

        :return: name of quality gate and whether it's the default
        :rtype: tuple(name, is_default)
        """
        data = json.loads(self.get(api="qualitygates/get_by_project", params={"project": self.key}).text)
        return (data["qualityGate"]["name"], data["qualityGate"]["default"])

    def webhooks(self) -> dict[webhooks.WebHook]:
        """
        :return: Project webhooks indexed by their key
        :rtype: dict{key: WebHook}
        """
        log.debug("Getting %s webhooks", str(self))
        return webhooks.get_list(endpoint=self.endpoint, project_key=self.key)

    def links(self) -> list[dict[str, str]]:
        """
        :return: list of project links
        :rtype: list[{type, name, url}]
        """
        data = json.loads(self.get(api="project_links/search", params={"projectKey": self.key}).text)
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
        return util.remove_nones(branch_data)

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
                t_hist.append({k: v for k, v in t._json.items() if k not in _UNNEEDED_TASK_DATA})
            json_data["backgroundTasks"] = {
                "lastTaskScannerContext": ctxt,
                # "lastTaskWarnings": last_task.warnings(),
                "taskHistory": t_hist,
            }
        return json_data

    def export(self, export_settings: types.ConfigSettings, settings_list: dict[str, str] = None) -> types.ObjectJsonRepr:
        """Exports the entire project configuration as JSON

        :return: All project configuration settings
        :rtype: dict
        """
        log.info("Exporting %s", str(self))
        json_data = self._json.copy()
        json_data.update({"key": self.key, "name": self.name})
        try:
            json_data["binding"] = self.__export_get_binding()
            nc = self.new_code()
            if nc != "":
                json_data[settings.NEW_CODE_PERIOD] = nc
            json_data["qualityProfiles"] = self.__export_get_qp()
            json_data["links"] = self.links()
            json_data["permissions"] = self.permissions().to_json(csv=export_settings.get("INLINE_LISTS", True))
            json_data["branches"] = self.__get_branch_export(export_settings)
            json_data["tags"] = self.tags()
            json_data["visibility"] = self.visibility()
            (json_data["qualityGate"], qg_is_default) = self.quality_gate()
            if qg_is_default:
                json_data.pop("qualityGate")

            hooks = webhooks.export(self.endpoint, self.key)
            if hooks is not None:
                json_data["webhooks"] = hooks
            json_data = util.filter_export(json_data, _IMPORTABLE_PROPERTIES, export_settings.get("FULL_EXPORT", False))

            if export_settings.get("MODE", "") == "MIGRATION":
                json_data.update(self.migration_export(export_settings))

            settings_dict = settings.get_bulk(endpoint=self.endpoint, component=self, settings_list=settings_list, include_not_set=False)
            # json_data.update({s.to_json() for s in settings_dict.values() if include_inherited or not s.inherited})
            for s in settings_dict.values():
                if not export_settings.get("INCLUDE_INHERITED", False) and s.inherited:
                    continue
                json_data.update(s.to_json())
        except (ConnectionError, RequestException) as e:
            errmsg = util.error_msg(e)
            log.error("Exception: %s while exporting %s, export of this project interrupted", errmsg, str(self))
            json_data["error"] = f"{errmsg} while extracting project"
        except Exception as e:
            log.critical("Exception: %s while exporting %s, export of this project interrupted", errmsg, str(self))
            json_data["error"] = f"{errmsg} while extracting project"
        log.debug("Exporting %s done", str(self))
        return util.remove_nones(json_data)

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
        try:
            self.permissions().set(desired_permissions)
            return True
        except (ConnectionError, RequestException) as e:
            log.error("%s while setting permissions of %s", util.error_msg(e), str(self))
            if not isinstance(e, HTTPError) or e.response.status_code != HTTPStatus.BAD_REQUEST:
                raise e
            return False

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

    def set_tags(self, tags: list[str]) -> bool:
        """Sets project tags

        :param list tags: list of tags
        :return: Whether the operation was successful
        """
        if tags is None:
            return False
        my_tags = util.list_to_csv(tags) if isinstance(tags, list) else util.csv_normalize(tags)
        r = self.post("project_tags/set", params={"project": self.key, "tags": my_tags})
        self._tags = util.csv_to_list(my_tags)
        return r.ok

    def set_quality_gate(self, quality_gate: str) -> bool:
        """Sets project quality gate

        :param quality_gate: quality gate name
        :type quality_gate: str
        :return: Whether the operation was successful
        :rtype: bool
        """
        if quality_gate is None:
            return False
        try:
            _ = qualitygates.QualityGate.get_object(self.endpoint, quality_gate)
        except exceptions.ObjectNotFound:
            log.warning("Quality gate '%s' not found, can't set it for %s", quality_gate, str(self))
            return False
        log.debug("Setting quality gate '%s' for %s", quality_gate, str(self))
        r = self.post("qualitygates/select", params={"projectKey": self.key, "gateName": quality_gate})
        return r.ok

    def set_quality_profile(self, language: str, quality_profile: str) -> bool:
        """Sets project quality profile for a given language

        :param str language: Language mnemonic, following SonarQube convention
        :param str quality_profile: Name of the quality profile in the language
        :return: Whether the operation was successful
        :rtype: bool
        """
        if not qualityprofiles.exists(endpoint=self.endpoint, language=language, name=quality_profile):
            log.warning("Quality profile '%s' in language '%s' does not exist, can't set it for %s", quality_profile, language, str(self))
            return False
        log.debug("Setting quality profile '%s' of language '%s' for %s", quality_profile, language, str(self))
        r = self.post("qualityprofiles/add_project", params={"project": self.key, "qualityProfile": quality_profile, "language": language})
        return r.ok

    def rename_main_branch(self, main_branch_name: str) -> bool:
        """Renames the project main branch

        :param main_branch_name: New main branch name
        :type main_branch_name: str
        :return: Whether the operation was successful
        :rtype: bool
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
        current_wh = self.webhooks()
        current_wh_names = [wh.name for wh in current_wh.values()]
        wh_map = {wh.name: k for k, wh in current_wh.items()}
        # FIXME: Handle several webhooks with same name
        for wh_name, wh in webhook_data.items():
            if wh_name in current_wh_names:
                current_wh[wh_map[wh_name]].update(name=wh_name, **wh)
            else:
                webhooks.update(name=wh_name, endpoint=self.endpoint, project=self.key, **wh)

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
        if self.endpoint.edition() == "community":
            raise exceptions.UnsupportedOperation(f"{str(self)}: Can't set project binding on Community Edition")
        alm_key = data["key"]
        if not devops.exists(alm_key, self.endpoint):
            log.warning("DevOps platform '%s' does not exists, can't set it for %s", alm_key, str(self))
            return False
        alm_type = devops.devops_type(platform_key=alm_key, endpoint=self.endpoint)
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
        if self.endpoint.edition() == "community":
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

    def update(self, data: types.ObjectJsonRepr) -> None:
        """Updates a project with a whole configuration set

        :param dict data: JSON of configuration settings
        :return: Nothing
        """
        if "permissions" in data:
            decoded_perms = {}
            for ptype in perms.PERMISSION_TYPES:
                if ptype not in data["permissions"]:
                    continue
                decoded_perms[ptype] = {u: perms.decode(v) for u, v in data["permissions"][ptype].items()}
            self.set_permissions(decoded_perms)
        self.set_links(data)
        self.set_tags(data.get("tags", None))
        self.set_quality_gate(data.get("qualityGate", None))
        for lang, qp_name in data.get("qualityProfiles", {}).items():
            self.set_quality_profile(language=lang, quality_profile=qp_name)
        for bname, bdata in data.get("branches", {}).items():
            if bdata.get("isMain", False):
                self.rename_main_branch(bname)
                break
        if "binding" in data:
            try:
                self.set_devops_binding(data["binding"])
            except exceptions.UnsupportedOperation as e:
                log.warning(e.message)
        else:
            log.debug("%s has no devops binding, skipped", str(self))
        settings_to_apply = {
            k: v for k, v in data.items() if k not in ("permissions", "tags", "links", "qualityGate", "qualityProfiles", "binding", "name")
        }
        # TODO: Set branch settings
        self.set_settings(settings_to_apply)

    def search_params(self) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        return {"project": self.key}


def count(endpoint: pf.Platform, params: types.ApiParams = None) -> int:
    """Counts projects

    :param params: list of parameters to filter projects to search
    :type params: dict
    :return: Count of projects
    :rtype: int
    """
    new_params = {} if params is None else params.copy()
    new_params.update({"ps": 1, "p": 1})
    util.nbr_total_elements(json.loads(endpoint.get(Project.SEARCH_API, params=params).text))


def search(endpoint: pf.Platform, params: types.ApiParams = None) -> dict[str, Project]:
    """Searches projects in SonarQube

    :param endpoint: Reference to the SonarQube platform
    :type endpoint: pf.Platform
    :param params: list of parameters to narrow down the search
    :type params: dict
    :return: list of projects
    :rtype: dict{key: Project}
    """
    new_params = {} if params is None else params.copy()
    new_params["qualifiers"] = "TRK"
    return sqobject.search_objects(endpoint=endpoint, object_class=Project, params=new_params)


def get_list(endpoint: pf.Platform, key_list: types.KeyList = None, use_cache: bool = True) -> dict[str, Project]:
    """
    :param Platform endpoint: Reference to the SonarQube platform
    :param KeyList key_list: List of portfolios keys to get, if None or empty all portfolios are returned
    :param bool use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :return: the list of all projects
    :rtype: dict{key: Project}
    """
    with _CLASS_LOCK:
        if key_list is None or len(key_list) == 0 or not use_cache:
            log.info("Listing projects")
            return search(endpoint=endpoint)
    return {key: Project.get_object(endpoint, key) for key in util.csv_to_list(key_list)}


def __audit_thread(queue: Queue[Project], results: list[Problem], audit_settings: types.ConfigSettings, bindings: dict[str, str]) -> None:
    """Audit callback function for multitheaded audit"""
    audit_bindings = audit_settings.get("audit.projects.bindings", True)
    while not queue.empty():
        log.debug("Picking from the queue")
        project = queue.get()
        results += project.audit(audit_settings)
        try:
            if project.endpoint.edition() == "community" or not audit_bindings or project.is_part_of_monorepo():
                queue.task_done()
                log.debug("%s audit done", str(project))
                continue
            bindkey = project.binding_key()
            if bindkey and bindkey in bindings:
                results.append(Problem(get_rule(RuleId.PROJ_DUPLICATE_BINDING), project, str(project), str(bindings[bindkey])))
            else:
                bindings[bindkey] = project
        except (ConnectionError, RequestException) as e:
            log.error("%s while auditing %s", util.error_msg(e), str(project))
        queue.task_done()
        log.debug("%s audit complete", str(project))
    log.debug("Queue empty, exiting thread")


def audit(endpoint: pf.Platform, audit_settings: types.ConfigSettings, key_list: types.KeyList = None) -> list[Problem]:
    """Audits all or a list of projects

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings audit_settings: Configuration of audit
    :param KeyList key_list: List of project keys to audit, defaults to None (all projects)
    :return: list of problems found
    :rtype: list[Problem]
    """
    log.info("--- Auditing projects ---")
    plist = get_list(endpoint, key_list)
    problems = []
    q = Queue(maxsize=0)
    for p in plist.values():
        q.put(p)
    bindings = {}
    for i in range(audit_settings.get("threads", 1)):
        log.debug("Starting project audit thread %d", i)
        worker = Thread(target=__audit_thread, args=(q, problems, audit_settings, bindings))
        worker.setDaemon(True)
        worker.setName(f"ProjectAudit{i}")
        worker.start()
    q.join()
    if not audit_settings.get("audit.projects.duplicates", True):
        log.info("Project duplicates auditing was disabled by configuration")
        return problems
    for key, p in plist.items():
        log.debug("Auditing for potential duplicate projects")
        for key2 in plist:
            if key2 != key and re.match(key2, key):
                problems.append(Problem(get_rule(RuleId.PROJ_DUPLICATE), p, str(p), key2))
    return problems


def __export_thread(queue: Queue[Project], results: dict[str, str], export_settings: types.ConfigSettings, write_q: Optional[Queue] = None) -> None:
    """Project export callback function for multitheaded export"""
    while not queue.empty():
        project = queue.get()
        exp_json = project.export(export_settings=export_settings)
        if write_q:
            write_q.put(exp_json)
        else:
            results[project.key] = exp_json
            results[project.key].pop("key", None)
        with _CLASS_LOCK:
            export_settings["EXPORTED"] += 1
        nb, tot = export_settings["EXPORTED"], export_settings["NBR_PROJECTS"]
        lvl = log.INFO if nb % 10 == 0 or tot - nb < 10 else log.DEBUG
        log.log(lvl, "%d/%d projects exported (%d%%)", nb, tot, (nb * 100) // tot)
        queue.task_done()
    log.info("Project export queue empty, export complete")


def export(
    endpoint: pf.Platform, export_settings: types.ConfigSettings, key_list: Optional[types.KeyList] = None, write_q: Optional[Queue] = None
) -> types.ObjectJsonRepr:
    """Exports all or a list of projects configuration as dict

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings export_settings: Export parameters
    :param KeyList key_list: List of project keys to export, defaults to None (all projects)
    :return: list of projects settings
    :rtype: ObjectJsonRepr
    """
    for qp in qualityprofiles.get_list(endpoint).values():
        qp.projects()

    q = Queue(maxsize=0)
    proj_list = get_list(endpoint=endpoint, key_list=key_list)
    export_settings["NBR_PROJECTS"] = len(proj_list)
    export_settings["EXPORTED"] = 0
    log.info("Exporting %d projects", export_settings["NBR_PROJECTS"])
    for p in proj_list.values():
        q.put(p)
    project_settings = {}
    for i in range(export_settings.get("THREADS", 8)):
        log.debug("Starting project export thread %d", i)
        worker = Thread(target=__export_thread, args=(q, project_settings, export_settings, write_q))
        worker.daemon = True
        worker.name = f"ProjectExport{i}"
        worker.start()
    q.join()
    if write_q:
        write_q.put(None)
    return dict(sorted(project_settings.items()))


def exists(key: str, endpoint: pf.Platform) -> bool:
    """
    :param str key: project key to check
    :param Platform endpoint: reference to the SonarQube platform
    :return: whether the project exists
    :rtype: bool
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
    :return: Nothing
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


def __export_zip_thread(queue: Queue[Project], results: list[dict[str, str]], statuses: dict[str, int], export_timeout: int) -> None:
    while not queue.empty():
        project = queue.get()
        try:
            dump = project.export_zip(timeout=export_timeout)
        except exceptions.UnsupportedOperation:
            queue.task_done()
            util.exit_fatal("Zip export unsupported on your SonarQube version", errcodes.UNSUPPORTED_OPERATION)
        status = dump["status"]
        statuses[status] = 1 if status not in statuses else statuses[status] + 1
        data = {"key": project.key, "status": status}
        if status == "SUCCESS":
            data["file"] = os.path.basename(dump["file"])
            data["path"] = dump["file"]
        results.append(data)
        log.info("%s", ", ".join([f"{k}:{v}" for k, v in statuses.items()]))
        queue.task_done()


def export_zip(endpoint: pf.Platform, key_list: types.KeyList = None, threads: int = 8, export_timeout: int = 30) -> dict[str, str]:
    """Export as zip all or a list of projects

    :param Platform endpoint: reference to the SonarQube platform
    :param KeyList key_list: List of project keys to export, defaults to None (all projects)
    :param threads: Number of parallel threads for export, defaults to 8
    :type threads: int, optional
    :param export_timeout: Tiemout to export the project, defaults to 30
    :type export_timeout: int, optional
    :return: list of exported projects and platform version
    :rtype: dict
    """
    statuses, exports = {}, []
    projects_list = get_list(endpoint, key_list)
    nbr_projects = len(projects_list)
    log.info("Exporting %d projects to export", nbr_projects)
    q = Queue(maxsize=0)
    for p in projects_list.values():
        q.put(p)
    for i in range(threads):
        log.debug("Starting project export thread %d", i)
        worker = Thread(target=__export_zip_thread, args=(q, exports, statuses, export_timeout))
        worker.setDaemon(True)
        worker.setName(f"ZipExport{i}")
        worker.start()
    q.join()

    return {
        "sonarqube_environment": {
            "version": ".".join([str(n) for n in endpoint.version()[:2]]),
            "plugins": endpoint.plugins(),
        },
        "project_exports": exports,
    }


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
    new_json = []
    for proj in util.dict_to_list(original_json, "key"):
        new_json.append(convert_proj_for_yaml(proj))
    return new_json
