#
# sonar-tools
# Copyright (C) 2022-2023 Olivier Korach
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

from http import HTTPStatus
import json
from urllib.parse import unquote
from requests.exceptions import HTTPError
import requests.utils
import sonar.sqobject as sq
from sonar import measures, components, syncer, settings, exceptions
from sonar.projects import projects
from sonar.findings import issues, hotspots
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

    @classmethod
    def get_object(cls, concerned_object, branch_name):
        """Gets a SonarQube Branch object

        :param concerned_object: Object concerned by the branch (Project or Application)
        :type concerned_object: Project or Application
        :param str branch_name: The branch name
        :raises UnsupportedOperation: If trying to manipulate branches on a community edition
        :raises ObjectNotFound: If project key or branch name not found in SonarQube
        :return: The Branch object
        :rtype: Branch
        """
        branch_name = unquote(branch_name)
        _uuid = uuid(concerned_object.key, branch_name)
        if _uuid in _OBJECTS:
            return _OBJECTS[_uuid]
        try:
            data = json.loads(concerned_object.endpoint.get(APIS["list"], params={"project": concerned_object.key}).text)
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                raise exceptions.ObjectNotFound(concerned_object.key, f"Project '{concerned_object.key}' not found")
        for br in data.get("branches", []):
            if br["name"] == branch_name:
                return cls.load(concerned_object, branch_name, data)
        raise exceptions.ObjectNotFound(branch_name, f"Branch '{branch_name}' of project '{concerned_object.key}' not found")

    @classmethod
    def load(cls, concerned_object, branch_name, data):
        """Gets a Branch object from JSON data gotten from a list API call

        :param concerned_object: Object concerned by the branch (Project or Application)
        :type concerned_object: Project or Application
        :param str branch_name:
        :param dict data:
        :raises UnsupportedOperation: If trying to manipulate branches on a community edition
        :raises ObjectNotFound: If project key or branch name not found in SonarQube
        :return: The Branch object
        :rtype: Branch
        """
        branch_name = unquote(branch_name)
        _uuid = uuid(concerned_object.key, branch_name)
        o = _OBJECTS[_uuid] if _uuid in _OBJECTS else cls(concerned_object, branch_name)
        o._load(data)
        return o

    def __init__(self, concerned_object, name):
        """Don't use this, use class methods to create Branch objects

        :raises UnsupportedOperation: When attempting to branches on Community Edition
        """
        if concerned_object.endpoint.edition() == "community":
            raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)
        name = unquote(name)
        super().__init__(name, concerned_object.endpoint)
        self.name = name
        self.concerned_object = concerned_object
        self._is_main = None
        self._new_code = None
        self._last_analysis = None
        self._keep_when_inactive = None
        _OBJECTS[self.uuid()] = self
        util.logger.debug("Created object %s", str(self))

    def __str__(self):
        return f"branch '{self.name}' of {str(self.concerned_object)}"

    def refresh(self):
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
        return uuid(self.concerned_object.key, self.name)

    def last_analysis(self):
        """
        :param include_branches: Unused, present for inheritance reasons
        :type include_branches: bool, optional
        :return: Datetime of last analysis
        :rtype: datetime
        """
        if self._last_analysis is None:
            self.refresh()
        return self._last_analysis

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
                util.logger.warning("Can't delete %s, it's the main branch", str(self))
            return False

    def new_code(self):
        """
        :return: The branch new code period definition
        :rtype: str
        """
        if self._new_code is None:
            try:
                data = json.loads(self.get(api=APIS["get_new_code"], params={"project": self.concerned_object.key}).text)
            except HTTPError as e:
                if e.response.status_code == HTTPStatus.NOT_FOUND:
                    raise exceptions.ObjectNotFound(self.concerned_object.key, f"str{self.concerned_object} not found")
            for b in data["newCodePeriods"]:
                new_code = settings.new_code_to_string(b)
                if b["branchKey"] == self.name:
                    self._new_code = new_code
                else:
                    # While we're there let's store the new code of other branches
                    Branch.get_object(self.concerned_object, b["branchKey"])._new_code = new_code
        return self._new_code

    def export(self, full_export=True):
        """Exports a branch configuration (is main, keep when inactive, optionally name, project)

        :param full_export: Also export branches attributes that are not needed for import, defaults to True
        :type include_branches: bool, optional
        :return: The branch new code period definition
        :rtype: str
        """
        util.logger.debug("Exporting %s", str(self))
        data = {settings.NEW_CODE_PERIOD: self.new_code()}
        if self.is_main():
            data["isMain"] = True
        if self.is_kept_when_inactive() and not self.is_main():
            data["keepWhenInactive"] = True
        if self.new_code():
            data[settings.NEW_CODE_PERIOD] = self.new_code()
        if full_export:
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
            util.logger.debug("Skipping rename %s with same new name", str(self))
            return False
        util.logger.info("Renaming main branch of %s from '%s' to '%s'", str(self.concerned_object), self.name, new_name)
        try:
            self.post(APIS["rename"], params={"project": self.concerned_object.key, "name": new_name})
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                raise exceptions.ObjectNotFound(self.concerned_object.key, f"str{self.concerned_object} not found")
        _OBJECTS.pop(uuid(self.concerned_object.key, self.name), None)
        self.name = new_name
        _OBJECTS[uuid(self.concerned_object.key, self.name)] = self
        return True

    def __audit_zero_loc(self):
        if self.last_analysis() and self.loc() == 0:
            rule = rules.get_rule(rules.RuleId.PROJ_ZERO_LOC)
            return [problem.Problem(rule.type, rule.severity, rule.msg.format(str(self)), concerned_object=self)]
        return []

    def get_measures(self, metrics_list):
        """Retrieves a branch list of measures

        :param metrics_list: List of metrics to return
        :type metrics_list: str (comma separated)
        :return: List of measures of a projects
        :rtype: dict
        """
        return measures.get(self, metrics_list)

    def get_issues(self):
        """Returns a branch list of issues

        :return: dict of Issues, with issue key as key
        :rtype: dict{key: Issue}
        """
        return issues.search_all(
            endpoint=self.endpoint,
            params={
                "componentKeys": self.concerned_object.key,
                "branch": self.name,
                "additionalFields": "comments",
            },
        )

    def get_hotspots(self):
        """Returns a branch list of hotspots

        :return: dict of Hotspots, with hotspot key as key
        :rtype: dict{key: Hotspot}
        """
        return hotspots.search(
            endpoint=self.endpoint,
            params={
                "projectKey": self.concerned_object.key,
                "branch": self.name,
                "additionalFields": "comments",
            },
        )

    def get_findings(self):
        """Returns a branch list of findings

        :return: dict of Findings, with finding key as key
        :rtype: dict{key: Finding}
        """
        return self.get_issues() + self.get_hotspots()

    def sync(self, another_branch, sync_settings):
        """Syncs branch findings with another branch

        :param another_branch: other branch to sync issues into (not necesssarily of same project)
        :type another_branch: Branch
        :param sync_settings: Parameters to configure the sync
        :type sync_settings: dict
        :return: sync report as tuple, with counts of successful and unsuccessful issue syncs
        :rtype: tuple(report, counters)
        """
        report, counters = [], {}
        (report, counters) = syncer.sync_lists(
            self.get_issues(),
            another_branch.get_issues(),
            self,
            another_branch,
            sync_settings=sync_settings,
        )
        (tmp_report, tmp_counts) = syncer.sync_lists(
            self.get_hotspots(),
            another_branch.get_hotspots(),
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
        max_age = audit_settings["audit.projects.branches.maxLastAnalysisAge"]
        problems = []
        if self.is_main():
            util.logger.debug("%s is main (not purgeable)", str(self))
        elif self.is_kept_when_inactive():
            util.logger.debug("%s is kept when inactive (not purgeable)", str(self))
        elif age > max_age:
            rule = rules.get_rule(rules.RuleId.BRANCH_LAST_ANALYSIS)
            msg = rule.msg.format(str(self), age)
            problems.append(problem.Problem(rule.type, rule.severity, msg, concerned_object=self))
        else:
            util.logger.debug("%s age is %d days", str(self), age)
        return problems

    def audit(self, audit_settings):
        """Audits a branch and return list of problems found

        :meta private:
        :param audit_settings: Options of what to audit and thresholds to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        util.logger.debug("Auditing %s", str(self))
        return self.__audit_last_analysis(audit_settings) + self.__audit_zero_loc()

    def search_params(self):
        """Return params used to search for that object

        :meta private:
        """
        return {"project": self.concerned_object.key, "branch": self.name}


def uuid(project_key, branch_name):
    """Computes a uuid for the branch that can serve as index

    :param str project_key: The project key
    :param str branch_name: The branch name
    :return: the UUID
    :rtype: str
    """
    return f"{project_key} {branch_name}"


def get_list(project):
    """Retrieves the list of branches of a project

    :param Project project: Project the branch belongs to
    :raises UnsupportedOperation: Branches not supported in Community Edition
    :return: List of project branches
    :rtype: dict{branch_name: Branch}
    """
    if project.endpoint.edition() == "community":
        util.logger.debug(_UNSUPPORTED_IN_CE)
        raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)

    util.logger.debug("Reading all branches of %s", str(project))
    data = json.loads(project.endpoint.get(APIS["list"], params={"project": project.key}).text)
    return {branch["name"]: Branch.load(project, branch["name"], data=branch) for branch in data.get("branches", {})}


def exists(endpoint, branch_name, project_key):
    """Checks if a branch exists

    :param Platform endpoint: Reference to the SonarQube platform
    :param str branch_name: Branch name
    :param str project_key: Project key
    :raises UnsupportedOperation: Branches not supported in Community Edition
    :return: Whether the branch exists in SonarQube
    :rtype: bool
    """
    try:
        project = projects.Project.get_object(endpoint, project_key)
    except exceptions.ObjectNotFound:
        return False
    return branch_name in get_list(project)
