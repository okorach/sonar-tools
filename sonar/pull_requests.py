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
from datetime import datetime

import requests.utils

import sonar.logging as log
from sonar.util import cache
from sonar import components, exceptions
import sonar.util.misc as util
import sonar.utilities as sutil
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem
import sonar.util.constants as c
from sonar.api.manager import ApiOperation as Oper
from sonar.api.manager import ApiManager as Api
from sonar import projects as proj

if TYPE_CHECKING:
    from sonar.issues import Issue
    from sonar.hotspots import Hotspot
    from sonar.util.types import ApiPayload, ApiParams, ConfigSettings
    from sonar.platform import Platform

_UNSUPPORTED_IN_CE = "Pull requests not available in Community Edition"


class PullRequest(components.Component):
    """Abstraction of the Sonar pull request concept"""

    CACHE = cache.Cache()

    def __init__(self, project: proj.Project, key: str, data: Optional[ApiPayload] = None) -> None:
        """Constructor"""
        super().__init__(endpoint=project.endpoint, key=key)
        self.concerned_object: proj.Project = project
        self.status: Optional[str] = None
        self.base: Optional[str] = None
        self.target: Optional[str] = None
        self.branch: Optional[str] = None
        if data is not None:
            self.reload(data)
        PullRequest.CACHE.put(self)
        log.debug("Created object %s", str(self))

    def __str__(self) -> str:
        """Returns string representation of the PR"""
        return f"pull request key '{self.key}' of {str(self.project())}"

    def __hash__(self) -> int:
        """Returns a PR unique ID"""
        return hash((self.project().key, self.key, self.base_url()))

    @classmethod
    def get_object(cls, endpoint: Platform, project: Union[proj.Project, str], pull_request_key: str) -> PullRequest:
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
        if isinstance(project, str):
            project = proj.Project.get_object(endpoint, project)
        if o := cls.CACHE.get(project.key, pull_request_key, project.base_url()):
            return o
        return cls(project, pull_request_key)

    @classmethod
    def load(cls, endpoint: Platform, project: Union[proj.Project, str], data: ApiPayload) -> PullRequest:
        """Loads a PR object from API data"""
        if isinstance(project, str):
            project = proj.Project.get_object(endpoint, project)
        if not (o := cls.CACHE.get(project.key, data["key"], project.base_url())):
            o = cls(project, data["key"])
        o.reload(data)
        return o

    @classmethod
    def get_list(cls, project: proj.Project) -> dict[str, PullRequest]:
        """Retrieves the list of pull requests of a project

        :param proj.Project project: proj.Project to get PRs from
        :raises UnsupportedOperation: PRs not supported in Community Edition
        :return: List of project PRs
        :rtype: dict{PR_ID: PullRequest}
        """
        if project.endpoint.edition() == c.CE:
            log.debug(_UNSUPPORTED_IN_CE)
            raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)

        api, _, params, ret = project.endpoint.api.get_details(cls, Oper.SEARCH, project=project.key)
        data = json.loads(project.get(api, params=params).text)
        pr_list = {}
        for pr in data[ret]:
            pr_list[pr["key"]] = cls.load(project.endpoint, project, pr)
        return pr_list

    def reload(self, data: ApiPayload) -> PullRequest:
        """Reloads a PR object from API data"""
        super().reload(data)
        self._last_analysis = sutil.string_to_date(data["analysisDate"])
        self.name = self._description = data["title"]
        self.status = data["status"]["qualityGateStatus"]
        self.base = data["base"]
        self.target = data["target"]
        self.branch = data["branch"]
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

    def last_analysis(self) -> datetime:
        if self._last_analysis is None and "analysisDate" in self.json:
            self._last_analysis = sutil.string_to_date(self.json["analysisDate"])
        return self._last_analysis

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
