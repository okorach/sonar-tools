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

"""Abstraction of the SonarQube project branch concept"""

from __future__ import annotations
from http import HTTPStatus
from typing import Optional
import json
from urllib.parse import unquote
from requests import HTTPError, RequestException
import requests.utils

from sonar import platform
from sonar.util import types, cache, constants as c
import sonar.logging as log
import sonar.sqobject as sq
from sonar import components, settings, exceptions, tasks
from sonar import projects
import sonar.utilities as util

from sonar.audit.problem import Problem
from sonar.audit.rules import get_rule, RuleId


_UNSUPPORTED_IN_CE = "Branches not available in Community Edition"


class Branch(components.Component):
    """
    Abstraction of the SonarQube "project branch" concept
    """

    CACHE = cache.Cache()
    API = {
        c.LIST: "project_branches/list",
        c.DELETE: "project_branches/delete",
        c.RENAME: "project_branches/rename",
        "get_new_code": "new_code_periods/list",
    }

    def __init__(self, project: projects.Project, name: str) -> None:
        """Don't use this, use class methods to create Branch objects

        :raises UnsupportedOperation: When attempting to branches on Community Edition
        """
        if project.endpoint.edition() == "community":
            raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)
        name = unquote(name)
        super().__init__(endpoint=project.endpoint, key=name)
        self.name = name
        self.concerned_object = project
        self._is_main = None
        self._new_code = None
        self._last_analysis = None
        self._keep_when_inactive = None
        Branch.CACHE.put(self)
        log.debug("Created object %s", str(self))

    @classmethod
    def get_object(cls, concerned_object: projects.Project, branch_name: str) -> Branch:
        """Gets a SonarQube Branch object

        :param projects.Project concerned_object: projects.Project concerned by the branch
        :param str branch_name: The branch name
        :raises UnsupportedOperation: If trying to manipulate branches on a community edition
        :raises ObjectNotFound: If project key or branch name not found in SonarQube
        :return: The Branch object
        :rtype: Branch
        """
        branch_name = unquote(branch_name)
        o = Branch.CACHE.get(concerned_object.key, branch_name, concerned_object.endpoint.url)
        if o:
            return o
        try:
            data = json.loads(concerned_object.get(Branch.API[c.LIST], params={"project": concerned_object.key}).text)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"searching {str(concerned_object)} for branch '{branch_name}'", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
            raise exceptions.ObjectNotFound(concerned_object.key, f"{str(concerned_object)} not found")

        for br in data.get("branches", []):
            if br["name"] == branch_name:
                return cls.load(concerned_object, branch_name, br)
        raise exceptions.ObjectNotFound(branch_name, f"Branch '{branch_name}' of {str(concerned_object)} not found")

    @classmethod
    def load(cls, concerned_object: projects.Project, branch_name: str, data: types.ApiPayload) -> Branch:
        """Gets a Branch object from JSON data gotten from a list API call

        :param projects.Project concerned_object: the projects.Project the branch belonsg to
        :param str branch_name: Name of the branch
        :param dict data: Data received from API call
        :raises UnsupportedOperation: If trying to manipulate branches on a community edition
        :raises ObjectNotFound: If project key or branch name not found in SonarQube
        :return: The Branch object
        :rtype: Branch
        """
        branch_name = unquote(branch_name)
        o = Branch.CACHE.get(concerned_object.key, branch_name, concerned_object.endpoint.url)
        if not o:
            o = cls(concerned_object, branch_name)
        o._load(data)
        return o

    def __str__(self) -> str:
        return f"branch '{self.name}' of {str(self.project())}"

    def __hash__(self) -> int:
        """Computes a uuid for the branch that can serve as index"""
        return hash((self.concerned_object.key, self.name, self.endpoint.url))

    def project(self) -> projects.Project:
        """Returns the project key"""
        return self.concerned_object

    def refresh(self) -> Branch:
        """Reads a branch in SonarQube (refresh with latest data)

        :raises ObjectNotFound: Branch not found in SonarQube
        :return: itself
        :rtype: Branch
        """
        try:
            data = json.loads(self.get(Branch.API[c.LIST], params=self.api_params(c.LIST)).text)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"refreshing {str(self)}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
            Branch.CACHE.pop(self)
            raise exceptions.ObjectNotFound(self.key, f"{str(self)} not found in SonarQube")
        for br in data.get("branches", []):
            if br["name"] == self.name:
                self._load(br)
            else:
                # While we're there let's load other branches with up to date branch data
                Branch.load(self.concerned_object, br["name"], data)
        return self

    def _load(self, data: types.ApiPayload) -> None:
        if self.sq_json is None:
            self.sq_json = data
        else:
            self.sq_json.update(data)
        self._is_main = self.sq_json["isMain"]
        self._last_analysis = util.string_to_date(self.sq_json.get("analysisDate", None))
        self._keep_when_inactive = self.sq_json.get("excludedFromPurge", False)
        self._is_main = self.sq_json.get("isMain", False)

    def is_kept_when_inactive(self) -> bool:
        """
        :return: Whether the branch is kept when inactive
        :rtype: bool
        """
        if self._keep_when_inactive is None or self.sq_json is None:
            self.refresh()
        return self._keep_when_inactive

    def is_main(self) -> bool:
        """
        :return: Whether the branch is the project main branch
        :rtype: bool
        """
        if self._is_main is None or self.sq_json is None:
            self.refresh()
        return self._is_main

    def delete(self) -> bool:
        """Deletes a branch

        :raises ObjectNotFound: Branch not found for deletion
        :return: Whether the deletion was successful
        :rtype: bool
        """
        try:
            return super().delete()
        except (ConnectionError, RequestException) as e:
            if isinstance(e, HTTPError) and e.response.status_code == HTTPStatus.BAD_REQUEST:
                log.warning("Can't delete %s, it's the main branch", str(self))
            return False

    def new_code(self) -> str:
        """
        :return: The branch new code period definition
        :rtype: str
        """
        if self._new_code is None and self.endpoint.is_sonarcloud():
            self._new_code = settings.new_code_to_string({"inherited": True})
        elif self._new_code is None:
            try:
                data = json.loads(self.get(api=Branch.API["get_new_code"], params=self.api_params(c.LIST)).text)
            except (ConnectionError, RequestException) as e:
                util.handle_error(e, f"getting new code period of {str(self)}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
                Branch.CACHE.pop(self)
                raise exceptions.ObjectNotFound(self.concerned_object.key, f"{str(self.concerned_object)} not found")

            for b in data["newCodePeriods"]:
                new_code = settings.new_code_to_string(b)
                if b["branchKey"] == self.name:
                    self._new_code = new_code
                else:
                    # While we're there let's store the new code of other branches
                    Branch.get_object(self.concerned_object, b["branchKey"])._new_code = new_code
        return self._new_code

    def export(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """Exports a branch configuration (is main, keep when inactive, optionally name, project)

        :param full_export: Also export branches attributes that are not needed for import, defaults to True
        :type include_branches: bool, optional
        :return: The branch new code period definition
        :rtype: str
        """
        log.debug("Exporting %s", str(self))
        data = {settings.NEW_CODE_PERIOD: self.new_code()}
        if self.is_main():
            data["isMain"] = True
        if self.is_kept_when_inactive() and not self.is_main():
            data["keepWhenInactive"] = True
        if self.new_code():
            data[settings.NEW_CODE_PERIOD] = self.new_code()
        if export_settings.get("FULL_EXPORT", True):
            data.update({"name": self.name, "project": self.concerned_object.key})
        if export_settings.get("MODE", "") == "MIGRATION":
            data.update(self.migration_export(export_settings))
        data = util.remove_nones(data)
        return None if len(data) == 0 else data

    def url(self) -> str:
        """
        :return: The branch URL in SonarQube as permalink
        :rtype: str
        """
        return f"{self.endpoint.url}/dashboard?id={self.concerned_object.key}&branch={requests.utils.quote(self.name)}"

    def rename(self, new_name: str) -> bool:
        """Renames a branch

        :param str new_name: New branch name
        :raises UnsupportedOperation: If trying to rename anything than the main branch
        :raises ObjectNotFound: Concerned object (project) not found
        :return: Whether the branch was renamed
        :rtype: bool
        """
        if not self.is_main():
            raise exceptions.UnsupportedOperation(f"{str(self)} can't be renamed since it's not the main branch")

        if self.name == new_name:
            log.debug("Skipping rename %s with same new name", str(self))
            return False
        log.info("Renaming main branch of %s from '%s' to '%s'", str(self.concerned_object), self.name, new_name)
        try:
            self.post(Branch.API[c.RENAME], params={"project": self.concerned_object.key, "name": new_name})
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"Renaming {str(self)}", catch_http_statuses=(HTTPStatus.NOT_FOUND, HTTPStatus.BAD_REQUEST))
            if isinstance(e, HTTPError):
                if e.response.status_code == HTTPStatus.NOT_FOUND:
                    Branch.CACHE.pop(self)
                    raise exceptions.ObjectNotFound(self.concerned_object.key, f"str{self.concerned_object} not found")
                if e.response.status_code == HTTPStatus.BAD_REQUEST:
                    return False
        Branch.CACHE.pop(self)
        self.name = new_name
        Branch.CACHE.put(self)
        return True

    def __audit_zero_loc(self) -> list[Problem]:
        """Audits whether a branch has 0 LoC"""
        if self.last_analysis() and self.loc() == 0:
            return [Problem(get_rule(RuleId.PROJ_ZERO_LOC), self, str(self))]
        return []

    def __audit_never_analyzed(self) -> list[Problem]:
        """Detects branches that have never been analyzed are are kept when inactive"""
        if not self.last_analysis() and self.is_kept_when_inactive():
            return [Problem(get_rule(RuleId.BRANCH_NEVER_ANALYZED), self, str(self))]
        return []

    def get_findings(self) -> dict[str, object]:
        """Returns a branch list of findings

        :return: dict of Findings, with finding key as key
        :rtype: dict{key: Finding}
        """
        findings = self.get_issues()
        findings.update(self.get_hotspots())
        return findings

    def component_data(self) -> dict[str, str]:
        """Returns key data"""
        return {
            "key": self.concerned_object.key,
            "name": self.concerned_object.name,
            "type": type(self.concerned_object).__name__.upper(),
            "branch": self.name,
            "url": self.url(),
        }

    def sync(self, another_branch: Branch, sync_settings: types.ConfigSettings) -> tuple[list[dict[str, str]], dict[str, int]]:
        """Syncs branch findings with another branch

        :param Branch another_branch: other branch to sync issues into (not necesssarily of same project)
        :param dict sync_settings: Parameters to configure the sync
        :return: sync report as tuple, with counts of successful and unsuccessful issue syncs
        :rtype: tuple(report, counters)
        """
        from sonar.syncer import sync_lists

        report, counters = [], {}
        log.info("Syncing %s (%s) and %s (%s) issues", str(self), self.endpoint.url, str(another_branch), another_branch.endpoint.url)
        (report, counters) = sync_lists(
            list(self.get_issues().values()),
            list(another_branch.get_issues().values()),
            self,
            another_branch,
            sync_settings=sync_settings,
        )
        log.info("Syncing %s (%s) and %s (%s) hotspots", str(self), self.endpoint.url, str(another_branch), another_branch.endpoint.url)
        (tmp_report, tmp_counts) = sync_lists(
            list(self.get_hotspots().values()),
            list(another_branch.get_hotspots().values()),
            self,
            another_branch,
            sync_settings=sync_settings,
        )
        report += tmp_report
        counters = util.dict_add(counters, tmp_counts)
        return (report, counters)

    def __audit_last_analysis(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        age = util.age(self.last_analysis())
        if self.is_main() or age is None:
            # Main branch (not purgeable) or branch not analyzed yet
            return []
        max_age = audit_settings.get("audit.projects.branches.maxLastAnalysisAge", 30)
        problems = []
        if self.is_main():
            log.debug("%s is main (not purgeable)", str(self))
        elif self.is_kept_when_inactive():
            log.debug("%s is kept when inactive (not purgeable)", str(self))
        elif age > max_age:
            problems.append(Problem(get_rule(RuleId.BRANCH_LAST_ANALYSIS), self, str(self), age))
        else:
            log.debug("%s age is %d days", str(self), age)
        return problems

    def audit(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits a branch and return list of problems found

        :param ConfigSettings audit_settings: Options of what to audit and thresholds to raise problems
        :return: List of problems found, or empty list
        """
        if not audit_settings.get("audit.project.branches", True):
            log.debug("Branch audit disabled, skipping audit of %s", str(self))
            return []
        log.debug("Auditing %s", str(self))
        try:
            return (
                self.__audit_last_analysis(audit_settings)
                + self.__audit_zero_loc()
                + self.__audit_never_analyzed()
                + self._audit_bg_task(audit_settings)
                + self._audit_history_retention(audit_settings)
                + self._audit_accepted_or_fp_issues(audit_settings)
            )
        except Exception as e:
            log.error("%s while auditing %s, audit skipped", util.error_msg(e), str(self))
        return []

    def api_params(self, op: str = c.GET) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {c.GET: {"project": self.concerned_object.key, "branch": self.name}, c.LIST: {"project": self.concerned_object.key}}
        return ops[op] if op in ops else ops[c.GET]

    def last_task(self) -> Optional[tasks.Task]:
        """Returns the last analysis background task of a problem, or none if not found"""
        return tasks.search_last(component_key=self.concerned_object.key, endpoint=self.endpoint, type="REPORT", branch=self.name)


def get_list(project: projects.Project) -> dict[str, Branch]:
    """Retrieves the list of branches of a project

    :param projects.Project project: projects.Project the branch belongs to
    :raises UnsupportedOperation: Branches not supported in Community Edition
    :return: List of project branches
    :rtype: dict{branch_name: Branch}
    """
    if project.endpoint.edition() == "community":
        log.debug(_UNSUPPORTED_IN_CE)
        raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)

    log.debug("Reading all branches of %s", str(project))
    data = json.loads(project.endpoint.get(Branch.API[c.LIST], params={"project": project.key}).text)
    return {branch["name"]: Branch.load(project, branch["name"], data=branch) for branch in data.get("branches", {})}


def exists(endpoint: platform.Platform, branch_name: str, project_key: str) -> bool:
    """Checks if a branch exists

    :param Platform endpoint: Reference to the SonarQube platform
    :param str branch_name: Branch name
    :param str project_key: projects.Project key
    :raises UnsupportedOperation: Branches not supported in Community Edition
    :return: Whether the branch exists in SonarQube
    :rtype: bool
    """
    try:
        project = projects.Project.get_object(endpoint, project_key)
    except exceptions.ObjectNotFound:
        return False
    return branch_name in get_list(project)
