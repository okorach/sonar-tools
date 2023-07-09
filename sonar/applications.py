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

import json
from http import HTTPStatus
from threading import Lock
from requests.exceptions import HTTPError
from sonar import components, exceptions, settings
from sonar.projects import projects, branches
from sonar.permissions import permissions, application_permissions
import sonar.sqobject as sq
import sonar.aggregations as aggr
import sonar.utilities as util
from sonar.audit import rules

_OBJECTS = {}
_MAP = {}
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
_NOT_SUPPORTED = "Applications not supported in community edition"


class Application(aggr.Aggregation):
    """
    Abstraction of the SonarQube "application" concept
    """

    @classmethod
    def get_object(cls, endpoint, key):
        """Gets an Application object from SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application key not found in SonarQube
        :return: The found Application object
        :rtype: Application
        """
        if endpoint.edition() == "community":
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        if key in _OBJECTS:
            return _OBJECTS[key]
        try:
            data = json.loads(endpoint.get(APIS["get"], params={"application": key}).text)
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                raise exceptions.ObjectNotFound(key, f"Application '{key}' not found")
        return cls.load(endpoint, data)

    @classmethod
    def load(cls, endpoint, data):
        """Loads an Application object with data retrieved from SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :param dict data: Data coming from api/components/search_projects or api/applications/show
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectNotFound: If Application key not found in SonarQube
        :return: The found Application object
        :rtype: Application
        """
        if endpoint.edition() == "community":
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        o = _OBJECTS.get(data["key"], cls(endpoint, data["key"], data["name"]))
        o.reload(data)
        return o

    @classmethod
    def create(cls, endpoint, key, name):
        """Creates an Application object in SonarQube

        :param Platform endpoint: Reference to the SonarQube platform
        :param str key: Application key, must not already exist on SonarQube
        :param str name: Application name
        :raises UnsupportedOperation: If on a Community Edition
        :raises ObjectAlreadyExists: If key already exist for another Application
        :return: The created Application object
        :rtype: Application
        """
        if endpoint.edition() == "community":
            raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
        try:
            endpoint.post(APIS["create"], params={"key": key, "name": name})
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.BAD_REQUEST:
                raise exceptions.ObjectAlreadyExists(key, e.response.text)
        return Application(endpoint, key, name)

    def __init__(self, endpoint, key, name):
        """Don't use this directly, go through the class methods to create Objects"""
        super().__init__(key, endpoint)
        self._branches = None
        self._projects = None
        self._description = None
        self.name = name
        util.logger.debug("Created object %s", str(self))
        _OBJECTS[self.key] = self
        _MAP[self.name] = self.key

    def refresh(self):
        """Refreshes the by re-reading SonarQube

        :raises ObjectNotFound: If the Application does not exists anymore
        :return: self:
        :rtype: Appplication
        """
        try:
            return self.reload(json.loads(self.get(APIS["get"], params={"application": self.key}).text)["application"])
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.NOT_FOUND:
                _OBJECTS.pop(self.key, None)
                raise exceptions.ObjectNotFound(self.key, f"{str(self)} not found")
            raise

    def __str__(self):
        return f"application key '{self.key}'"

    def permissions(self):
        """
        :return: The application permissions
        :rtype: ApplicationPermissions
        """
        if self._permissions is None:
            self._permissions = application_permissions.ApplicationPermissions(self)
        return self._permissions

    def projects(self):
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

    def branch_exists(self, branch):
        """
        :return: Whether the Application branch exists
        :rtype: bool
        """
        return branch in self.branches()

    def branch_is_main(self, branch):
        """
        :return: Whether the Application branch is the main branch
        :rtype: bool
        """
        return branch in self.branches() and self._branches[branch]["isMain"]

    def set_branch(self, branch_name, branch_data):
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
                if bname == settings.DEFAULT_SETTING:
                    bname = o_proj.main_branch().name
                if not branches.exists(self.endpoint, bname, pkey):
                    ok = False
                    util.logger.warning("Branch '%s' of %s not found while setting application branch", bname, str(o_proj))
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

    def branches(self):
        """
        :return: the list of branches of the application and their definition
        :rtype: dict {<appBranch: {"projects": {<projectKey>: <projectBranch>, ...}}}
        """
        if self._branches is not None:
            return self._branches
        if "branches" not in self._json:
            self.refresh()
        params = {"application": self.key}
        self._branches = {}

        for br in self._json["branches"]:
            if not br["isMain"]:
                br.pop("isMain")
            b_name = br.pop("name")
            params["branch"] = b_name
            data = json.loads(self.get(APIS["get"], params=params).text)
            br["projects"] = {}
            for proj in data["application"]["projects"]:
                br["projects"][proj["key"]] = proj["branch"]
            self._branches[b_name] = br
        return self._branches

    def delete(self):
        """Deletes an Application

        :param params: Params for delete, typically None
        :type params: dict, optional
        :param exit_on_error: When to fail fast and exit if the HTTP status code is not 2XX, defaults to True
        :type exit_on_error: bool, optional
        :param mute: Tuple of HTTP Error codes to mute (ie not write an error log for), defaults to None.
        Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :type mute: tuple, optional
        :return: Whether the delete succeeded
        :rtype: bool
        """
        return sq.delete_object(self, "applications/delete", {"application": self.key}, _OBJECTS)

    def _audit_empty(self, audit_settings):
        """Audits if an application contains 0 projects"""
        if not audit_settings["audit.applications.empty"]:
            util.logger.debug("Auditing empty applications is disabled, skipping...")
            return []
        return super()._audit_empty_aggregation(broken_rule=rules.RuleId.APPLICATION_EMPTY)

    def _audit_singleton(self, audit_settings):
        """Audits if an application contains a single project (makes littel sense)"""
        if not audit_settings["audit.applications.singleton"]:
            util.logger.debug("Auditing singleton applications is disabled, skipping...")
            return []
        return super()._audit_singleton_aggregation(broken_rule=rules.RuleId.APPLICATION_SINGLETON)

    def audit(self, audit_settings):
        """Audits an application and returns list of problems found

        :param dict audit_settings: Audit configuration settings from sonar-audit properties config file
        :return: list of problems found
        :rtype: list [Problem]
        """
        util.logger.info("Auditing %s", str(self))
        return self._audit_empty(audit_settings) + self._audit_singleton(audit_settings) + self._audit_bg_task(audit_settings)

    def export(self, full=False):
        """Exports an application

        :param full: Whether to do a full export including settings that can't be set, defaults to False
        :type full: bool, optional
        """
        util.logger.info("Exporting %s", str(self))
        self.refresh()
        json_data = self._json.copy()
        json_data.update(
            {
                "key": self.key,
                "name": self.name,
                "description": None if self._description == "" else self._description,
                "visibility": self.visibility(),
                # 'projects': self.projects(),
                "branches": self.branches(),
                "permissions": self.permissions().export(),
                "tags": util.list_to_csv(self.tags(), separator=", "),
            }
        )
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))

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

    def add_projects(self, project_list):
        current_projects = self.projects().keys()
        ok = True
        for proj in project_list:
            if proj in current_projects:
                util.logger.debug("Won't add project '%s' to %s, it's already added", proj, str(self))
                continue
            util.logger.debug("Adding project '%s' to %s", proj, str(self))
            try:
                r = self.post("applications/add_project", params={"application": self.key, "project": proj})
                ok = ok and r.ok
            except HTTPError as e:
                if e.response.status_code == HTTPStatus.NOT_FOUND:
                    util.logger.warning("Project '%s' not found, can't be added to %s", proj, self)
                    ok = False
                else:
                    raise
        return ok

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
        """Return params used to search for that object

        :meta private:
        """
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


