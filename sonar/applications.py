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
from typing import Union

import json
from datetime import datetime
from http import HTTPStatus
from threading import Lock
from requests.exceptions import HTTPError

import sonar.logging as log
import sonar.platform as pf

from sonar import exceptions, settings, projects, branches
from sonar.permissions import permissions, application_permissions
import sonar.sqobject as sq
import sonar.aggregations as aggr
import sonar.utilities as util
from sonar.audit import rules, problem

_OBJECTS = {}
_CLASS_LOCK = Lock()

APIS = {
    "search": "api/components/search_projects",
    "get": "api/applications/show",
    "create": "api/applications/create",
    "delete": "api/applications/delete",
    "create_branch": "api/applications/create_branch",
    "update_branch": "api/applications/update_branch",
}

_IMPORTABLE_PROPERTIES = ("key", "name", "description", "visibility", "branches", "permissions", "tags")


class Application(aggr.Aggregation):
    """
    Abstraction of the SonarQube "application" concept
    """

    def __init__(self, endpoint: pf.Platform, key: str, name: str) -> None:
        """Don't use this directly, go through the class methods to create Objects"""
        super().__init__(endpoint=endpoint, key=key)
        self._branches = None
        self._projects = None
        self._description = None
        self.name = name
        log.debug("Created object %s with uuid %s id %x", str(self), self.uuid(), id(self))
        _OBJECTS[self.uuid()] = self

    @classmethod
    def get_object(cls, endpoint: pf.Platform, key: str) -> Application:
        """Gets an Application object from SonarQube

        :param pf.Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application key not found in SonarQube
        :return: The found Application object
        :rtype: Application
        """
        check_supported(endpoint)
        uu = sq.uuid(key=key, url=endpoint.url)
        if uu in _OBJECTS:
            return _OBJECTS[uu]
        try:
            data = json.loads(endpoint.get(APIS["get"], params={"application": key}).text)["application"]
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                raise exceptions.ObjectNotFound(key, f"Application key '{key}' not found")
        return cls.load(endpoint, data)

    @classmethod
    def load(cls, endpoint: pf.Platform, data: dict[str, str]) -> Application:
        """Loads an Application object with data retrieved from SonarQube

        :param pf.Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :param dict data: Data coming from api/components/search_projects or api/applications/show
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application key not found in SonarQube
        :return: The found Application object
        :rtype: Application
        """
        check_supported(endpoint)
        uu = sq.uuid(key=data["key"], url=endpoint.url)
        if uu in _OBJECTS:
            o = _OBJECTS[uu]
        else:
            o = cls(endpoint, data["key"], data["name"])
        o.reload(data)
        return o

    @classmethod
    def create(cls, endpoint: pf.Platform, key: str, name: str) -> Application:
        """Creates an Application object in SonarQube

        :param pf.Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :param str name: Application name
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectAlreadyExists: If key already exist for another Application
        :return: The created Application object
        :rtype: Application
        """
        check_supported(endpoint)
        try:
            endpoint.post(APIS["create"], params={"key": key, "name": name})
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.BAD_REQUEST:
                raise exceptions.ObjectAlreadyExists(key, e.response.text)
        return Application(endpoint, key, name)

    def refresh(self) -> None:
        """Refreshes the by re-reading SonarQube

        :raises ObjectNotFound: If the Application does not exists anymore
        :return: self:
        :rtype: Appplication
        """
        try:
            self.reload(json.loads(self.get("navigation/component", params={"component": self.key}).text))
            self.reload(json.loads(self.get(APIS["get"], params=self.search_params()).text)["application"])
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                _OBJECTS.pop(self.uuid(), None)
                raise exceptions.ObjectNotFound(self.key, f"{str(self)} not found")
            raise

    def __str__(self) -> str:
        """String name of object"""
        return f"application key '{self.key}'"

    def permissions(self) -> application_permissions.ApplicationPermissions:
        """
        :return: The application permissions
        :rtype: ApplicationPermissions
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
        if self._json is None or "projects" not in self._json:
            self.refresh()
        for p in self._json["projects"]:
            # TODO: Support several branches of same project in the Application
            # TODO: Return projects in an application branch
            self._projects[p["key"]] = p["branch"]
        return self._projects

    def branch_exists(self, branch_name: str) -> bool:
        """
        :return: Whether the Application branch exists
        :rtype: bool
        """
        return branch_name in [b.name for b in self.branches()]

    def branch_is_main(self, branch: str) -> bool:
        """
        :return: Whether the Application branch is the main branch
        :rtype: bool
        """
        return branch in self.branches() and self._branches[branch]["isMain"]

    def set_branch(self, branch_name: str, branch_data: dict[str, str]) -> Application:
        """Creates or updates an Application branch with a set of project branches

        :param str branch_name: The Application branch to set
        :param dict branch_data: in format returned by api/applications/show or {"projects": {<projectKey>: <branch>, ...}}
        :raises ObjectNotFound: if a project key does not exist or project branch does not exists
        :return: self:
        :rtype: Application
        """
        project_list, branch_list = [], []
        ok = True
        for p in branch_data.get("projects", []):
            (pkey, bname) = (p["projectKey"], p["branch"]) if isinstance(p, dict) else (p, branch_data["projects"][p])
            try:
                o_proj = projects.Project.get_object(self.endpoint, pkey)
                if bname == settings.DEFAULT_BRANCH:
                    bname = o_proj.main_branch().name
                if not branches.exists(self.endpoint, bname, pkey):
                    ok = False
                    log.warning("Branch '%s' of %s not found while setting application branch", bname, str(o_proj))
                else:
                    project_list.append(pkey)
                    branch_list.append(bname)
            except exceptions.ObjectNotFound:
                ok = False

        if len(project_list) > 0:
            params = {"application": self.key, "branch": branch_name, "project": project_list, "projectBranch": branch_list}
            api = APIS["create_branch"]
            if self.branch_exists(branch_name):
                api = APIS["update_branch"]
                params["name"] = params["branch"]
            ok = ok and self.post(api, params=params).ok
        return self

    def branches(self) -> dict[str, object]:
        """
        :return: the list of branches of the application and their definition
        :rtype: dict {<branchName>: <ApplicationBranch>}
        """
        from sonar.app_branches import list_from

        if self._branches is not None:
            return self._branches
        if not self._json or "branches" not in self._json:
            self.refresh()
        self._branches = list_from(app=self, data=self._json)
        return self._branches

    def delete(self) -> bool:
        """Deletes an Application and all its branches

        :return: Whether the delete succeeded
        :rtype: bool
        """
        ok = True
        if self.branches() is not None:
            for branch in self.branches().values():
                if not branch.is_main:
                    ok = ok and branch.delete()
        return ok and sq.delete_object(self, "applications/delete", {"application": self.key}, _OBJECTS)

    def get_filtered_branches(self, filters: dict[str, str]) -> Union[None, dict[str, object]]:
        """Get lists of branches according to the filter"""
        from sonar.app_branches import ApplicationBranch

        if not filters:
            return None
        f = filters.copy()
        br = f.pop("branch", None)
        if not br:
            return None
        objects = {}
        if br:
            if "*" in br:
                objects = self.branches()
            else:
                try:
                    for b in br:
                        objects[b] = ApplicationBranch.get_object(app=self, branch_name=b)
                except exceptions.ObjectNotFound as e:
                    log.error(e.message)
        return objects

    def get_hotspots(self, filters: dict[str, str] = None) -> dict[str, object]:
        my_branches = self.get_filtered_branches(filters)
        if my_branches is None:
            return super().get_hotspots(filters)
        findings_list = {}
        for comp in my_branches.values():
            if comp:
                findings_list = {**findings_list, **comp.get_hotspots()}
        return findings_list

    def get_issues(self, filters: dict[str, str] = None) -> dict[str, object]:
        my_branches = self.get_filtered_branches(filters)
        if my_branches is None:
            return super().get_issues(filters)
        findings_list = {}
        for comp in my_branches.values():
            if comp:
                findings_list = {**findings_list, **comp.get_issues()}
        return findings_list

    def _audit_empty(self, audit_settings: dict[str, str]) -> list[problem.Problem]:
        """Audits if an application contains 0 projects"""
        if not audit_settings.get("audit.applications.empty", True):
            log.debug("Auditing empty applications is disabled, skipping...")
            return []
        return super()._audit_empty_aggregation(broken_rule=rules.RuleId.APPLICATION_EMPTY)

    def _audit_singleton(self, audit_settings: dict[str, str]) -> list[problem.Problem]:
        """Audits if an application contains a single project (makes littel sense)"""
        if not audit_settings.get("audit.applications.singleton", True):
            log.debug("Auditing singleton applications is disabled, skipping...")
            return []
        return super()._audit_singleton_aggregation(broken_rule=rules.RuleId.APPLICATION_SINGLETON)

    def audit(self, audit_settings: dict[str, str]) -> list[problem.Problem]:
        """Audits an application and returns list of problems found

        :param dict audit_settings: Audit configuration settings from sonar-audit properties config file
        :return: list of problems found
        :rtype: list [Problem]
        """
        log.info("Auditing %s", str(self))
        return self._audit_empty(audit_settings) + self._audit_singleton(audit_settings) + self._audit_bg_task(audit_settings)

    def export(self, export_settings: dict[str, str]) -> dict[str, str]:
        """Exports an application

        :param full: Whether to do a full export including settings that can't be set, defaults to False
        :type full: bool, optional
        """
        log.info("Exporting %s", str(self))
        self.refresh()
        json_data = self._json.copy()
        json_data.update(
            {
                "key": self.key,
                "name": self.name,
                "description": None if self._description == "" else self._description,
                "visibility": self.visibility(),
                # 'projects': self.projects(),
                "branches": {br.name: br.export() for br in self.branches().values()},
                "permissions": self.permissions().export(export_settings=export_settings),
                "tags": util.list_to_csv(self.tags(), separator=", ", check_for_separator=True),
            }
        )
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, export_settings.get("FULL_EXPORT", False)))

    def set_permissions(self, data):
        """Sets an application permissions

        :param dict data: dict of permission {"users": [<user1>, <user2>, ...], "groups": [<group1>, <group2>, ...]}
        :raises: ObjectNotFound if a user or a group does not exists
        :return: self
        """
        return self.permissions().set(data)

    def set_tags(self, tags):
        if tags is None or len(tags) == 0:
            return
        if isinstance(tags, list):
            my_tags = util.list_to_csv(tags)
        else:
            my_tags = util.csv_normalize(tags)
        self.post("applications/set_tags", params={"application": self.key, "tags": my_tags})
        self._tags = util.csv_to_list(my_tags)

    def add_projects(self, project_list: list[str]) -> bool:
        """Add projects to an application"""
        current_projects = self.projects().keys()
        ok = True
        for proj in project_list:
            if proj in current_projects:
                log.debug("Won't add project '%s' to %s, it's already added", proj, str(self))
                continue
            log.debug("Adding project '%s' to %s", proj, str(self))
            try:
                r = self.post("applications/add_project", params={"application": self.key, "project": proj})
                ok = ok and r.ok
            except HTTPError as e:
                if e.response.status_code == HTTPStatus.NOT_FOUND:
                    log.warning("Project '%s' not found, can't be added to %s", proj, self)
                    ok = False
                else:
                    raise
        return ok

    def last_analysis(self) -> datetime:
        """Returns the last analysis date of an app"""
        if self._last_analysis is None:
            self.refresh()
        if "analysisDate" in self._json:
            self._last_analysis = util.string_to_date(self._json["analysisDate"])
        return self._last_analysis

    def update(self, data):
        """Updates an Application with data coming from a JSON (export)

        :param dict data:
        """
        if "permissions" in data:
            decoded_perms = {}
            for ptype in permissions.PERMISSION_TYPES:
                if ptype not in data["permissions"]:
                    continue
                decoded_perms[ptype] = {u: permissions.decode(v) for u, v in data["permissions"][ptype].items()}
            self.set_permissions(decoded_perms)
            # perms = {k: permissions.decode(v) for k, v in data.get("permissions", {}).items()}
            # self.set_permissions(util.csv_to_list(perms))
        self.add_projects(_project_list(data))
        self.set_tags(data.get("tags", None))
        for name, branch_data in data.get("branches", {}).items():
            self.set_branch(name, branch_data)

    def search_params(self):
        """Return params used to search/create/delete for that object"""
        return {"application": self.key}


def _project_list(data):
    plist = {}
    for b in data.get("branches", {}).values():
        if isinstance(b["projects"], dict):
            plist.update(b["projects"])
        else:
            for p in b["projects"]:
                plist[p["projectKey"]] = ""
    return plist.keys()


def count(endpoint: pf.Platform) -> int:
    """returns count of applications

    :param pf.Platform endpoint: Reference to the SonarQube platform
    :return: Count of applications
    :rtype: int
    """
    check_supported(endpoint)
    data = json.loads(endpoint.get(APIS["search"], params={"ps": 1, "filter": "qualifier = APP"}).text)
    return data["paging"]["total"]


def check_supported(endpoint: pf.Platform) -> None:
    """Verifies the edition and raise exception if not supported"""
    if endpoint.edition() not in ("developer", "enterprise", "datacenter"):
        errmsg = f"No applications in {endpoint.edition()} edition"
        log.warning(errmsg)
        raise exceptions.UnsupportedOperation(errmsg)


def search(endpoint: pf.Platform, params: dict[str, str] = None) -> dict[str, Application]:
    """Searches applications

    :param Platform endpoint: Reference to the SonarQube platform
    :param params: Search filters (see api/components/search parameters)
    :raises UnsupportedOperation: If on a community edition
    :return: dict of applications
    :rtype: dict {<appKey>: Application, ...}
    """
    check_supported(endpoint)
    new_params = {"filter": "qualifier = APP"}
    if params is not None:
        new_params.update(params)
    return sq.search_objects(
        api=APIS["search"], params=new_params, returned_field="components", key_field="key", object_class=Application, endpoint=endpoint
    )


def get_list(endpoint: pf.Platform, key_list: list[str] = None, use_cache: bool = True) -> dict[str, Application]:
    """
    :return: List of Applications (all of them if key_list is None or empty)
    :param Platform endpoint: Reference to the Sonar platform
    :param key_list: List of app keys to get, if None or empty all applications are returned
    :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :type use_cache: bool
    :rtype: dict{<branchName>: <Branch>}
    """
    with _CLASS_LOCK:
        if key_list is None or len(key_list) == 0 or not use_cache:
            log.info("Listing applications")
            return search(endpoint=endpoint)
        object_list = {}
        for key in util.csv_to_list(key_list):
            object_list[key] = Application.get_object(endpoint, key)
    return object_list


def exists(endpoint: pf.Platform, key: str) -> bool:
    """Tells whether a application with a given key exists"""
    try:
        Application.get_object(endpoint, key)
        return True
    except exceptions.ObjectNotFound:
        return False


def export(endpoint: pf.Platform, export_settings: dict[str, str], key_list: list[str] = None) -> dict[str, str]:
    """Exports applications as JSON

    :param Platform endpoint: Reference to the Sonar platform
    :param key_list: list of Application keys to export, defaults to all if None
    :type key_list: list, optional
    :param full: Whether to export all attributes, including those that can't be set, defaults to False
    :type full: bool
    :return: Dict of applications settings
    :rtype: dict
    """
    if endpoint.is_sonarcloud():
        # log.info("Applications do not exist in SonarCloud, export skipped")
        raise exceptions.UnsupportedOperation("Applications do not exist in SonarCloud, export skipped")

    apps_settings = {k: app.export(export_settings) for k, app in get_list(endpoint, key_list).items()}
    for k in apps_settings:
        # remove key from JSON value, it's already the dict key
        apps_settings[k].pop("key")
    return apps_settings


def audit(endpoint: pf.Platform, audit_settings: dict[str, str], key_list: list[str] = None) -> list[problem.Problem]:
    """Audits applications and return list of problems found

    :param Platform endpoint: Reference to the Sonar platform
    :param dict audit_settings: dict of audit config settings
    :param key_list: list of Application keys to audit, defaults to all if None
    :type key_list: list, optional
    :return: List of problems found
    :rtype: list [Problem]
    """
    if endpoint.edition() == "community":
        return []
    if not audit_settings.get("audit.applications", True):
        log.debug("Auditing applications is disabled, skipping...")
        return []
    log.info("--- Auditing applications ---")
    problems = []
    for obj in get_list(endpoint, key_list=key_list).values():
        problems += obj.audit(audit_settings)
    return problems


def import_config(endpoint: pf.Platform, config_data: dict[str, str], key_list: list[str] = None) -> bool:
    """Imports a list of application configuration in a SonarQube platform

    :param Platform endpoint: Reference to the SonarQube platform
    :param dict config_data: JSON representation of applications configuration
    :param key_list: list of Application keys to import, defaults to all if None
    :type key_list: list, optional
    :return: Whether import succeeded
    :rtype: bool
    """
    if "applications" not in config_data:
        log.info("No applications to import")
        return True
    if endpoint.edition() == "community":
        log.warning("Can't import applications in a community edition")
        return False
    log.info("Importing applications")
    search(endpoint=endpoint)
    new_key_list = util.csv_to_list(key_list)
    for key, data in config_data["applications"].items():
        if new_key_list and key not in new_key_list:
            continue
        log.info("Importing application key '%s'", key)
        try:
            o = Application.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            o = Application.create(endpoint, key, data["name"])
        o.update(data)
    return True


def search_by_name(endpoint: pf.Platform, name: str) -> dict[str, Application]:
    """Searches applications by name. Several apps may match as name does not have to be unique"""
    get_list(endpoint=endpoint, use_cache=False)
    data = {}
    for app in _OBJECTS.values():
        if app.name == name:
            log.debug("Found APP %s id %x", app.key, id(app))
            data[app.key] = app
    # return {app.key: app for app in _OBJECTS.values() if app.name == name}
    return data
