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
from typing import Optional, Any, TYPE_CHECKING

from http import HTTPStatus
import json
import re
from urllib.parse import unquote
import requests.utils

from sonar.util import cache
import sonar.logging as log
from sonar import components, settings, exceptions, tasks

import sonar.projects as proj
import sonar.util.misc as util
import sonar.utilities as sutil

from sonar.audit.problem import Problem
from sonar.audit.rules import get_rule, RuleId
import sonar.util.constants as c
from sonar.api.manager import ApiOperation as op
from sonar.api.manager import ApiManager as Api

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload, ApiParams, ConfigSettings, ObjectJsonRepr
    from datetime import datetime

_UNSUPPORTED_IN_CE = "Branches not available in Community Edition"


class Branch(components.Component):
    """Abstraction of the SonarQube "project branch" concept"""

    CACHE = cache.Cache()

    def __init__(self, project: proj.Project, name: str) -> None:
        """Don't use this, use class methods to create Branch objects

        :raises UnsupportedOperation: When attempting to branches on Community Edition
        """
        if project.endpoint.edition() == c.CE:
            raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)
        name = unquote(name)
        super().__init__(endpoint=project.endpoint, key=name)
        self.name = name
        self.concerned_object: proj.Project = project
        self._is_main: Optional[bool] = None
        self._new_code: Optional[str] = None
        self._last_analysis: Optional[datetime] = None
        self._keep_when_inactive: Optional[bool] = None
        Branch.CACHE.put(self)
        log.debug("Created object %s", str(self))

    def __str__(self) -> str:
        return f"branch '{self.name}' of {str(self.project())}"

    def __hash__(self) -> int:
        """Computes a uuid for the branch that can serve as index"""
        return hash((self.concerned_object.key, self.name, self.base_url()))

    @classmethod
    def get_object(cls, concerned_object: proj.Project, branch_name: str) -> Branch:
        """Gets a SonarQube Branch object

        :param proj.Project concerned_object: Project concerned by the branch
        :param str branch_name: The branch name
        :raises UnsupportedOperation: If trying to manipulate branches on a community edition
        :raises ObjectNotFound: If project key or branch name not found in SonarQube
        :return: The Branch object
        :rtype: Branch
        """
        branch_name = unquote(branch_name)
        if o := Branch.CACHE.get(concerned_object.key, branch_name, concerned_object.base_url()):
            return o
        api, _, params, _ = Api(Branch, op.LIST, concerned_object.endpoint).get_all(project=concerned_object.key)
        data = json.loads(concerned_object.get(api, params=params).text)
        br = next((b for b in data.get("branches", []) if b["name"] == branch_name), None)
        if not br:
            raise exceptions.ObjectNotFound(branch_name, f"Branch '{branch_name}' of {str(concerned_object)} not found")
        return cls.load(concerned_object, branch_name, br)

    @classmethod
    def load(cls, concerned_object: proj.Project, branch_name: str, data: ApiPayload) -> Branch:
        """Gets a Branch object from JSON data gotten from a list API call

        :param proj.Project concerned_object: the Project the branch belonsg to
        :param str branch_name: Name of the branch
        :param dict data: Data received from API call
        :return: The Branch object
        :rtype: Branch
        """
        branch_name = unquote(branch_name)
        br_data = next((br for br in data.get("branches", []) if br["name"] == branch_name), None)
        if not (o := Branch.CACHE.get(concerned_object.key, branch_name, concerned_object.base_url())):
            o = cls(concerned_object, branch_name)
        if br_data:
            o.reload(br_data)
        return o

    @classmethod
    def get_list(cls, project: proj.Project) -> dict[str, Branch]:
        """Retrieves the list of branches of a project

        :param proj.Project project: Project the branch belongs to
        :raises UnsupportedOperation: Branches not supported in Community Edition
        :return: List of project branches
        :rtype: dict{branch_name: Branch}
        """
        if project.endpoint.edition() == c.CE:
            log.debug(_UNSUPPORTED_IN_CE)
            raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)

        log.debug("Reading all branches of %s", str(project))
        api, _, params, _ = Api(cls, op.LIST, project.endpoint).get_all(project=project.key)
        data = json.loads(project.endpoint.get(api, params=params).text)
        return {branch["name"]: cls.load(project, branch["name"], data=branch) for branch in data.get("branches", {})}

    @classmethod
    def exists(cls, endpoint: Platform, branch_name: str, project_key: str) -> bool:
        """Checks if a branch exists

        :param Platform endpoint: Reference to the SonarQube platform
        :param str branch_name: Branch name
        :param str project_key: Project key
        :raises UnsupportedOperation: Branches not supported in Community Edition
        """
        try:
            cls.get_object(concerned_object=proj.Project.get_object(endpoint, project_key), branch_name=branch_name)
        except exceptions.ObjectNotFound:
            return False
        return True

    def reload(self, data: ApiPayload) -> Branch:
        log.debug("Loading %s with data %s", self, data)
        self.sq_json = (self.sq_json or {}) | data
        self._is_main = self.sq_json["isMain"]
        self._last_analysis = sutil.string_to_date(self.sq_json.get("analysisDate", None))
        self._keep_when_inactive = self.sq_json.get("excludedFromPurge", False)
        self._is_main = self.sq_json.get("isMain", False)
        return self

    def url(self) -> str:
        """returns the branch URL in SonarQube as permalink"""
        return f"{self.concerned_object.url()}&branch={requests.utils.quote(self.name)}"

    def project(self) -> proj.Project:
        """Returns the project key"""
        return self.concerned_object

    def refresh(self) -> Branch:
        """Reads a branch in SonarQube (refresh with latest data)

        :raises ObjectNotFound: Branch not found in SonarQube
        :return: itself
        :rtype: Branch
        """
        api, _, params, _ = Api(self, op.LIST).get_all(**self.api_params(op.LIST))
        data = json.loads(self.get(api, params=params).text)
        br_data = next((br for br in data.get("branches", []) if br["name"] == self.name), None)
        if not br_data:
            Branch.CACHE.clear()
            raise exceptions.ObjectNotFound(self.name, f"{str(self)} not found")
        self.reload(br_data)
        # While we're there let's load other branches with up to date branch data
        for br in [b for b in data.get("branches", []) if b["name"] != self.name]:
            Branch.load(self.concerned_object, br["name"], data)
        return self

    def is_kept_when_inactive(self) -> bool:
        """Returns whether the branch is kept when inactive"""
        if self._keep_when_inactive is None or self.sq_json is None:
            self.refresh()
        return self._keep_when_inactive

    def is_main(self) -> bool:
        """Returns whether the branch is the project main branch"""
        if self._is_main is None or self.sq_json is None:
            self.refresh()
        return self._is_main

    def delete(self) -> bool:
        """Deletes a branch, return whether the deletion was successful"""
        return super().delete_object(**self.api_params(op.DELETE))

    def get(self, api: str, params: ApiParams = None, data: Optional[str] = None, mute: tuple[HTTPStatus] = (), **kwargs: str) -> requests.Response:
        """Performs an HTTP GET request for the object"""
        try:
            return super().get(api=api, params=params, data=data, mute=mute, **kwargs)
        except exceptions.ObjectNotFound as e:
            if re.match(r"Project .+ not found", e.message):
                log.warning("Clearing project cache")
                proj.Project.CACHE.clear()
            raise

    def post(self, api: str, params: ApiParams = None, mute: tuple[HTTPStatus] = (), **kwargs: str) -> requests.Response:
        """Performs an HTTP POST request for the object"""
        try:
            return super().post(api=api, params=params, mute=mute, **kwargs)
        except exceptions.ObjectNotFound as e:
            if re.match(r"Project .+ not found", e.message):
                log.warning("Clearing project cache")
                proj.Project.CACHE.clear()
            raise

    def new_code(self) -> str:
        """returns the branch new code period definition"""
        if self._new_code is None and self.endpoint.is_sonarcloud():
            self._new_code = settings.new_code_to_string({"inherited": True})
        elif self._new_code is None:
            api, _, params, _ = Api(self, op.LIST_NEW_CODE_PERIODS).get_all(**self.api_params(op.LIST))
            data = json.loads(self.get(api, params=params).text)
            for b in data["newCodePeriods"]:
                new_code = settings.new_code_to_string(b)
                if b["branchKey"] == self.name:
                    self._new_code = new_code
                else:
                    # While we're there let's store the new code of other branches
                    Branch.get_object(self.concerned_object, b["branchKey"])._new_code = new_code
        return self._new_code

    def set_keep_when_inactive(self, keep: bool) -> bool:
        """Sets whether the branch is kept when inactive

        :param bool keep: Whether to keep the branch when inactive
        :raises UnsupportedOperation: If trying to keep the main branch when inactive
        :raises ObjectNotFound: If the branch is not found
        :return: Whether the operation was successful
        """
        log.info("Setting %s keep when inactive to %s", self, keep)
        if self.is_main():
            if not keep:
                log.warning("%s is main branch, can't be purgeable, skipping...", str(self))
                raise exceptions.UnsupportedOperation(f"{str(self)} is the main branch, can't be purgeable")
            return True
        api, _, params, _ = Api(self, op.KEEP_WHEN_INACTIVE).get_all(**self.api_params(), value=str(keep).lower())
        self.post(api, params=params)
        self._keep_when_inactive = keep
        return True

    def rename(self, new_name: str) -> bool:
        """Renames a branch

        :param str new_name: New branch name
        :raises UnsupportedOperation: If trying to rename anything than the main branch
        :return: Whether the operation was successful
        """
        if not self.is_main():
            raise exceptions.UnsupportedOperation(f"{str(self)} can't be renamed since it's not the main branch")

        log.info("Renaming main branch of %s from '%s' to '%s'", str(self.concerned_object), self.name, new_name)
        api, _, params, _ = Api(self, op.RENAME).get_all(project=self.concerned_object.key, name=new_name)
        self.post(api, params=params)
        Branch.CACHE.pop(self)
        self.name = new_name
        Branch.CACHE.put(self)
        return True

    def set_as_main(self) -> bool:
        """Sets the branch as the main branch of the project

        :raises ObjectNotFound: If the branch is not found
        :return: Whether the operation was successful
        """
        api, _, params, _ = Api(self, op.SET_MAIN).get_all(**self.api_params())
        self.post(api, params=params)
        for b in self.concerned_object.branches().values():
            b._is_main = b.name == self.name
        return True

    def set_new_code(self, new_code_type: str, additional_data: Optional[Any]) -> bool:
        """Sets the branch new code period

        :param str new_code_type: PREVIOUS_VERSION, NUMBER_OF_DAYS, REFERENCE_BRANCH, SPECIFIC_ANALYSIS
        :param additional_data: Additional data depending on the new code type
        :return: Whether the operation was successful
        """
        log.info("Setting %s new code to %s / %s", self, new_code_type, additional_data)
        return settings.set_new_code_period(
            endpoint=self.endpoint, nc_type=new_code_type, nc_value=additional_data, project_key=self.concerned_object.key, branch=self.name
        )

    def export(self, export_settings: ConfigSettings) -> ObjectJsonRepr:
        """Exports a branch configuration (is main, keep when inactive, optionally name, project)

        :param bool full_export: Also export branches attributes that are not needed for import, optional, defaults to True
        :return: The branch configuration as JSON
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
            data |= {"name": self.name, "project": self.concerned_object.key}
        if export_settings.get("MODE", "") == "MIGRATION":
            data |= self.migration_export(export_settings)
        data = util.remove_nones(data)
        return None if len(data) == 0 else data

    def import_config(self, config_data: ObjectJsonRepr) -> None:
        """Imports a branch configuration

        :param config_data: The branch configuration to import
        """
        log.debug("Importing %s with %s", str(self), config_data)
        if config_data.get("isMain", False):
            self.set_as_main()
        try:
            self.set_keep_when_inactive(config_data.get("keepWhenInactive", False))
        except exceptions.UnsupportedOperation as e:
            log.warning(e.message)
        if settings.NEW_CODE_PERIOD in config_data:
            new_code = settings.string_to_new_code(config_data[settings.NEW_CODE_PERIOD])
            param = None
            if len(new_code) > 1:
                (new_code, param) = new_code
            self.set_new_code(new_code, param)

    def get_findings(self, filters: Optional[ApiParams] = None) -> dict[str, object]:
        """Returns a branch list of findings

        :return: dict of Findings, with finding key as key
        :rtype: dict{key: Finding}
        """
        if not filters:
            return self.concerned_object.get_findings(branch=self.name)
        return self.get_issues(filters) | self.get_hotspots(filters)

    def component_data(self) -> dict[str, str]:
        """Returns key data"""
        return {
            "key": self.concerned_object.key,
            "name": self.concerned_object.name,
            "type": type(self.concerned_object).__name__.upper(),
            "branch": self.name,
            "url": self.url(),
        }

    def project_key(self) -> str:
        """Returns the project key"""
        return self.concerned_object.key

    def sync(self, another_branch: Branch, sync_settings: ConfigSettings) -> tuple[list[dict[str, str]], dict[str, int]]:
        """Syncs branch findings with another branch

        :param Branch another_branch: other branch to sync issues into (not necessarily of same project)
        :param dict sync_settings: Parameters to configure the sync
        :return: sync report as tuple, with counts of successful and unsuccessful issue syncs
        :rtype: tuple(report, counters)
        """
        from sonar.syncer import sync_objects

        return sync_objects(self, another_branch, sync_settings=sync_settings)

    def __audit_never_analyzed(self) -> list[Problem]:
        """Detects branches that have never been analyzed are are kept when inactive"""
        if not self.last_analysis() and self.is_kept_when_inactive():
            return [Problem(get_rule(RuleId.BRANCH_NEVER_ANALYZED), self, str(self))]
        return []

    def __audit_last_analysis(self, audit_settings: ConfigSettings) -> list[Problem]:
        if self.is_main():
            log.info("%s is main (not purgeable)", str(self))
            return []
        if (max_age := audit_settings.get("audit.projects.branches.maxLastAnalysisAge", 30)) == 0:
            log.debug("%s last analysis audit is disabled, skipped...", str(self))
            return []
        if (age := util.age(self.last_analysis())) is None:
            log.warning("%s: Can't get last analysis date for audit, skipped", str(self))
            return []
        preserved = audit_settings.get("audit.projects.branches.keepWhenInactive", None)
        problems = []
        if preserved is not None and age > max_age and not re.match(rf"^{preserved}$", self.name):
            log.info("%s age %d greater than %d days and not matches '%s'", str(self), age, max_age, preserved)
            problems.append(Problem(get_rule(RuleId.BRANCH_LAST_ANALYSIS), self, str(self), age))
        elif self.is_kept_when_inactive():
            log.info("%s is kept when inactive (not purgeable)", str(self))
        elif age > max_age:
            problems.append(Problem(get_rule(RuleId.BRANCH_LAST_ANALYSIS), self, str(self), age))
        else:
            log.debug("%s age is %d days", str(self), age)
        return problems

    def audit(self, audit_settings: ConfigSettings) -> list[Problem]:
        """Audits a branch and return list of problems found

        :param ConfigSettings audit_settings: Options of what to audit and thresholds to raise problems
        :return: List of problems found, or empty list
        """
        if not audit_settings.get("audit.project.branches", True):
            log.debug("Branch audit disabled, skipping audit of %s", str(self))
            return []
        log.debug("Auditing %s", str(self))
        try:
            if audit_settings.get(c.AUDIT_MODE_PARAM, "") == "housekeeper":
                return self.__audit_last_analysis(audit_settings)
            return self.__audit_last_analysis(audit_settings) + self.__audit_never_analyzed() + self._audit_component(audit_settings)
        except Exception as e:
            log.error("%s while auditing %s, audit skipped", sutil.error_msg(e), str(self))
        return []

    def api_params(self, operation: Optional[Any] = None) -> ApiParams:
        """Return params used to search/create/delete for that object"""
        ops = {
            op.READ: {"project": self.concerned_object.key, "branch": self.name},
            op.LIST: {"project": self.concerned_object.key},
            op.DELETE: {"project": self.concerned_object.key, "branch": self.name},
        }
        return ops[operation] if operation and operation in ops else ops[op.READ]

    def last_task(self) -> Optional[tasks.Task]:
        """Returns the last analysis background task of a problem, or none if not found"""
        if task := tasks.search_last(component_key=self.concerned_object.key, endpoint=self.endpoint, type="REPORT", branch=self.name):
            task.concerned_object = self
        return task
