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

"""Abstraction of the SonarQube group concept"""
from __future__ import annotations
import json

from typing import Optional

from http import HTTPStatus
from requests import HTTPError, RequestException

import sonar.logging as log
import sonar.platform as pf
import sonar.sqobject as sq
import sonar.utilities as util
from sonar import exceptions, users

from sonar.audit import rules
from sonar.audit.problem import Problem
from sonar.util import types, cache, constants as c

SONAR_USERS = "sonar-users"
ADD_USER = "ADD_USER"
REMOVE_USER = "REMOVE_USER"
GROUPS_API = "v2/authorizations/groups"
MEMBERSHIP_API = "v2/authorizations/group-memberships"


class Group(sq.SqObject):
    """
    Abstraction of the SonarQube "group" concept.
    Objects of this class must be created with one of the 3 available class methods. Don't use __init__
    """

    CACHE = cache.Cache()

    API = {
        c.CREATE: GROUPS_API,
        c.UPDATE: GROUPS_API,
        c.DELETE: GROUPS_API,
        c.SEARCH: GROUPS_API,
        ADD_USER: MEMBERSHIP_API,
        REMOVE_USER: MEMBERSHIP_API,
    }
    API_V1 = {
        c.CREATE: "user_groups/create",
        c.UPDATE: "user_groups/update",
        c.DELETE: "user_groups/delete",
        c.SEARCH: "user_groups/search",
        ADD_USER: "user_groups/add_user",
        REMOVE_USER: "user_groups/remove_user",
    }
    SEARCH_KEY_FIELD = "name"
    SEARCH_RETURN_FIELD = "groups"

    def __init__(self, endpoint: pf.Platform, name: str, data: types.ApiPayload) -> None:
        """Do not use, use class methods to create objects"""
        super().__init__(endpoint=endpoint, key=name)
        self.name = name  #: Group name
        self.description = data.get("description", "")  #: Group description
        self.__members = None
        self.__is_default = data.get("default", None)
        self.id = data.get("id", None)  #: SonarQube 10.4+ Group id
        self.sq_json = data
        Group.CACHE.put(self)
        log.debug("Created %s object, id '%s'", str(self), str(self.id))

    @classmethod
    def read(cls, endpoint: pf.Platform, name: str) -> Group:
        """Creates a Group object corresponding to the group with same name in SonarQube
        :param Platform endpoint: Reference to the SonarQube platform
        :param str name: Group name
        :raises ObjectNotFound: if group name not found
        :return: The group object
        """
        log.debug("Reading group '%s'", name)
        o = Group.CACHE.get(name, endpoint.url)
        if o:
            return o
        data = util.search_by_name(endpoint, name, Group.api_for(c.SEARCH, endpoint), "groups")
        if data is None:
            raise exceptions.ObjectNotFound(name, f"Group '{name}' not found.")
        # SonarQube 10 compatibility: "id" field is dropped, use "name" instead
        o = Group.CACHE.get(data.get("id", data["name"]), endpoint.url)
        if o:
            return o
        return cls(endpoint, name, data=data)

    @classmethod
    def create(cls, endpoint: pf.Platform, name: str, description: str = None) -> Group:
        """Creates a new group in SonarQube and returns the corresponding Group object

        :param endpoint: Reference to the SonarQube platform
        :param name: Group name
        :param description: Group description, optional
        :return: The group object
        """
        log.debug("Creating group '%s'", name)
        try:
            data = json.loads(endpoint.post(Group.api_for(c.CREATE, endpoint), params={"name": name, "description": description}).text)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"creating group '{name}'", catch_http_errors=(HTTPStatus.BAD_REQUEST,))
            raise exceptions.ObjectAlreadyExists(name, util.sonar_error(e.response))
        o = cls.read(endpoint=endpoint, name=name)
        o.sq_json.update(data)
        return o

    @classmethod
    def load(cls, endpoint: pf.Platform, data: types.ApiPayload) -> Group:
        """Creates a Group object from the result of a SonarQube API group search data

        :param Platform endpoint: Reference to the SonarQube platform
        :param data: The JSON data corresponding to the group
        :return: The group object
        """
        return cls(endpoint=endpoint, name=data["name"], data=data)

    @classmethod
    def api_for(cls, op: str, endpoint: object) -> Optional[str]:
        """Returns the API for a given operation depending on the SonarQube version"""
        if endpoint.is_sonarcloud() or endpoint.version() < (10, 4, 0):
            api_to_use = Group.API_V1
        else:
            api_to_use = Group.API
        return api_to_use[op] if op in api_to_use else api_to_use[c.LIST]

    @classmethod
    def get_object(cls, endpoint: pf.Platform, name: str) -> Group:
        """Returns a group object

        :param Platform endpoint: reference to the SonarQube platform
        :param str name: group name
        :return: The group
        """
        o = Group.CACHE.get(name, endpoint.url)
        if not o:
            get_list(endpoint)
        o = Group.CACHE.get(name, endpoint.url)
        if not o:
            raise exceptions.ObjectNotFound(name, message=f"Group '{name}' not found")
        return o

    def delete(self) -> bool:
        """Deletes an object, returns whether the operation succeeded"""
        log.info("Deleting %s", str(self))
        try:
            if self.endpoint.version() >= (10, 4, 0):
                ok = self.endpoint.delete(api=f"{Group.API[c.DELETE]}/{self.id}").ok
            else:
                ok = self.post(api=Group.API_V1[c.DELETE], params=self.api_params(c.DELETE)).ok
            if ok:
                log.info("Removing from %s cache", str(self.__class__.__name__))
                self.__class__.CACHE.pop(self)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, f"deleting {str(self)}", catch_http_errors=(HTTPStatus.NOT_FOUND,))
            raise exceptions.ObjectNotFound(self.key, f"{str(self)} not found")
        return ok

    def api_params(self, op: str) -> types.ApiParams:
        """Return params used to search/create/delete for that object"""
        if self.endpoint.version() >= (10, 4, 0):
            ops = {c.GET: {}}
        else:
            ops = {c.GET: {"name": self.name}}
        return ops[op] if op in ops else ops[c.GET]

    def __str__(self) -> str:
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"group '{self.name}'"

    def is_default(self) -> bool:
        """
        :return: whether the group is a default group (sonar-users only for now) or not
        """
        return self.__is_default

    def members(self, use_cache: bool = True) -> list[users.User]:
        """Returns the group members"""
        if self.__members is None or not use_cache:
            if self.endpoint.version() >= (10, 4, 0):
                data = json.loads(self.get(MEMBERSHIP_API, params={"groupId": self.id}).text)
                self.__members = [users.User.get_object_by_id(self.endpoint, d["userId"]) for d in data["groupMemberships"]]
            else:
                data = self.endpoint.get_paginated("api/user_groups/users", return_field="users", params={"name": self.name})
                self.__members = [users.User.get_object(self.endpoint, d["login"]) for d in data["users"]]
        return self.__members

    def size(self) -> int:
        """
        :return: Number of users in the group
        """
        return len(self.members())

    def url(self) -> str:
        """
        :return: the SonarQube permalink URL to the group, actually the global groups page only
                 since this is as close as we can get to the precise group definition
        """
        return f"{self.endpoint.url}/admin/groups"

    def add_user(self, user: object) -> bool:
        """Adds an user to the group

        :param user: the User to add
        :return: Whether the operation succeeded
        """
        log.info("Adding %s to %s", str(user), str(self))
        try:
            if self.endpoint.version() >= (10, 4, 0):
                params = {"groupId": self.id, "userId": user.id}
            else:
                params = {"login": user.login, "name": self.name}
            r = self.post(Group.api_for(ADD_USER, self.endpoint), params=params)
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, "adding user to group")
            if isinstance(e, HTTPError):
                code = e.response.status_code
                if code == HTTPStatus.BAD_REQUEST:
                    raise exceptions.UnsupportedOperation(util.sonar_error(e.response))
                if code == HTTPStatus.NOT_FOUND:
                    raise exceptions.ObjectNotFound(user.login, util.sonar_error(e.response))
        return r.ok

    def remove_user(self, user: object) -> bool:
        """Removes a user from the group

        :param str user_login: User login
        :return: Whether the operation succeeded
        :rtype: bool
        """
        log.info("Removing %s from %s", str(user), str(self))
        try:
            if self.endpoint.version() >= (10, 4, 0):
                for m in json.loads(self.get(MEMBERSHIP_API, params={"userId": user.id}).text)["groupMemberships"]:
                    if m["groupId"] == self.id:
                        return self.endpoint.delete(f"{Group.api_for(REMOVE_USER, self.endpoint)}/{m['id']}").ok
                raise exceptions.ObjectNotFound(user.login, f"{str(self)} or user id '{user.id} not found")
            else:
                params = {"login": user.login, "name": self.name}
                return self.post(Group.api_for(REMOVE_USER, self.endpoint), params=params).ok
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, "removing user from group")
            if isinstance(e, HTTPError):
                code = e.response.status_code
                if code == HTTPStatus.BAD_REQUEST:
                    raise exceptions.UnsupportedOperation(util.sonar_error(e.response))
                if code == HTTPStatus.NOT_FOUND:
                    raise exceptions.ObjectNotFound(user.login, util.sonar_error(e.response))
        return False

    def audit(self, audit_settings: types.ConfigSettings = None) -> list[Problem]:
        """Audits a group and return list of problems found
        Current audit is limited to verifying that the group is not empty

        :param audit_settings: Options of what to audit and thresholds to raise problems, default to None
        :type audit_settings: dict, optional
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        log.debug("Auditing %s size %s", str(self), str(self.size()))
        problems = []
        if audit_settings.get("audit.groups.empty", True) and self.size() == 0:
            problems = [Problem(rules.get_rule(rules.RuleId.GROUP_EMPTY), self, str(self))]
        return problems

    def to_json(self, full_specs: bool = False) -> types.ObjectJsonRepr:
        """Returns the group properties (name, description, default) as dict

        :param full_specs: Also include properties that are not modifiable, default to False
        :type full_specs: bool, optional
        :return: Dict of the group
        :rtype: dict
        """
        if full_specs:
            json_data = self.sq_json.copy()
        else:
            json_data = {"name": self.name}
            json_data["description"] = self.description if self.description and self.description != "" else None
            if self.is_default():
                json_data["default"] = True
        return util.remove_nones(json_data)

    def set_description(self, description: str) -> bool:
        """Set a group description

        :param description: The new group description
        :return: Whether the new description was successfully set
        """
        if description is None or description == self.description:
            log.debug("No description to update for %s", str(self))
            return False
        log.debug("Updating %s with description = %s", str(self), description)
        if self.endpoint.version() >= (10, 4, 0):
            r = self.patch(f"{Group.API[c.UPDATE]}/{self.id}", params={"description": description})
        else:
            r = self.post(Group.API_V1[c.UPDATE], params={"currentName": self.key, "description": description})
        if r.ok:
            self.description = description
        return r.ok

    def set_name(self, name: str) -> bool:
        """Set a group name

        :param name: The new group name
        :return: Whether the new description was successfully set
        """
        if name is None or name == self.name:
            log.debug("No name to update for %s", str(self))
            return False
        log.debug("Updating %s with name = %s", str(self), name)
        if self.endpoint.version() >= (10, 4, 0):
            r = self.patch(f"{Group.API[c.UPDATE]}/{self.id}", params={"name": name})
        else:
            r = self.post(Group.API_V1[c.UPDATE], params={"currentName": self.key, "name": name})
        if r.ok:
            Group.CACHE.pop(self)
            self.name = name
            self.key = name
            Group.CACHE.put(self)
        return r.ok


def search(endpoint: pf.Platform, params: types.ApiParams = None) -> dict[str, Group]:
    """Search groups

    :params Platform endpoint: Reference to the SonarQube platform
    :return: dict of groups with group name as key
    """
    return sq.search_objects(endpoint=endpoint, object_class=Group, params=params, api_version=2)


def get_list(endpoint: pf.Platform) -> dict[str, Group]:
    """Returns the list of groups

    :params Platform endpoint: Reference to the SonarQube platform
    :return: The list of groups
    :rtype: dict
    """
    log.info("Listing groups")
    return dict(sorted(search(endpoint).items()))


def export(endpoint: pf.Platform, export_settings: types.ConfigSettings, **kwargs) -> types.ObjectJsonRepr:
    """Exports groups representation in JSON

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings export_settings: Export parameters
    :rtype: ObjectJsonRepr
    """

    log.info("Exporting groups")
    write_q = kwargs.get("write_q", None)
    g_list = {}
    for g_name, g_obj in get_list(endpoint=endpoint).items():
        if not export_settings.get("FULL_EXPORT", False) and g_obj.is_default():
            continue
        g_list[g_name] = "" if g_obj.description is None else g_obj.description
    log.info("%s groups to export", len(g_list))
    if write_q:
        write_q.put(g_list)
        write_q.put(util.WRITE_END)
    return g_list


def audit(endpoint: pf.Platform, audit_settings: types.ConfigSettings, **kwargs) -> list[Problem]:
    """Audits all groups

    :param dict audit_settings: Configuration of audit
    :param Platform endpoint: reference to the SonarQube platform
    :return: list of problems found
    :rtype: list[Problem]
    """
    if not audit_settings.get("audit.groups", True):
        log.info("Auditing groups is disabled, skipping...")
        return []
    log.info("--- Auditing groups ---")
    problems = []
    for g in search(endpoint=endpoint).values():
        problems += g.audit(audit_settings)
    if "write_q" in kwargs:
        kwargs["write_q"].put(problems)
    return problems


def get_object_from_id(endpoint: pf.Platform, id: str) -> Group:
    """Searches a Group object from its id - SonarQube 10.4+"""
    if endpoint.version() < (10, 4, 0):
        raise exceptions.UnsupportedOperation("Operation unsupported before SonarQube 10.4")
    if len(Group.CACHE) == 0:
        get_list(endpoint)
    for o in Group.CACHE.values():
        if o.id == id:
            return o
    raise exceptions.ObjectNotFound(id, message=f"Group '{id}' not found")


def create_or_update(endpoint: pf.Platform, name: str, description: str) -> Group:
    """Creates or updates a group

    :param Platform endpoint: reference to the SonarQube platform
    :param str name: group name
    :param str description: group description
    :return: The group
    :rtype: Group
    """
    try:
        o = Group.get_object(endpoint=endpoint, name=name)
        o.set_description(description)
        return o
    except exceptions.ObjectNotFound:
        log.debug("Group '%s' does not exist, creating...", name)
        return Group.create(endpoint, name, description)


def import_config(endpoint: pf.Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> None:
    """Imports a group configuration in SonarQube

    :param Platform endpoint: reference to the SonarQube platform
    :param dict config_data: the configuration to import
    :return: Nothing
    """
    if "groups" not in config_data:
        log.info("No groups to import")
        return
    log.info("Importing groups")
    for name, data in config_data["groups"].items():
        if isinstance(data, dict):
            desc = data["description"]
        else:
            desc = data
        create_or_update(endpoint, name, desc)


def exists(endpoint: pf.Platform, name: str) -> bool:
    """
    :param endpoint: reference to the SonarQube platform
    :param group_name: group name to check
    :return: whether the group exists
    """
    return Group.get_object(endpoint=endpoint, name=name) is not None


def convert_for_yaml(original_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    return util.dict_to_list(util.remove_nones(original_json), "name", "description")
