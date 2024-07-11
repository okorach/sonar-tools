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
import requests.utils

import sonar.logging as log
from sonar import components, sqobject, exceptions
import sonar.utilities as util
from sonar.audit import rules, problem

_OBJECTS = {}

_UNSUPPORTED_IN_CE = "Pull requests not available in Community Edition"


class PullRequest(components.Component):
    def __init__(self, project, key, endpoint=None, data=None):
        if endpoint is not None:
            super().__init__(key, endpoint)
        else:
            super().__init__(key, project.endpoint)
        self.project = project
        self.json = data
        self._last_analysis = None
        _OBJECTS[self.uuid()] = self
        log.debug("Created object %s", str(self))

    def __str__(self):
        return f"pull request key '{self.key}' of {str(self.project)}"

    def url(self):
        return f"{self.endpoint.url}/dashboard?id={self.project.key}&pullRequest={requests.utils.quote(self.key)}"

    def uuid(self):
        return uuid(self.project.key, self.key, self.endpoint.url)

    def last_analysis(self):
        if self._last_analysis is None and "analysisDate" in self.json:
            self._last_analysis = util.string_to_date(self.json["analysisDate"])
        return self._last_analysis

    def delete(self):
        return sqobject.delete_object(self, "project_pull_requests/delete", self.search_params(), _OBJECTS)

    def audit(self, audit_settings):
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


def uuid(project_key: str, pull_request_key: str, url: str):
    return f"{project_key}{components.KEY_SEPARATOR}{pull_request_key}@{url}"


def get_object(pull_request_key, project, data=None):
    if project.endpoint.edition() == "community":
        log.debug("Pull requests not available in Community Edition")
        return None
    uid = uuid(project.key, pull_request_key, project.endpoint.url)
    if uid not in _OBJECTS:
        _ = PullRequest(project, pull_request_key, endpoint=project.endpoint, data=data)
    return _OBJECTS[uid]


def get_list(project):
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