def count(endpoint):
    """returns count of applications

    :param Platform endpoint: Reference to the SonarQube platform
    :return: Count of applications
    :rtype: int
    """
    data = json.loads(endpoint.get(components.SEARCH_API, params={"ps": 1, "filter": "qualifier = APP"}).text)
    return data["paging"]["total"]


def search(endpoint, params=None):
    """Searches applications

    :param Platform endpoint: Reference to the SonarQube platform
    :param params: Search filters (see api/components/search parameters)
    :raises UnsupportedOperation: If on a community edition
    :return: dict of applications
    :rtype: dict {<appKey>: Application, ...}
    """
    if endpoint.edition() == "community":
        raise exceptions.UnsupportedOperation(_NOT_SUPPORTED)
    new_params = {"filter": "qualifier = APP"}
    if params is not None:
        new_params.update(params)
    return sq.search_objects(
        api=APIS["search"], params=new_params, returned_field="components", key_field="key", object_class=Application, endpoint=endpoint
    )


def get_list(endpoint, key_list=None, use_cache=True):
    """
    :return: List of Applications (all of them if key_list is None or empty)
    :param key_list: List of app keys to get, if None or empty all portfolios are returned
    :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :type use_cache: bool
    :rtype: dict{<branchName>: <Branch>}
    """
    with _CLASS_LOCK:
        if key_list is None or len(key_list) == 0 or not use_cache:
            util.logger.info("Listing applications")
            return search(endpoint=endpoint)
        object_list = {}
        for key in util.csv_to_list(key_list):
            object_list[key] = Application.get_object(endpoint, key)
    return object_list


