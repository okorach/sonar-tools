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

from __future__ import annotations
from typing import Optional, TYPE_CHECKING

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
from sonar.api.manager import ApiOperation as op

if TYPE_CHECKING:
    from sonar.util.types import ApiPayload, ApiParams, ConfigSettings

_UNSUPPORTED_IN_CE = "Pull requests not available in Community Edition"


class PullRequest(components.Component):
    """
    Abstraction of the Sonar pull request concept
    """

    CACHE = cache.Cache()
    API = {op.DELETE: "project_pull_requests/delete", op.LIST: "project_pull_requests/list"}

    def __init__(self, project: object, key: str, data: Optional[ApiPayload] = None) -> None:
        """Constructor"""
        super().__init__(endpoint=project.endpoint, key=key)
        self.concerned_object = project
        self.json = data
        self._last_analysis: Optional[datetime] = None
        PullRequest.CACHE.put(self)
        log.debug("Created object %s", str(self))

    def __str__(self) -> str:
        """Returns string representation of the PR"""
        return f"pull request key '{self.key}' of {str(self.project())}"

    def __hash__(self) -> int:
        """Returns a PR unique ID"""
        return hash((self.project().key, self.key, self.base_url()))

    def url(self) -> str:
        """Returns the PR permalink (until PR is purged)"""
        return f"{self.concerned_object.url()}&pullRequest={requests.utils.quote(self.key)}"

    def get_tags(self, **kwargs) -> list[str]:
        """
        :return: The tags of the project corresponding to the PR
        """
        return self.concerned_object.get_tags(**kwargs)

    def project(self) -> object:
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

    def api_params(self, operation: Optional[op] = None) -> ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {op.READ: {"project": self.concerned_object.key, "pullRequest": self.key}}
        return ops[operation] if operation and operation in ops else ops[op.READ]

    def get_findings(self, filters: Optional[ApiParams] = None) -> dict[str, object]:
        """Returns a PR list of findings

        :return: dict of Findings, with finding key as key
        :rtype: dict{key: Finding}
        """
        if not filters:
            return self.concerned_object.get_findings(pr=self.key)
        return self.get_issues(filters) | self.get_hotspots(filters)


def get_object(pull_request_key: str, project: object, data: Optional[ApiPayload] = None) -> Optional[PullRequest]:
    """Returns a PR object from a PR key and a project"""
    if project.endpoint.edition() == c.CE:
        log.debug("Pull requests not available in Community Edition")
        return None
    o = PullRequest.CACHE.get(project.key, pull_request_key, project.base_url())
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
    if project.endpoint.edition() == c.CE:
        log.debug(_UNSUPPORTED_IN_CE)
        raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)

    data = json.loads(project.get(PullRequest.API[op.LIST], params={"project": project.key}).text)
    pr_list = {}
    for pr in data["pullRequests"]:
        pr_list[pr["key"]] = get_object(pr["key"], project, pr)
    return pr_list
