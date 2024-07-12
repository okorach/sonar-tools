#
# sonar-tools
# Copyright (C) 2022-2024 Olivier Korach
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
from typing import Union

import requests.utils

import sonar.logging as log

from sonar import components, sqobject, exceptions
import sonar.utilities as util
from sonar.audit import rules, problem

_OBJECTS = {}

_UNSUPPORTED_IN_CE = "Pull requests not available in Community Edition"


class PullRequest(components.Component):
    """
    Abstraction of the Sonar pull request concept
    """

    def __init__(self, project: object, key: str, data: dict[str, str] = None) -> None:
        """Constructor"""
        super().__init__(endpoint=project.endpoint, key=key)
        self.project = project
        self.json = data
        self._last_analysis = None
        _OBJECTS[self.uuid()] = self
        log.debug("Created object %s", str(self))

    def __str__(self) -> str:
        """Returns string representation of the PR"""
        return f"pull request key '{self.key}' of {str(self.project)}"

    def url(self) -> str:
        """Returns the PR permalink (until PR is purged)"""
        return f"{self.endpoint.url}/dashboard?id={self.project.key}&pullRequest={requests.utils.quote(self.key)}"

    def uuid(self) -> str:
        """Returns a PR unique ID"""
        return uuid(self.project.key, self.key, self.endpoint.url)

    def last_analysis(self) -> datetime:
        if self._last_analysis is None and "analysisDate" in self.json:
            self._last_analysis = util.string_to_date(self.json["analysisDate"])
        return self._last_analysis

    def delete(self) -> bool:
        """Deletes a PR and returns whether the operation succeeded"""
        return sqobject.delete_object(self, "project_pull_requests/delete", self.search_params(), _OBJECTS)

    def audit(self, audit_settings: dict[str, str]) -> list[problem.Problem]:
        age = util.age(self.last_analysis())
        if age is None:  # Main branch not analyzed yet
            return []
        max_age = audit_settings.get("audit.projects.pullRequests.maxLastAnalysisAge", 30)
        problems = []
        if age > max_age:
            rule = rules.get_rule(rules.RuleId.PULL_REQUEST_LAST_ANALYSIS)
            problems.append(problem.Problem(broken_rule=rule, msg=rule.msg.format(str(self), age), concerned_object=self))
        else:
            log.debug("%s age is %d days", str(self), age)
        return problems

    def search_params(self) -> dict[str, str]:
        """Return params used to search/create/delete for that object"""
        return {"project": self.project.key, "pullRequest": self.key}


def uuid(project_key: str, pull_request_key: str, url: str) -> str:
    """UUID for pull request objects"""
    return f"{project_key}{components.KEY_SEPARATOR}{pull_request_key}@{url}"


def get_object(pull_request_key: str, project: object, data: dict[str, str] = None) -> Union[PullRequest, None]:
    """Returns a PR object from a PR key and a project"""
    if project.endpoint.edition() == "community":
        log.debug("Pull requests not available in Community Edition")
        return None
    uid = uuid(project.key, pull_request_key, project.endpoint.url)
    if uid not in _OBJECTS:
        _ = PullRequest(project, pull_request_key, data=data)
    return _OBJECTS[uid]


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

    data = json.loads(project.get("project_pull_requests/list", params={"project": project.key}).text)
    pr_list = {}
    for pr in data["pullRequests"]:
        pr_list[pr["key"]] = get_object(pr["key"], project, pr)
    return pr_list
