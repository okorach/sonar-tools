#
# sonar-tools
# Copyright (C) 2022-2026 Olivier Korach
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

Abstraction of the SonarQube "pull request" concept

"""

from __future__ import annotations
from typing import Optional, Union, Any, TYPE_CHECKING

import json
import requests.utils

import sonar.logging as log
from sonar.util import cache
from sonar import exceptions
from sonar.components import Component
import sonar.util.misc as util
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem
import sonar.util.constants as c
from sonar.api.manager import ApiOperation as Oper
from sonar import projects as proj

if TYPE_CHECKING:
    from sonar.issues import Issue
    from sonar.hotspots import Hotspot
    from sonar.util.types import ApiPayload, ApiParams, ConfigSettings
    from sonar.platform import Platform

_UNSUPPORTED_IN_CE = "Pull requests not available in Community Edition"


class PullRequest(Component):
    """Abstraction of the Sonar pull request concept"""

    CACHE = cache.Cache()
    __PROJECT_KEY = "projectKey"

    def __init__(self, endpoint: Platform, data: ApiPayload) -> None:
        """Constructor"""
        self.key = data["key"]
        self.concerned_object: proj.Project = proj.Project.get_project_object(endpoint, data[self.__PROJECT_KEY])
        super().__init__(endpoint, data)
        self.reload(data)
        self.__class__.CACHE.put(self)
        log.debug("Constructed object %s", str(self))

    def __str__(self) -> str:
        """Returns string representation of the PR"""
        return f"pull request key '{self.key}' of {str(self.project())}"

    @staticmethod
    def hash_payload(data: ApiPayload) -> tuple[Any, ...]:
        """Returns the hash items for a given object search payload"""
        return (data[PullRequest.__PROJECT_KEY], data["key"])

    def hash_object(self) -> tuple[Any, ...]:
        """Computes a uuid for the branch that can serve as index"""
        return (self.concerned_object.key, self.key)

    @classmethod
    def get_object(cls, endpoint: Platform, project: Union[proj.Project, str], pull_request_key: str, use_cache: bool = True) -> PullRequest:
        """Returns a PR object from a PR key and a project

        :param endpoint: Reference to the SonarQube platform
        :param project: proj.Project object or project key
        :param pull_request_key: Pull request key
        :raises UnsupportedOperation: PRs not supported in Community Edition
        :raises ObjectNotFound: PR not found
        :return: The PullRequest object
        """
        if endpoint.edition() == c.CE:
            raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)
        project = proj.Project.get_project_object(endpoint, project)
        o: Optional[PullRequest] = cls.CACHE.get(endpoint.local_url, project.key, pull_request_key)
        if use_cache and o:
            return o
        api, _, params, ret = endpoint.api.get_details(PullRequest, Oper.SEARCH, project=project.key)
        data = json.loads(project.get(api, params=params).text)[ret]
        for pr in data:
            pr[cls.__PROJECT_KEY] = project.key
            o = cls.load(endpoint, pr)
            o.concerned_object = project
            if o.key == pull_request_key:
                object_to_return = o
        return object_to_return

    @classmethod
    def search(cls, endpoint: Platform, project: Union[proj.Project, str], **search_params: Any) -> dict[str, PullRequest]:
        """Retrieves the list of pull requests of a project

        :param Platform endpoint: Reference to the SonarQube platform
        :param str | Project project: project to get PRs from
        :raises UnsupportedOperation: PRs not supported in Community Edition
        :return: Dict of project PRs indexed by PR key
        """
        if project.endpoint.edition() == c.CE:
            log.debug(_UNSUPPORTED_IN_CE)
            raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)
        project = proj.Project.get_project_object(endpoint, project)
        api, _, params, ret = project.endpoint.api.get_details(cls, Oper.SEARCH, project=project.key)
        dataset = json.loads(project.get(api, params=params).text)[ret]
        for pr in dataset:
            pr[cls.__PROJECT_KEY] = project.key
        res = {}
        for pr in dataset:
            res[pr["key"]] = cls.load(endpoint, pr)
        return res

    def reload(self, data: ApiPayload) -> PullRequest:
        """Reloads a PR object from API data"""
        super().reload(data)
        self.concerned_object = self.concerned_object or proj.Project.get_project_object(self.endpoint, data[self.__PROJECT_KEY])
        self.name = self._description = data["title"]
        return self

    def url(self) -> str:
        """Returns the PR permalink (until PR is purged)"""
        return f"{self.concerned_object.url()}&pullRequest={requests.utils.quote(self.key)}"

    def get_tags(self, **kwargs) -> list[str]:
        """
        :return: The tags of the project corresponding to the PR
        """
        return self.concerned_object.get_tags(**kwargs)

    def project(self) -> proj.Project:
        """Returns the project"""
        return self.concerned_object

    def audit(self, audit_settings: ConfigSettings) -> list[Problem]:
        """Audits the pull request according to the audit settings"""
        problems = [] if audit_settings.get(c.AUDIT_MODE_PARAM, "") == "housekeeper" else self._audit_component(audit_settings)
        if (age := util.age(self.last_analysis())) is None:
            log.warning("%s: Can't get last analysis date for audit, skipped")
            return problems
        if (max_age := audit_settings.get("audit.projects.pullRequests.maxLastAnalysisAge", 30)) == 0:
            log.info("%s: Audit of last analysis date is disabled", self)
            return problems
        if age > max_age:
            problems.append(Problem(get_rule(RuleId.PULL_REQUEST_LAST_ANALYSIS), self, str(self), age))
        else:
            log.debug("%s age is %d days", str(self), age)
        return problems

    def project_key(self) -> str:
        """Returns the project key"""
        return self.concerned_object.key

    def api_params(self, operation: Optional[Oper] = None) -> ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {
            Oper.GET: {"project": self.concerned_object.key, "pullRequest": self.key},
            Oper.DELETE: {"project": self.concerned_object.key, "pullRequest": self.key},
        }
        return ops[operation] if operation and operation in ops else ops[Oper.GET]

    def delete(self) -> bool:
        """Deletes a pull request"""
        return super().delete_object(project=self.concerned_object.key, pullRequest=self.key)

    def get_issues(self, **search_params: Any) -> dict[str, Issue]:
        """Returns a list of issues on a PR"""
        from sonar.issues import Issue

        return Issue.search(self.endpoint, **(search_params | {"project": self.concerned_object.key, "pullRequest": self.key}))

    def get_hotspots(self, **search_params: Any) -> dict[str, Hotspot]:
        """Returns a list of hotspots on a PR"""
        from sonar.hotspots import Hotspot

        return Hotspot.search(self.endpoint, **(search_params | {"project": self.concerned_object.key, "pullRequest": self.key}))

    def get_findings(self, **search_params: Any) -> dict[str, Union[Issue, Hotspot]]:
        """Returns a list of findings, issues and hotspots together on a PR"""
        return self.concerned_object.get_findings(**(search_params | {"pullRequest": self.key}))
