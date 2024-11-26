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
Abstraction of the SonarQube "application" concept
"""

from __future__ import annotations
from typing import Union

import json
from datetime import datetime
from http import HTTPStatus
from threading import Lock
from requests import RequestException

import sonar.logging as log
import sonar.platform as pf
import sonar.util.constants as c
from sonar.util import types, cache

from sonar import exceptions, settings, projects, branches
from sonar.permissions import permissions, application_permissions
import sonar.sqobject as sq
import sonar.aggregations as aggr
import sonar.utilities as util
from sonar.audit import rules, problem

_CLASS_LOCK = Lock()
_IMPORTABLE_PROPERTIES = ("key", "name", "description", "visibility", "branches", "permissions", "tags")


class Application(aggr.Aggregation):
    """
    Abstraction of the SonarQube "application" concept
    """

    CACHE = cache.Cache()

    SEARCH_API = "components/search_projects"
    SEARCH_KEY_FIELD = "key"
    SEARCH_RETURN_FIELD = "components"
    API = {
        c.CREATE: "applications/create",
        c.GET: "applications/show",
        c.DELETE: "applications/delete",
        c.LIST: "components/search_projects",
        c.SET_TAGS: "applications/set_tags",
        c.GET_TAGS: "applications/show",
        "CREATE_BRANCH": "applications/create_branch",
        "UDPATE_BRANCH": "applications/update_branch",
    }

    def __init__(self, endpoint: pf.Platform, key: str, name: str) -> None:
        """Don't use this directly, go through the class methods to create Objects"""
        super().__init__(endpoint=endpoint, key=key)
        self._branches = None
        self._projects = None
        self._description = None
        self.name = name
        log.debug("Created object %s with uuid %d id %x", str(self), hash(self), id(self))
        Application.CACHE.put(self)

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
        o = Application.CACHE.get(key, endpoint.url)
        if o:
            return o
        try:
            data = json.loads(endpoint.get(Application.API[c.GET], params={"application": key}).text)["application"]
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"searching application {key}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
            raise exceptions.ObjectNotFound(key, f"Application key '{key}' not found")
        return cls.load(endpoint, data)

    @classmethod
    def load(cls, endpoint: pf.Platform, data: types.ApiPayload) -> Application:
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
        o = Application.CACHE.get(data["key"], endpoint.url)
        if not o:
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
            endpoint.post(Application.API["CREATE"], params={"key": key, "name": name})
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"creating application {key}", catch_http_statuses=(HTTPStatus.BAD_REQUEST,))
            raise exceptions.ObjectAlreadyExists(key, e.response.text)
        log.info("Creating object")
        return Application(endpoint=endpoint, key=key, name=name)

    def refresh(self) -> None:
        """Refreshes the by re-reading SonarQube

        :raises ObjectNotFound: If the Application does not exists anymore
        :return: self:
        :rtype: Appplication
        """
        try:
            self.reload(json.loads(self.get("navigation/component", params={"component": self.key}).text))
            self.reload(json.loads(self.get(Application.API[c.GET], params=self.api_params(c.GET)).text)["application"])
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"refreshing {str(self)}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
            Application.CACHE.pop(self)
            raise exceptions.ObjectNotFound(self.key, f"{str(self)} not found")

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
        if self.sq_json is None or "projects" not in self.sq_json:
            self.refresh()
        for p in self.sq_json["projects"]:
            # TODO: Support several branches of same project in the Application
            # TODO: Return projects in an application branch
            self._projects[p["key"]] = p["branch"]
        return self._projects

    def branch_exists(self, branch_name: str) -> bool:
        """
        :return: Whether the Application branch exists
        :rtype: bool
        """
        return branch_name in self.branches()

    def branch_is_main(self, branch: str) -> bool:
        """
        :return: Whether the Application branch is the main branch
        :rtype: bool
        """
        br = self.branches()
        return branch in br and br[branch].is_main()

    def set_branch(self, branch_name: str, branch_data: types.ObjectJsonRepr) -> Application:
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
            api = Application.API["CREATE_BRANCH"]
            if self.branch_exists(branch_name):
                api = Application.API["UPDATE_BRANCH"]
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
        if not self.sq_json or "branches" not in self.sq_json:
            self.refresh()
        self._branches = list_from(app=self, data=self.sq_json)
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
        ok = ok and sq.delete_object(self, "applications/delete", {"application": self.key}, Application.CACHE)
        if ok:
            Application.CACHE.pop(self)
        return ok

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

    def _audit_empty(self, audit_settings: types.ConfigSettings) -> list[problem.Problem]:
        """Audits if an application contains 0 projects"""
        if not audit_settings.get("audit.applications.empty", True):
            log.debug("Auditing empty applications is disabled, skipping...")
            return []
        return super()._audit_empty_aggregation(broken_rule=rules.RuleId.APPLICATION_EMPTY)

    def _audit_singleton(self, audit_settings: types.ConfigSettings) -> list[problem.Problem]:
        """Audits if an application contains a single project (makes littel sense)"""
        if not audit_settings.get("audit.applications.singleton", True):
            log.debug("Auditing singleton applications is disabled, skipping...")
            return []
        return super()._audit_singleton_aggregation(broken_rule=rules.RuleId.APPLICATION_SINGLETON)

    def audit(self, audit_settings: types.ConfigSettings, **kwargs) -> list[problem.Problem]:
        """Audits an application and returns list of problems found

        :param dict audit_settings: Audit configuration settings from sonar-audit properties config file
        :return: list of problems found
        :rtype: list [Problem]
        """
        log.info("Auditing %s", str(self))
        problems = (
            super().audit(audit_settings)
            + self._audit_empty(audit_settings)
            + self._audit_singleton(audit_settings)
            + self._audit_bg_task(audit_settings)
        )
        if "write_q" in kwargs:
            kwargs["write_q"].put(problems)
        return problems

    def export(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """Exports an application

        :param full: Whether to do a full export including settings that can't be set, defaults to False
        :type full: bool, optional
        """
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
        return util.filter_export(json_data, _IMPORTABLE_PROPERTIES, export_settings.get("FULL_EXPORT", False))

    def set_permissions(self, data: types.JsonPermissions) -> application_permissions.ApplicationPermissions:
        """Sets an application permissions

        :param dict data: dict of permission {"users": [<user1>, <user2>, ...], "groups": [<group1>, <group2>, ...]}
        :raises: ObjectNotFound if a user or a group does not exists
        :return: self
        """
        return self.permissions().set(data)

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
            except (ConnectionError, RequestException) as e:
                util.handle_error(e, f"adding project '{proj}' to {str(self)}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
                Application.CACHE.pop(self)
                ok = False
        return ok

    def last_analysis(self) -> datetime:
        """Returns the last analysis date of an app"""
        if self._last_analysis is None:
            self.refresh()
        if "analysisDate" in self.sq_json:
            self._last_analysis = util.string_to_date(self.sq_json["analysisDate"])
        return self._last_analysis

    def update(self, data: types.ObjectJsonRepr) -> None:
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
        self.set_tags(util.csv_to_list(data.get("tags", [])))
        for name, branch_data in data.get("branches", {}).items():
            self.set_branch(name, branch_data)

    def api_params(self, op: str = c.GET) -> types.ApiParams:
        ops = {c.GET: {"application": self.key}, c.SET_TAGS: {"application": self.key}, c.GET_TAGS: {"application": self.key}}
        return ops[op] if op in ops else ops[c.GET]

    def search_params(self) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        return self.api_params(c.GET)


def _project_list(data: types.ObjectJsonRepr) -> types.KeyList:
    """Returns the list of project keys of an application"""
    plist = {}
    for b in data.get("branches", {}).values():
        if "projects" not in b:
            continue
        if isinstance(b["projects"], dict):
            plist.update(b["projects"])
        else:
            plist.update({p["projectKey"]: "" for p in b["projects"]})
    return list(plist.keys())


def count(endpoint: pf.Platform) -> int:
    """returns count of applications

    :param pf.Platform endpoint: Reference to the SonarQube platform
    :return: Count of applications
    :rtype: int
    """
    check_supported(endpoint)
    return util.nbr_total_elements(json.loads(endpoint.get(Application.API[c.LIST], params={"ps": 1, "filter": "qualifier = APP"}).text))


def check_supported(endpoint: pf.Platform) -> None:
    """Verifies the edition and raise exception if not supported"""
    if endpoint.edition() not in ("developer", "enterprise", "datacenter"):
        errmsg = f"No applications in {endpoint.edition()} edition"
        log.warning(errmsg)
        raise exceptions.UnsupportedOperation(errmsg)


def search(endpoint: pf.Platform, params: types.ApiParams = None) -> dict[str, Application]:
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
    return sq.search_objects(endpoint=endpoint, object_class=Application, params=new_params)


def get_list(endpoint: pf.Platform, key_list: types.KeyList = None, use_cache: bool = True) -> dict[str, Application]:
    """
    :return: List of Applications (all of them if key_list is None or empty)
    :param Platform endpoint: Reference to the Sonar platform
    :param KeyList key_list: List of app keys to get, if None or empty all applications are returned
    :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :type use_cache: bool
    :rtype: dict{<branchName>: <Branch>}
    """
    with _CLASS_LOCK:
        if key_list is None or len(key_list) == 0 or not use_cache:
            log.info("Listing applications")
            return dict(sorted(search(endpoint=endpoint).items()))
        object_list = {key: Application.get_object(endpoint, key) for key in sorted(key_list)}
    return object_list


def exists(endpoint: pf.Platform, key: str) -> bool:
    """Tells whether a application with a given key exists"""
    try:
        Application.get_object(endpoint, key)
        return True
    except exceptions.ObjectNotFound:
        return False


def export(endpoint: pf.Platform, export_settings: types.ConfigSettings, **kwargs) -> types.ObjectJsonRepr:
    """Exports applications as JSON

    :param Platform endpoint: Reference to the Sonar platform
    :param ConfigSetting export_settings: Options to use for export
    :param KeyList key_list: list of Application keys to export, defaults to all if None
    :return: Dict of applications settings
    :rtype: ObjectJsonRepr
    """
    write_q = kwargs.get("write_q", None)
    key_list = kwargs.get("key_list", None)
    if endpoint.is_sonarcloud():
        # log.info("Applications do not exist in SonarCloud, export skipped")
        raise exceptions.UnsupportedOperation("Applications do not exist in SonarCloud, export skipped")

    apps_settings = {}
    for k, app in get_list(endpoint, key_list).items():
        app_json = app.export(export_settings)
        if write_q:
            write_q.put(app_json)
        else:
            app_json.pop("key")
            apps_settings[k] = app_json
    if write_q:
        write_q.put(util.WRITE_END)
    return apps_settings


def audit(endpoint: pf.Platform, audit_settings: types.ConfigSettings, **kwargs) -> list[problem.Problem]:
    """Audits applications and return list of problems found

    :param Platform endpoint: Reference to the Sonar platform
    :param dict audit_settings: dict of audit config settings
    :param KeyList key_list: list of Application keys to audit, defaults to all if None
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
    for obj in get_list(endpoint, key_list=kwargs.get("key_list", None)).values():
        problems += obj.audit(audit_settings, **kwargs)
    return problems


def import_config(endpoint: pf.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> bool:
    """Imports a list of application configuration in a SonarQube platform

    :param Platform endpoint: Reference to the SonarQube platform
    :param dict config_data: JSON representation of applications configuration
    :param KeyList key_list: list of Application keys to import, defaults to all if None
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
    for app in Application.CACHE.values():
        if app.name == name:
            log.debug("Found APP %s id %x", app.key, id(app))
            data[app.key] = app
    # return {app.key: app for app in Application.CACHE.values() if app.name == name}
    return data


def convert_for_yaml(original_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    new_json = util.dict_to_list(util.remove_nones(original_json), "key")
    for app_json in new_json:
        app_json["branches"] = util.dict_to_list(app_json["branches"], "name")
        for b in app_json["branches"]:
            if "projects" in b:
                b["projects"] = [{"key": k, "branch": br} for k, br in b["projects"].items()]
        if "permissions" in app_json:
            app_json["permissions"] = permissions.convert_for_yaml(app_json["permissions"])
    return new_json
