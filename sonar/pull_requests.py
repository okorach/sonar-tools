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
"""

    Abstraction of the SonarQube "pull request" concept

"""

import json
from datetime import datetime
from typing import Optional

import requests.utils

import sonar.logging as log
from sonar.util import types, cache, constants as c
from sonar import components, sqobject, exceptions
import sonar.utilities as util
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem


_UNSUPPORTED_IN_CE = "Pull requests not available in Community Edition"


class PullRequest(components.Component):
    """
    Abstraction of the Sonar pull request concept
    """

    CACHE = cache.Cache()
    API = {c.DELETE: "project_pull_requests/delete", c.LIST: "project_pull_requests/list"}

    def __init__(self, project: object, key: str, data: types.ApiPayload = None) -> None:
        """Constructor"""
        super().__init__(endpoint=project.endpoint, key=key)
        self.concerned_object = project
        self.json = data
        self._last_analysis = None
        PullRequest.CACHE.put(self)
        log.debug("Created object %s", str(self))

    def __str__(self) -> str:
        """Returns string representation of the PR"""
        return f"pull request key '{self.key}' of {str(self.project())}"

    def __hash__(self) -> int:
        """Returns a PR unique ID"""
        return hash((self.project().key, self.key, self.endpoint.url))

    def url(self) -> str:
        """Returns the PR permalink (until PR is purged)"""
        return f"{self.endpoint.url}/dashboard?id={self.concerned_object.key}&pullRequest={requests.utils.quote(self.key)}"

    def project(self) -> object:
        """Returns the project"""
        return self.concerned_object

    def last_analysis(self) -> datetime:
        if self._last_analysis is None and "analysisDate" in self.json:
            self._last_analysis = util.string_to_date(self.json["analysisDate"])
        return self._last_analysis

    def audit(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        age = util.age(self.last_analysis())
        if age is None:  # Main branch not analyzed yet
            return []
        max_age = audit_settings.get("audit.projects.pullRequests.maxLastAnalysisAge", 30)
        problems = []
        if age > max_age:
            problems.append(Problem(get_rule(RuleId.PULL_REQUEST_LAST_ANALYSIS), self, str(self), age))
        else:
            log.debug("%s age is %d days", str(self), age)
        return problems

    def api_params(self, op: str = c.GET) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {c.GET: {"project": self.concerned_object.key, "pullRequest": self.key}}
        return ops[op] if op in ops else ops[c.GET]


def get_object(pull_request_key: str, project: object, data: types.ApiPayload = None) -> Optional[PullRequest]:
    """Returns a PR object from a PR key and a project"""
    if project.endpoint.edition() == "community":
        log.debug("Pull requests not available in Community Edition")
        return None
    o = PullRequest.CACHE.get(project.key, pull_request_key, project.endpoint.url)
    if not o:
        o = PullRequest(project, pull_request_key, data=data)
    return o


def get_list(project: object) -> dict[str, PullRequest]:
    """Retrieves the list of pull requests of a project

    :param Project project: Project to get PRs from
    :raises UnsupportedOperation: PRs not supported in Community Edition
    :return: List of project PRs
    :rtype: dict{PR_ID: PullRequest}
    """
    if project.endpoint.edition() == "community":
        log.debug(_UNSUPPORTED_IN_CE)
        raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)

    data = json.loads(project.get(PullRequest.API[c.LIST], params={"project": project.key}).text)
    pr_list = {}
    for pr in data["pullRequests"]:
        pr_list[pr["key"]] = get_object(pr["key"], project, pr)
    return pr_list