def export(endpoint, key_list=None, full=False):
    """Exports applications as JSON

    :param Platform endpoint: Reference to the SonarQube platform
    :param key_list: list of Application keys to export, defaults to all if None
    :type key_list: list, optional
    :param full: Whether to export all attributes, including those that can't be set, defaults to False
    :type full: bool
    :return: Dict of applications settings
    :rtype: dict
    """
    apps_settings = {k: app.export(full) for k, app in get_list(endpoint, key_list).items()}
    for k in apps_settings:
        # remove key from JSON value, it's already the dict key
        apps_settings[k].pop("key")
    return apps_settings


def audit(audit_settings, endpoint=None, key_list=None):
    """Audits applications and return list of problems found

    :param Platform endpoint: Reference to the SonarQube platform
    :param dict audit_settings: dict of audit config settings
    :param key_list: list of Application keys to audit, defaults to all if None
    :type key_list: list, optional
    :return: List of problems found
    :rtype: list [Problem]
    """
    if endpoint.edition() == "community":
        return []
    if not audit_settings["audit.applications"]:
        util.logger.debug("Auditing applications is disabled, skipping...")
        return []
    util.logger.info("--- Auditing applications ---")
    problems = []
    for obj in get_list(endpoint, key_list=key_list).values():
        problems += obj.audit(audit_settings)
    return problems


def import_config(endpoint, config_data, key_list=None):
    """Imports a list of application configuration in a SonarQube platform

    :param Platform endpoint: Reference to the SonarQube platform
    :param dict config_data: JSON representation of applications configuration
    :param key_list: list of Application keys to import, defaults to all if None
    :type key_list: list, optional
    :return: Whether import succeeded
    :rtype: bool
    """
    if "applications" not in config_data:
        util.logger.info("No applications to import")
        return True
    if endpoint.edition() == "community":
        util.logger.warning("Can't import applications in a community edition")
        return False
    util.logger.info("Importing applications")
    search(endpoint=endpoint)
    new_key_list = util.csv_to_list(key_list)
    for key, data in config_data["applications"].items():
        if new_key_list and key not in new_key_list:
            continue
        util.logger.info("Importing application key '%s'", key)
        try:
            o = Application.get_object(endpoint, key)
        except exceptions.ObjectNotFound:
            o = Application.create(endpoint, key, data["name"])
        o.update(data)
    return True


def search_by_name(endpoint, name):
    return util.search_by_name(endpoint, name, components.SEARCH_API, "components", extra_params={"qualifiers": "APP"})
