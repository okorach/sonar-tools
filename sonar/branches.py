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

"""Abstraction of the SonarQube project branch concept"""

from __future__ import annotations
from typing import Optional, Any, Union, TYPE_CHECKING

from http import HTTPStatus
import json
import re
from urllib.parse import unquote
import requests.utils

from sonar.util import cache
import sonar.logging as log
from sonar import components, settings, exceptions

import sonar.projects as proj
import sonar.util.misc as util
import sonar.utilities as sutil

from sonar.audit.problem import Problem
from sonar.audit.rules import get_rule, RuleId
import sonar.util.constants as c
from sonar.api.manager import ApiOperation as Oper
from sonar import measures

if TYPE_CHECKING:
    from sonar.tasks import Task
    from sonar.issues import Issue
    from sonar.hotspots import Hotspot
    from sonar.platform import Platform
    from sonar.components import Component
    from sonar.util.types import ApiPayload, ApiParams, ConfigSettings, ObjectJsonRepr

_UNSUPPORTED_IN_CE = "Branches not available in Community Edition"


class Branch(components.Component):
    """Abstraction of the SonarQube "project branch" concept"""

    CACHE = cache.Cache()
    __PROJECT_KEY = "projectKey"

    def __init__(self, endpoint: Platform, data: ApiPayload) -> None:
        """Don't use this, use class methods to create Branch objects

        :raises UnsupportedOperation: When attempting to branches on Community Edition
        """
        if endpoint.edition() == c.CE:
            raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)
        super().__init__(endpoint, data)
        self.branch = unquote(data["name"])
        self.name: str = self.branch
        self.concerned_object: proj.Project = proj.Project.get_project_object(endpoint, data[self.__class__.__PROJECT_KEY])
        log.debug("Loading branch %s of %s", self.name, self.concerned_object)
        self._is_main: bool = data.get("isMain")
        self._new_code: str = data.get("newCode")
        self._keep_when_inactive: str = data.get("excludedFromPurge")
        self.__class__.CACHE.put(self)
        log.debug("Constructed object %s", self)

    def __str__(self) -> str:
        return f"branch '{self.name}' of {self.project()}"

    @staticmethod
    def hash_payload(data: ApiPayload) -> tuple[Any, ...]:
        """Returns the hash items for a given object search payload"""
        return (data[Branch.__PROJECT_KEY], unquote(data["name"]))

    def hash_object(self) -> tuple[Any, ...]:
        """Computes a uuid for the branch that can serve as index"""
        return (self.concerned_object.key, self.name)

    @classmethod
    def get_object(cls, endpoint: Platform, project: Union[str, proj.Project], branch_name: str, use_cache: bool = False) -> Branch:
        """Returns the project object from its project key"""
        branch_name = unquote(branch_name)
        project = proj.Project.get_project_object(endpoint, project)
        o: Optional[Branch] = cls.CACHE.get(endpoint.local_url, project.key, branch_name)
        if use_cache and o:
            return o
        api, _, params, ret = endpoint.api.get_details(Branch, Oper.SEARCH, project=project.key)
        dataset = json.loads(project.get(api, params=params).text)[ret]
        for branch_data in dataset:
            cls.load(endpoint, branch_data | {cls.__PROJECT_KEY: project.key})
        if o := cls.CACHE.get(endpoint.local_url, project.key, branch_name):
            return o
        raise exceptions.ObjectNotFound(branch_name, f"Branch '{branch_name}' of {project} not found")

    @classmethod
    def search(cls, endpoint: Platform, project: Union[str, proj.Project], **search_params: Any) -> dict[str, Branch]:
        """Retrieves the list of branches of a project

        :param Project | str project: Project the branch belongs to
        :raises UnsupportedOperation: Branches not supported in Community Edition
        :return: List of project branches
        :rtype: dict{branch_name: Branch}
        """
        if endpoint.edition() == c.CE:
            log.debug(_UNSUPPORTED_IN_CE)
            raise exceptions.UnsupportedOperation(_UNSUPPORTED_IN_CE)
        if isinstance(project, str):
            project = proj.Project.get_object(endpoint, project, use_cache=True)
        log.debug("Reading all branches of %s", str(project))
        api, _, params, ret = project.endpoint.api.get_details(cls, Oper.SEARCH, project=project.key, **search_params)
        dataset = json.loads(endpoint.get(api, params=params).text)[ret]
        for branch_data in dataset:
            branch_data[cls.__PROJECT_KEY] = project.key
        res = {}
        for branch_data in dataset:
            res[branch_data["name"]] = cls.load(project.endpoint, branch_data)
        return res

    def reload(self, data: ApiPayload) -> Branch:
        """Reloads a Branch object from API data"""
        self.concerned_object = self.concerned_object or proj.Project.get_project_object(self.endpoint, data[self.__PROJECT_KEY])
        super().reload(data)
        self._is_main = self.sq_json["isMain"]
        self._keep_when_inactive = self.sq_json.get("excludedFromPurge", False)
        self._is_main = self.sq_json.get("isMain", False)
        return self

    def refresh(self) -> Branch:
        """Refresh a branch from SonarQube"""
        return self.__class__.get_object(self.endpoint, self.concerned_object, self.name, use_cache=False)

    def url(self) -> str:
        """returns the branch URL in SonarQube as permalink"""
        return f"{self.concerned_object.url()}&branch={requests.utils.quote(self.name)}"

    def project(self) -> Component:
        """Returns the project key"""
        return self.concerned_object

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
        return self.delete_object(project=self.concerned_object.key, branch=self.name)

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
            api, _, params, _ = self.endpoint.api.get_details(self, Oper.LIST_NEW_CODE_PERIODS, project=self.concerned_object.key)
            data = json.loads(self.get(api, params=params).text)
            for b in data["newCodePeriods"]:
                new_code = settings.new_code_to_string(b)
                if b["branchKey"] == self.name:
                    self._new_code = new_code
                else:
                    # While we're there let's store the new code of other branches
                    Branch.get_object(endpoint=self.endpoint, project=self.concerned_object, branch_name=b["branchKey"])._new_code = new_code
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
        api, _, params, _ = self.endpoint.api.get_details(
            self, Oper.KEEP_WHEN_INACTIVE, project=self.concerned_object.key, branch=self.name, value=str(keep).lower()
        )
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
        api, _, params, _ = self.endpoint.api.get_details(self, Oper.RENAME, project=self.concerned_object.key, name=new_name)
        self.post(api, params=params)
        self.__class__.CACHE.pop(self)
        self.name = new_name
        self.__class__.CACHE.put(self)
        return True

    def set_as_main(self) -> bool:
        """Sets the branch as the main branch of the project

        :raises ObjectNotFound: If the branch is not found
        :return: Whether the operation was successful
        """
        api, _, params, _ = self.endpoint.api.get_details(self, Oper.SET_MAIN, project=self.concerned_object.key, branch=self.name)
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
            data |= self.migration_export(export_settings, project=self.concerned_object.key, branch=self.name)
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

    def get_issues(self, **search_params: Any) -> dict[str, Issue]:
        """Returns a list of issues on a branch"""
        from sonar.issues import Issue

        return Issue.search_by_project(self.endpoint, project=self.concerned_object.key, **(search_params | {"branch": self.name}))

    def get_hotspots(self, **search_params: Any) -> dict[str, Hotspot]:
        """Returns a list of hotspots on a branch"""
        from sonar.hotspots import Hotspot

        return Hotspot.search(self.endpoint, **(search_params | {"project": self.concerned_object.key, "branch": self.name}))

    def get_findings(self, **search_params: Any) -> dict[str, Union[Issue, Hotspot]]:
        """Returns a list of findings, issues and hotspots together on a branch"""
        return self.concerned_object.get_findings(**(search_params | {"branch": self.name}))

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

    def last_task(self) -> Optional[Task]:
        """Returns the last analysis background task of a problem, or none if not found"""
        from sonar.tasks import Task

        if task := Task.search_last(self.endpoint, component=self.concerned_object.key, type="REPORT", branch=self.name):
            task.concerned_object = self
        return task

    def get_measures_history(self, metrics_list: list[str]) -> dict[str, str]:
        """Returns the history of a project metrics"""
        return measures.get_history(self, metrics_list, component=self.concerned_object.key, branch=self.name)
