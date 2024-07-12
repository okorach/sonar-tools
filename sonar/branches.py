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

from __future__ import annotations
from http import HTTPStatus
import json
from urllib.parse import unquote
from requests.exceptions import HTTPError
import requests.utils

from sonar import platform
import sonar.logging as log
import sonar.sqobject as sq
from sonar import components, syncer, settings, exceptions
from sonar import projects
import sonar.utilities as util

from sonar.audit import rules, problem

_OBJECTS = {}

#: APIs used for branch management
APIS = {
    "list": "project_branches/list",
    "rename": "project_branches/rename",
    "get_new_code": "new_code_periods/list",
    "delete": "project_branches/delete",
}

_UNSUPPORTED_IN_CE = "Branches not available in Community Edition"


class Branch(components.Component):
    """
    Abstraction of the SonarQube "project branch" concept
    """

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
        _OBJECTS[self.uuid()] = self
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
        uu = uuid(concerned_object.key, branch_name, concerned_object.endpoint.url)
        if uu in _OBJECTS:
            return _OBJECTS[uu]
        try:
            data = json.loads(concerned_object.endpoint.get(APIS["list"], params={"project": concerned_object.key}).text)
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                raise exceptions.ObjectNotFound(concerned_object.key, f"Project '{concerned_object.key}' not found")
        for br in data.get("branches", []):
            if br["name"] == branch_name:
                return cls.load(concerned_object, branch_name, br)
        raise exceptions.ObjectNotFound(branch_name, f"Branch '{branch_name}' of project '{concerned_object.key}' not found")

    @classmethod
    def load(cls, concerned_object: projects.Project, branch_name: str, data: dict[str, str]) -> Branch:
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
        uu = uuid(concerned_object.key, branch_name, concerned_object.endpoint.url)
        o = _OBJECTS[uu] if uu in _OBJECTS else cls(concerned_object, branch_name)
        o._load(data)
        return o

    def __str__(self):
        return f"branch '{self.name}' of {str(self.concerned_object)}"

    def refresh(self) -> Branch:
        """Reads a branch in SonarQube (refresh with latest data)

        :raises ObjectNotFound: Branch not found in SonarQube
        :return: itself
        :rtype: Branch
        """
        try:
            data = json.loads(self.get(APIS["list"], params={"project": self.concerned_object.key}).text)
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                raise exceptions.ObjectNotFound(self.key, f"{str(self)} not found in SonarQube")
        for br in data.get("branches", []):
            if br["name"] == self.name:
                self._load(br)
            else:
                # While we're there let's load other branches with up to date branch data
                Branch.load(self.concerned_object, br["name"], data)
        return self

    def _load(self, data):
        if self._json is None:
            self._json = data
        else:
            self._json.update(data)
        self._is_main = self._json["isMain"]
        self._last_analysis = util.string_to_date(self._json.get("analysisDate", None))
        self._keep_when_inactive = self._json.get("excludedFromPurge", False)
        self._is_main = self._json.get("isMain", False)

    def uuid(self):
        """Computes a uuid for the branch that can serve as index
        :return: the UUID
        :rtype: str
        """
        return uuid(self.concerned_object.key, self.name, self.endpoint.url)

    def is_kept_when_inactive(self):
        """
        :return: Whether the branch is kept when inactive
        :rtype: bool
        """
        if self._keep_when_inactive is None or self._json is None:
            self.refresh()
        return self._keep_when_inactive

    def is_main(self):
        """
        :return: Whether the branch is the project main branch
        :rtype: bool
        """
        if self._is_main is None or self._json is None:
            self.refresh()
        return self._is_main

    def delete(self):
        """Deletes a branch

        :raises ObjectNotFound: Branch not found for deletion
        :return: Whether the deletion was successful
        :rtype: bool
        """
        try:
            return sq.delete_object(self, APIS["delete"], {"branch": self.name, "project": self.concerned_object.key}, _OBJECTS)
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.BAD_REQUEST:
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
                data = json.loads(self.get(api=APIS["get_new_code"], params={"project": self.concerned_object.key}).text)
            except HTTPError as e:
                if e.response.status_code == HTTPStatus.NOT_FOUND:
                    raise exceptions.ObjectNotFound(self.concerned_object.key, f"{str(self.concerned_object)} not found")
                if e.response.status_code == HTTPStatus.FORBIDDEN:
                    log.error("Error 403 when getting new code period of %s", {str(self)})
                raise e
            for b in data["newCodePeriods"]:
                new_code = settings.new_code_to_string(b)
                if b["branchKey"] == self.name:
                    self._new_code = new_code
                else:
                    # While we're there let's store the new code of other branches
                    Branch.get_object(self.concerned_object, b["branchKey"])._new_code = new_code
        return self._new_code

    def export(self, export_settings: dict[str, str]) -> dict[str, str]:
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
        data = util.remove_nones(data)
        return None if len(data) == 0 else data

    def url(self):
        """
        :return: The branch URL in SonarQube as permalink
        :rtype: str
        """
        return f"{self.endpoint.url}/dashboard?id={self.concerned_object.key}&branch={requests.utils.quote(self.name)}"

    def rename(self, new_name):
        """Renames a branch

        :param new_name: New branch name
        :type new_name: str
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
            self.post(APIS["rename"], params={"project": self.concerned_object.key, "name": new_name})
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                raise exceptions.ObjectNotFound(self.concerned_object.key, f"str{self.concerned_object} not found")
        _OBJECTS.pop(self.uuid(), None)
        self.name = new_name
        _OBJECTS[self.uuid()] = self
        return True

    def __audit_zero_loc(self):
        if self.last_analysis() and self.loc() == 0:
            rule = rules.get_rule(rules.RuleId.PROJ_ZERO_LOC)
            return [problem.Problem(broken_rule=rule, msg=rule.msg.format(str(self)), concerned_object=self)]
        return []

    def __audit_never_analyzed(self) -> list[problem.Problem]:
        """Detects branches that have never been analyzed are are kept when inactive"""
        if not self.last_analysis() and self.is_kept_when_inactive():
            rule = rules.get_rule(rules.RuleId.BRANCH_NEVER_ANALYZED)
            return [problem.Problem(broken_rule=rule, msg=rule.msg.format(str(self)), concerned_object=self)]
        return []

    def get_findings(self):
        """Returns a branch list of findings

        :return: dict of Findings, with finding key as key
        :rtype: dict{key: Finding}
        """
        return self.get_issues() + self.get_hotspots()

    def component_data(self) -> dict[str, str]:
        """Returns key data"""
        return {
            "key": self.concerned_object.key,
            "name": self.concerned_object.name,
            "type": type(self.concerned_object).__name__.upper(),
            "branch": self.name,
            "url": self.url(),
        }

    def sync(self, another_branch: Branch, sync_settings: dict[str, str]) -> tuple[list[dict[str, str]], dict[str, int]]:
        """Syncs branch findings with another branch

        :param another_branch: other branch to sync issues into (not necesssarily of same project)
        :type another_branch: Branch
        :param sync_settings: Parameters to configure the sync
        :type sync_settings: dict
        :return: sync report as tuple, with counts of successful and unsuccessful issue syncs
        :rtype: tuple(report, counters)
        """
        report, counters = [], {}
        log.info("Syncing %s (%s) and %s (%s) issues", str(self), self.endpoint.url, str(another_branch), another_branch.endpoint.url)
        (report, counters) = syncer.sync_lists(
            list(self.get_issues().values()),
            list(another_branch.get_issues().values()),
            self,
            another_branch,
            sync_settings=sync_settings,
        )
        log.info("Syncing %s (%s) and %s (%s) hotspots", str(self), self.endpoint.url, str(another_branch), another_branch.endpoint.url)
        (tmp_report, tmp_counts) = syncer.sync_lists(
            list(self.get_hotspots().values()),
            list(another_branch.get_hotspots().values()),
            self,
            another_branch,
            sync_settings=sync_settings,
        )
        report += tmp_report
        counters = util.dict_add(counters, tmp_counts)
        return (report, counters)

    def __audit_last_analysis(self, audit_settings):
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
            rule = rules.get_rule(rules.RuleId.BRANCH_LAST_ANALYSIS)
            msg = rule.msg.format(str(self), age)
            problems.append(problem.Problem(broken_rule=rule, msg=msg, concerned_object=self))
        else:
            log.debug("%s age is %d days", str(self), age)
        return problems

    def audit(self, audit_settings):
        """Audits a branch and return list of problems found

        :meta private:
        :param audit_settings: Options of what to audit and thresholds to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        if audit_settings.get("audit.project.branches", True):
            log.debug("Auditing %s", str(self))
            try:
                return self.__audit_last_analysis(audit_settings) + self.__audit_zero_loc() + self.__audit_never_analyzed()
            except HTTPError as e:
                if e.response.status_code == HTTPStatus.FORBIDDEN:
                    log.error("Not enough permission to fully audit %s", str(self))
                else:
                    log.error("HTTP error %s while auditing %s", str(e), str(self))
        else:
            log.debug("Branch audit disabled, skipping audit of %s", str(self))
        return []

    def search_params(self) -> dict[str, str]:
        """Return params used to search/create/delete for that object"""
        return {"project": self.concerned_object.key, "branch": self.name}


def uuid(project_key: str, branch_name: str, url: str) -> str:
    """Computes a uuid for the branch that can serve as index

    :param str project_key: The project key
    :param str branch_name: The branch name
    :return: the UUID
    :rtype: str
    """
    return f"{project_key}{components.KEY_SEPARATOR}{branch_name}@{url}"


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
    data = json.loads(project.endpoint.get(APIS["list"], params={"project": project.key}).text)
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
