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

"""Abstraction of the SonarQube "application" concept"""

from __future__ import annotations
from typing import Optional, Any, Union, TYPE_CHECKING

import re
import json
from datetime import datetime
from http import HTTPStatus
from threading import Lock
from requests import RequestException

import sonar.logging as log
from sonar.util import cache

from sonar.api.manager import ApiOperation as op
from sonar.api.manager import ApiManager as Api
from sonar import exceptions, projects, branches, app_branches
from sonar.permissions import application_permissions
import sonar.aggregations as aggr
import sonar.util.misc as util
import sonar.utilities as sutil
from sonar.audit import rules, problem
import sonar.util.constants as c
from sonar.util import common_json_helper


if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ConfigSettings, KeyList, ObjectJsonRepr, AppBranchDef, PermissionDef, AppBranchProjectDef


_CLASS_LOCK = Lock()
_IMPORTABLE_PROPERTIES = ("key", "name", "description", "visibility", "branches", "permissions", "tags")


class Application(aggr.Aggregation):
    """
    Abstraction of the SonarQube "application" concept
    """

    CACHE = cache.Cache()

    def __init__(self, endpoint: Platform, key: str, name: str) -> None:
        """Don't use this directly, go through the class methods to create Objects"""
        super().__init__(endpoint=endpoint, key=key)
        self._branches: Optional[dict[str, app_branches.ApplicationBranch]] = None
        self._projects: Optional[dict[str, str]] = None
        self._description: Optional[str] = None
        self.name = name
        log.debug("Constructed object %s with uuid %d id %x", str(self), hash(self), id(self))
        Application.CACHE.put(self)

    def __str__(self) -> str:
        """String name of object"""
        return f"application key '{self.key}'"

    @classmethod
    def get_object(cls, endpoint: Platform, key: str) -> Application:
        """Gets an Application object from SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application key not found in SonarQube
        :return: The found Application object
        :rtype: Application
        """
        check_supported(endpoint)
        o: Application = cls.CACHE.get(key, endpoint.local_url)
        if o:
            return o
        api, _, params, ret = Api(cls, op.GET, endpoint).get_all(application=key)
        data = json.loads(endpoint.get(api, params=params).text)[ret]
        return cls.load(endpoint, data)

    @classmethod
    def load(cls, endpoint: Platform, data: ApiPayload) -> Application:
        """Loads an Application object with data retrieved from SonarQube

        :param endpoint: Reference to the SonarQube platform
        :param data: Data coming from api/components/search_projects or api/applications/show
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application key not found in SonarQube
        :return: The found Application object
        """
        check_supported(endpoint)
        o: Application = cls.CACHE.get(data["key"], endpoint.local_url)
        if not o:
            o = cls(endpoint, data["key"], data["name"])
        o.reload(data)
        return o

    @classmethod
    def create(cls, endpoint: Platform, key: str, name: str) -> Application:
        """Creates an Application object in SonarQube

        :param endpoint: Reference to the SonarQube platform
        :param key: Application key, must not already exist on SonarQube
        :param name: Application name
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectAlreadyExists: If key already exist for another Application
        :return: The created Application object
        """
        check_supported(endpoint)
        api, _, params, _ = Api(cls, op.CREATE, endpoint).get_all(key=key, name=name)
        endpoint.post(api, params=params)
        return Application(endpoint=endpoint, key=key, name=name)

    @classmethod
    def search(cls, endpoint: Platform, params: Optional[ApiParams] = None) -> dict[str, Application]:
        """Searches applications

        :param endpoint: Reference to the SonarQube platform
        :param params: Search filters (see api/components/search_projects parameters)
        :raises UnsupportedOperation: If on a community edition
        :return: dict of applications
        """
        check_supported(endpoint)
        new_params = (params or {}) | {"filter": "qualifier = APP"}
        return cls.get_paginated(endpoint=endpoint, params=new_params)

    @classmethod
    def get_list(cls, endpoint: Platform, key_list: KeyList = None, use_cache: bool = True) -> dict[str, Application]:
        """
        :return: List of Applications (all of them if key_list is None or empty)
        :param endpoint: Reference to the Sonar platform
        :param key_list: List of app keys to get, if None or empty all applications are returned
        :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
        """
        check_supported(endpoint)
        with _CLASS_LOCK:
            if key_list is None or len(key_list) == 0 or not use_cache:
                log.info("Listing applications")
                return dict(sorted(cls.search(endpoint=endpoint).items()))
            object_list = {key: cls.get_object(endpoint, key) for key in sorted(key_list)}
        return object_list

    def refresh(self) -> Application:
        """Refreshes the application by re-reading SonarQube

        :raises ObjectNotFound: If the Application does not exists anymore
        """
        try:
            self.reload(json.loads(self.get("navigation/component", params={"component": self.key}).text))
            api, _, params, ret = Api(self, op.GET).get_all(application=self.key)
            self.reload(json.loads(self.endpoint.get(api, params=params).text)[ret])
            return self
        except exceptions.ObjectNotFound:
            self.__class__.CACHE.pop(self)
            raise

    def permissions(self) -> application_permissions.ApplicationPermissions:
        """
        :return: The application permissions
        """
        if self._permissions is None:
            self._permissions = application_permissions.ApplicationPermissions(self)
        return self._permissions

    def projects(self) -> dict[str, str]:
        """
        :return: The project branches included in the application
        :rtype: dict{<projectKey>: <branch>}
        """
        if self._projects is not None:
            return self._projects
        self._projects = {}
        self.refresh()
        log.debug("Refreshing project list with %s", util.json_dump(self.sq_json["projects"]))
        for p in self.sq_json["projects"]:
            # TODO: Support several branches of same project in the Application
            # TODO: Return projects in an application branch
            self._projects[p["key"]] = p["branch"]
        return self._projects

    def branch_exists(self, branch: str) -> bool:
        """
        :return: Whether the Application branch exists
        :rtype: bool
        """
        return app_branches.ApplicationBranch.exists(self.endpoint, app=self, branch_name=branch)

    def branch_is_main(self, branch: str) -> bool:
        """
        :return: Whether the Application branch is the main branch
        :rtype: bool
        """
        return app_branches.ApplicationBranch.get_object(self.endpoint, self, branch).is_main()

    def main_branch(self) -> object:
        """Returns the application main branch"""
        return next((br for br in self.branches().values() if br.is_main()), None)

    def create_branch(self, branch_name: str, branch_definition: ObjectJsonRepr) -> object:
        """Creates an application branch

        :param branch_name: The Application branch to set
        :param branch_definition, {<projectKey!>: <branchName1>, <projectKey2>: <branchName2>, ...}
        :raises ObjectAlreadyExists: if the branch name already exists
        :raises ObjectNotFound: if one of the specified projects or project branches does not exists
        """
        try:
            return app_branches.ApplicationBranch.create(
                app=self, name=branch_name, projects_or_branches=self.__get_project_branches(branch_definition)
            )
        except exceptions.UnsupportedOperation as e:
            log.error("Error creating %s branch '%s': %s", self, branch_name, e.message)
            return None

    def delete_branch(self, branch_name: str) -> bool:
        """Deletes an application branch

        :param branch_name: The Application branch to set
        :raises ObjectNotFound: if the branch name does not exist
        """
        return app_branches.ApplicationBranch.get_object(self.endpoint, self, branch_name).delete()

    def update_branch(self, branch_name: str, branch_definition: ObjectJsonRepr) -> object:
        """Updates an Application branch with a branch definition"""
        o_app_branch = app_branches.ApplicationBranch.get_object(self.endpoint, self, branch_name)
        try:
            o_app_branch.update_project_branches(new_project_branches=self.__get_project_branches(branch_definition))
        except exceptions.UnsupportedOperation as e:
            log.error("Error updating %s branch '%s': %s", self, branch_name, e.message)
            return None
        return o_app_branch

    def set_branches(self, branch_name: str, projects_data: list[AppBranchProjectDef]) -> Application:
        """Creates or updates an Application branch with a set of project branches

        :param branch_name: The Application branch to set
        :param branch_data: in format returned by api/applications/show or {"projects": {<projectKey>: <branch>, ...}}
        :raises ObjectNotFound: if a project key does not exist or project branch does not exist
        :return: self
        """
        log.debug("%s: APPL Updating application branch '%s' with %s", self, branch_name, util.json_dump(projects_data))
        branch_definition = {p["key"]: p.get("branch", c.DEFAULT_BRANCH) for p in projects_data}
        try:
            o = app_branches.ApplicationBranch.get_object(self.endpoint, self, branch_name)
            o.update_project_branches(new_project_branches=self.__get_project_branches(branch_definition))
        except exceptions.ObjectNotFound:
            self.create_branch(branch_name=branch_name, branch_definition=branch_definition)
        except exceptions.UnsupportedOperation as e:
            log.error("Error creating %s branch '%s': %s", self, branch_name, e.message)
        return self

    def branches(self) -> dict[str, object]:
        """
        :return: the list of branches of the application and their definition
        :rtype: dict {<branchName>: <ApplicationBranch>}
        """
        self.refresh()
        self._branches = app_branches.list_from(app=self, data=self.sq_json)
        return self._branches

    def delete(self) -> bool:
        """Deletes an Application and all its branches

        :return: Whether the delete succeeded
        """
        if self.branches() is not None:
            for branch in self.branches().values():
                branch.delete()
        return super().delete_object(application=self.key)

    def get_hotspots(self, filters: Optional[dict[str, str]] = None) -> dict[str, object]:
        """Returns the security hotspots of the application (ie of its projects or branches)"""
        new_filters = filters.copy() if filters else {}
        pattern = new_filters.pop("branch", None) if new_filters else None
        if not pattern:
            return super().get_hotspots(new_filters)
        matching_branches = [b for b in self.branches().values() if re.match(rf"^{pattern}$", b.name)]
        findings_list = {}
        for comp in matching_branches:
            findings_list |= comp.get_hotspots(new_filters)
        return findings_list

    def get_issues(self, filters: Optional[dict[str, str]] = None) -> dict[str, object]:
        """Returns the issues of the application (ie of its projects or branches)"""
        new_filters = filters.copy() if filters else {}
        pattern = new_filters.pop("branch", None) if new_filters else None
        if not pattern:
            return super().get_issues(new_filters)
        matching_branches = [b for b in self.branches().values() if re.match(rf"^{pattern}$", b.name)]
        findings_list = {}
        for comp in matching_branches:
            findings_list |= comp.get_issues(new_filters)
        return findings_list

    def nbr_projects(self, use_cache: bool = False) -> int:
        """Returns the nbr of projects of an application"""
        return len(self.projects())

    def _audit_empty(self, audit_settings: ConfigSettings) -> list[problem.Problem]:
        """Audits if an application contains 0 projects"""
        log.debug("Auditing empty for %s", self)
        if not audit_settings.get("audit.applications.empty", True):
            log.debug("Auditing empty applications is disabled, skipping...")
            return []
        return super()._audit_empty_aggregation(broken_rule=rules.RuleId.APPLICATION_EMPTY)

    def _audit_singleton(self, audit_settings: ConfigSettings) -> list[problem.Problem]:
        """Audits if an application contains a single project (makes littel sense)"""
        log.debug("Auditing singleton for %s", self)
        if not audit_settings.get("audit.applications.singleton", True):
            log.debug("Auditing singleton applications is disabled, skipping...")
            return []
        return super()._audit_singleton_aggregation(broken_rule=rules.RuleId.APPLICATION_SINGLETON)

    def audit(self, audit_settings: ConfigSettings, **kwargs) -> list[problem.Problem]:
        """Audits an application and returns list of problems found

        :param dict audit_settings: Audit configuration settings from sonar-audit properties config file
        """
        if not audit_settings.get("audit.applications", True):
            log.debug("Auditing applications is disabled, skipping...")
            return []
        log.info("Auditing %s", str(self))
        problems = (
            super().audit(audit_settings)
            + self._audit_empty(audit_settings)
            + self._audit_singleton(audit_settings)
            + self._audit_bg_task(audit_settings)
            + self.audit_visibility(audit_settings)
        )
        "write_q" in kwargs and kwargs["write_q"].put(problems)
        return problems

    def export(self, export_settings: ConfigSettings) -> ObjectJsonRepr:
        """Exports an application"""
        log.info("Exporting %s", str(self))
        self.refresh()
        json_data = self.sq_json.copy()
        json_data.update(
            {
                "key": self.key,
                "name": self.name,
                "description": None if self._description == "" else self._description,
                "visibility": self.visibility(),
                # 'projects': self.projects(),
                "branches": {br.name: br.export() for br in self.branches().values()},
                "permissions": self.permissions().export(export_settings=export_settings),
                "tags": self.get_tags(),
            }
        )
        json_data = convert_app_json(json_data)
        return util.filter_export(json_data, _IMPORTABLE_PROPERTIES, export_settings.get("FULL_EXPORT", False))

    def set_permissions(self, data: list[PermissionDef]) -> application_permissions.ApplicationPermissions:
        """Sets an application permissions

        :param data: list of permissions definitions
        :raises: ObjectNotFound if a user or a group does not exists
        :return: self
        """
        return self.permissions().set(data)

    def add_projects(self, project_list: list[str]) -> bool:
        """Add projects to an application"""
        current_projects = self.projects().keys()
        ok = True
        api_def = Api(self, op.ADD_PROJECT)
        for proj in [p for p in project_list if p not in current_projects]:
            log.debug("Adding project '%s' to %s", proj, str(self))
            try:
                api, _, params, _ = api_def.get_all(application=self.key, project=proj)
                r = self.endpoint.post(api, params=params)
                ok = ok and r.ok
            except (ConnectionError, RequestException) as e:
                sutil.handle_error(e, f"adding project '{proj}' to {str(self)}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
                self.__class__.CACHE.pop(self)
                ok = False
        self._projects = None
        self.projects()
        return ok

    def last_analysis(self) -> datetime:
        """Returns the last analysis date of an app"""
        if self._last_analysis is None:
            self.refresh()
        if "analysisDate" in self.sq_json:
            self._last_analysis = sutil.string_to_date(self.sq_json["analysisDate"])
        return self._last_analysis

    def recompute(self) -> bool:
        """Triggers application recomputation, return whether the operation succeeded"""
        log.debug("Recomputing %s", str(self))
        api, _, params, _ = Api(self, op.RECOMPUTE).get_all(application=self.key)
        return self.post(api, params=params).ok

    def update(self, data: ObjectJsonRepr) -> None:
        """Updates an Application with data coming from a JSON (export)

        :param data: Data coming from a JSON (export)
        """
        log.info("Updating %s with %s", self, util.json_dump(data))
        visi = data.get("visibility", None)
        if visi in ("public", "private"):
            self.set_visibility(visi)
        elif visi is None:
            log.warning("%s visibility is not defined in JSON configuration file", self)
        else:
            log.warning("%s visibility to an invalid value in JSON configuration file, it must be 'public' or 'private'")
        if perms := data.get("permissions", None):
            log.info("Setting %s permissions with %s", self, perms)
            self.set_permissions(perms)

        self.add_projects(_project_list(data))
        self.set_tags(util.csv_to_list(data.get("tags", [])))

        appl_branches: list[AppBranchDef] = data.get("branches", [])
        main_branch_name = next((e["name"] for e in appl_branches if e.get("isMain", False)), None)
        main_branch_name is None or self.main_branch().rename(main_branch_name)

        for branch_data in appl_branches:
            self.set_branches(branch_data["name"], branch_data.get("projects", []))

    def api_params(self, operation: Optional[str] = None) -> ApiParams:
        """Returns the base params to be used for the object API"""
        ops = {op.GET: {"application": self.key}, op.RECOMPUTE: {"key": self.key}}
        return ops[operation] if operation and operation in ops else ops[op.GET]

    def __get_project_branches(self, branch_definition: ObjectJsonRepr) -> list[Union[projects.Project, branches.Branch]]:
        project_branches = []
        list_mode = isinstance(branch_definition, list)
        for proj in branch_definition:
            o_proj = projects.Project.get_object(self.endpoint, proj)
            if list_mode:
                proj_br = o_proj.main_branch().name
            else:
                proj_br = branch_definition[proj]
            project_branches.append(
                o_proj if proj_br == c.DEFAULT_BRANCH else branches.Branch.get_object(self.endpoint, project=o_proj, branch_name=proj_br)
            )
        return project_branches


def _project_list(data: ObjectJsonRepr) -> KeyList:
    """Returns the list of project keys of an application"""
    plist = []
    for b in [b for b in data.get("branches", []) if "projects" in b]:
        plist += [p["key"] for p in b["projects"]]
    return sorted(set(plist))


def count(endpoint: Platform) -> int:
    """returns count of applications

    :param endpoint: Reference to the SonarQube platform
    :return: Count of applications
    """
    check_supported(endpoint)
    api, _, params, _ = Api(Application, op.SEARCH, endpoint).get_all(ps=1, filter="qualifier = APP")
    return sutil.nbr_total_elements(json.loads(endpoint.get(api, params=params).text))


def check_supported(endpoint: Platform) -> None:
    """Verifies the edition and raise exception if not supported"""
    if endpoint.edition() == c.CE:
        raise exceptions.UnsupportedOperation(f"No applications in {endpoint.edition()} edition")
    if endpoint.edition() == c.SC:
        raise exceptions.UnsupportedOperation("No applications in SonarQube Cloud")


def export(endpoint: Platform, export_settings: ConfigSettings, **kwargs: Any) -> list[dict[str, Any]]:
    """Exports applications as JSON

    :param endpoint: Reference to the Sonar platform
    :param export_settings: Options to use for export
    :param key_regexp: Regexp to filter application keys to export, defaults to all if None
    :return: Dict of applications settings
    """
    check_supported(endpoint)
    write_q = kwargs.get("write_q", None)
    key_regexp = kwargs.get("key_list", ".+")

    app_list = {k: v for k, v in Application.get_list(endpoint).items() if not key_regexp or re.match(key_regexp, k)}
    apps_settings = []
    for k, app in app_list.items():
        app_json = app.export(export_settings)
        if write_q:
            write_q.put(app_json)
        else:
            apps_settings.append(app_json)
    write_q and write_q.put(sutil.WRITE_END)
    return apps_settings


def audit(endpoint: Platform, audit_settings: ConfigSettings, **kwargs: Any) -> list[problem.Problem]:
    """Audits applications and return list of problems found

    :param endpoint: Reference to the Sonar platform
    :param audit_settings: dict of audit config settings
    :param key_list: list of Application keys to audit, defaults to all if None
    :return: List of problems found
    """
    if endpoint.edition() == c.CE:
        return []
    if not audit_settings.get("audit.applications", True):
        log.debug("Auditing applications is disabled, skipping...")
        return []
    log.info("--- Auditing applications ---")
    problems = []
    key_regexp = kwargs.get("key_list", ".+")
    for obj in [o for o in Application.get_list(endpoint).values() if not key_regexp or re.match(key_regexp, o.key)]:
        problems += obj.audit(audit_settings, **kwargs)
    return problems


def import_config(endpoint: Platform, config_data: ObjectJsonRepr, key_list: Optional[KeyList] = None) -> bool:
    """Imports a list of application configuration in a SonarQube platform

    :param endpoint: Reference to the SonarQube platform
    :param config_data: JSON representation of applications configuration
    :param key_list: list of Application keys to import, defaults to all if None
    :return: Whether import succeeded
    """
    apps_data = config_data.get("applications", [])
    log.info("Importing %d applications", len(apps_data))
    if len(apps_data) == 0:
        return True
    if (ed := endpoint.edition()) not in (c.DE, c.EE, c.DCE):
        log.warning("Can't import applications in %s edition", ed)
        return False
    Application.search(endpoint=endpoint)
    to_recompute = []
    for key, data in util.list_to_dict(apps_data, "key").items():
        if key_list and key not in key_list:
            log.debug("App key '%s' not in selected apps", key)
            continue
        log.info("Importing application key '%s'", key)
        try:
            if Application.exists(endpoint, key=key):
                if not Application.has_access(endpoint, key=key):
                    Application.restore_access(endpoint, key=key)
                o = Application.get_object(endpoint, key)
            else:
                o = Application.create(endpoint, key, data["name"])
            o.update(data)
            to_recompute.append(o)
        except (exceptions.ObjectNotFound, exceptions.UnsupportedOperation) as e:
            log.error("%s configuration incomplete: %s", str(o), e.message)
    # Recompute apps after import to avoid race conditions
    for o in to_recompute:
        o.recompute()
    return True


def search_by_name(endpoint: Platform, name: str) -> dict[str, Application]:
    """Searches applications by name. Several apps may match as name does not have to be unique"""
    Application.get_list(endpoint=endpoint, use_cache=False)
    data = {}
    for app in Application.CACHE.values():
        if app.name == name:
            log.debug("Found APP %s id %x", app.key, id(app))
            data[app.key] = app
    # return {app.key: app for app in Application.CACHE.values() if app.name == name}
    return data


def convert_app_json(old_app_json: dict[str, Any]) -> dict[str, Any]:
    """Converts sonar-config old JSON report format to new format for a single application"""
    new_json = common_json_helper.convert_common_fields(old_app_json.copy())
    if "branches" not in new_json:
        return new_json
    for br, data in new_json["branches"].items():
        if "projects" not in data:
            continue
        new_json["branches"][br] = util.order_keys(data, "name", "isMain", "projects")
        new_json["branches"][br]["projects"] = util.dict_to_list(new_json["branches"][br]["projects"], "key", "branch")
        for proj_data in new_json["branches"][br]["projects"]:
            if proj_data.get("branch", None) in ("__default__", c.DEFAULT_BRANCH):
                proj_data.pop("branch")
    new_json["branches"] = util.sort_list_by_key(util.dict_to_list(new_json["branches"], "name"), "name", "isMain")
    return util.order_keys(new_json, "key", "name", "visibility", "tags", "branches", "permissions")


def convert_apps_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts sonar-config old JSON report format to new format"""
    new_json = old_json.copy()
    for k, v in new_json.items():
        new_json[k] = convert_app_json(v)
    return util.dict_to_list(new_json, "key")
