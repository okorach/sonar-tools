#!/usr/bin/env python3
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

from typing import Optional, Any, TYPE_CHECKING

from sonar.sqobject import SqObject
import sonar.logging as log
import sonar.util.misc as util
import sonar.utilities as sutil
from sonar import exceptions
from sonar import users
from sonar.util import cache, constants as c

from sonar.audit import rules
from sonar.audit.problem import Problem
import sonar.api.manager as api_mgr

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ObjectJsonRepr, ConfigSettings, KeyList

ADD_USER = "ADD_USER"
REMOVE_USER = "REMOVE_USER"
GROUPS_API = "v2/authorizations/groups"
MEMBERSHIP_API = "v2/authorizations/group-memberships"


class Group(SqObject):
    """
    Abstraction of the SonarQube "group" concept.
    Objects of this class must be created with one of the 3 available class methods. Don't use __init__
    """

    CACHE = cache.Cache()

    SEARCH_KEY_FIELD = "name"
    SEARCH_RETURN_FIELD = "groups"

    def __init__(self, endpoint: Platform, name: str, data: ApiPayload) -> None:
        """Do not use, use class methods to create objects"""
        super().__init__(endpoint=endpoint, key=name)
        self.name = name  #: Group name
        self.description = data.get("description", "")  #: Group description
        self.__members: Optional[list[users.User]] = None
        self.__is_default = data.get("default", None)
        self.id = data.get("id", None)  #: SonarQube 10.4+ Group id
        self.sq_json = data
        Group.CACHE.put(self)
        log.debug("Created %s object, id '%s'", str(self), str(self.id))

    @classmethod
    def read(cls, endpoint: Platform, name: str) -> Group:
        """Creates a Group object corresponding to the group with same name in SonarQube
        :param Platform endpoint: Reference to the SonarQube platform
        :param str name: Group name
        :raises ObjectNotFound: if group name not found
        :return: The group object
        """
        log.debug("Reading group '%s'", name)
        if o := Group.CACHE.get(name, endpoint.local_url):
            return o
        api_def = api_mgr.get_api_def("Group", c.LIST, endpoint.version())
        api, _, params = api_mgr.prep_params(api_def, q=name)
        ret = api_mgr.return_field(api_def)
        data = json.loads(endpoint.get(api, params=params).text)[ret]
        if not data or data == []:
            raise exceptions.ObjectNotFound(name, f"Group '{name}' not found")
        data = next((d for d in data if d["name"] == name), None)
        return cls(endpoint, name, data=data)

    @classmethod
    def create(cls, endpoint: Platform, name: str, description: Optional[str] = None) -> Group:
        """Creates a new group in SonarQube and returns the corresponding Group object

        :param endpoint: Reference to the SonarQube platform
        :param name: Group name
        :param description: Group description, optional
        :return: The group object
        """
        log.debug("Creating group '%s'", name)
        api_def = api_mgr.get_api_def("Group", c.CREATE, endpoint.version())
        params = util.remove_nones({"name": name, "description": description})
        endpoint.post(api_def["api"], params=params)
        return cls.read(endpoint=endpoint, name=name)

    @classmethod
    def load(cls, endpoint: Platform, data: ApiPayload) -> Group:
        """Creates a Group object from the result of a SonarQube API group search data

        :param Platform endpoint: Reference to the SonarQube platform
        :param data: The JSON data corresponding to the group
        :return: The group object
        """
        return cls(endpoint=endpoint, name=data["name"], data=data)

    @classmethod
    def get_object(cls, endpoint: Platform, name: str) -> Group:
        """Returns a group object

        :param endpoint: reference to the SonarQube platform
        :param name: group name
        :return: The group
        """
        if not Group.CACHE.get(name, endpoint.local_url):
            get_list(endpoint)
        if o := Group.CACHE.get(name, endpoint.local_url):
            return o
        raise exceptions.ObjectNotFound(name, message=f"Group '{name}' not found")

    def __str__(self) -> str:
        """String representation of the object"""
        return f"group '{self.name}'"

    def url(self) -> str:
        """Return the SonarQube permalink URL to the group, actually the global groups page only
        since this is as close as we can get to the precise group definition

        :return: the SonarQube permalink URL to the group
        """
        return f"{self.base_url(local=False)}/admin/groups"

    def update(self, name: Optional[str] = None, description: Optional[str] = None) -> bool:
        """Updates the group

        :param name: The new group name, optional
        :param description: The new group description, optional
        :return: Whether the operation succeeded
        """
        if not name and not description:
            log.debug("No name or description to update for %s", self)
            return False
        log.info("Updating %s with name = %s, description = %s", self, name, description)
        api_def = api_mgr.get_api_def("Group", c.UPDATE, self.endpoint.version())
        params = util.remove_nones({"currentName": self.name, "id": self.id, "name": name, "description": description})
        api, method, params = api_mgr.prep_params(api_def, **params)
        if method == "PATCH":
            ok = self.endpoint.patch(api, params=params).ok
        else:
            ok = self.endpoint.post(api, params=params).ok
        if ok:
            if name:
                self.name = name
            if description:
                self.description = description
        return ok

    def delete(self) -> bool:
        """Deletes an object, returns whether the operation succeeded"""
        log.info("Deleting %s", str(self))
        try:
            api_def = api_mgr.get_api_def(self.__class__.__name__, c.DELETE, self.endpoint.version())
            api, method, params = api_mgr.prep_params(api_def, id=self.id, name=self.name)
            if method == "DELETE":
                ok = self.endpoint.delete(api=api, params=params).ok
            else:
                ok = self.endpoint.post(api=api, params=params).ok
            if ok:
                log.info("Removing from %s cache", str(self.__class__.__name__))
                self.__class__.CACHE.pop(self)
        except exceptions.ObjectNotFound:
            self.__class__.CACHE.pop(self)
            raise
        return ok

    def set_description(self, description: str) -> bool:
        """Set a group description

        :param description: The new group description
        :return: Whether the new description was successfully set
        """
        return self.update(description=description)

    def set_name(self, name: str) -> bool:
        """Set a group name

        :param name: The new group name
        :return: Whether the new description was successfully set
        """
        return self.update(name=name)

    def api_params(self, op: str) -> ApiParams:
        """Return params used to search/create/delete for that object"""
        if self.endpoint.version() >= c.GROUP_API_V2_INTRO_VERSION:
            ops = {c.GET: {}}
        else:
            ops = {c.GET: {"name": self.name}}
        return ops[op] if op in ops else ops[c.GET]

    def is_default(self) -> bool:
        """
        :return: whether the group is a default group (sonar-users on SQS, Mambers on SQC) or not
        """
        return self.__is_default

    def members(self, use_cache: bool = True) -> list[users.User]:
        """Returns the group members"""
        if self.__members is None or not use_cache:
            api_def = api_mgr.get_api_def("Group", c.LIST_MEMBERS, self.endpoint.version())
            ret = api_mgr.return_field(api_def)
            # TODO: handle pagination
            api, _, params = api_mgr.prep_params(api_def, groupId=self.id, ps=500, pageSize=500, name=self.name)
            data = json.loads(self.endpoint.get(api, params=params).text)[ret]
            if self.endpoint.version() >= c.GROUP_API_V2_INTRO_VERSION:
                pname = "id"
                fname = "userId"
            else:
                pname = fname = "login"
            self.__members = [users.User.get_object(self.endpoint, **{pname: d[fname]}) for d in data]
        return self.__members

    def size(self) -> int:
        """Return the number of users in the group"""
        return len(self.members())

    def __get_membership_id(self, user: users.User) -> Optional[str]:
        """Return the membership of a user in the group

        :param user: the User to get the membership of
        :return: the membership id of the user in the group
        """
        if self.endpoint.version() < c.GROUP_API_V2_INTRO_VERSION:
            return None
        api_def = api_mgr.get_api_def("Group", c.LIST_MEMBERS, self.endpoint.version())
        api, _, params = api_mgr.prep_params(api_def, groupId=self.id, userId=user.id)
        ret = api_mgr.return_field(api_def)
        data = json.loads(self.endpoint.get(api, params=params).text)[ret]
        return next((m["id"] for m in data if m["groupId"] == self.id and m["userId"] == user.id), None)

    def add_user(self, user: users.User) -> bool:
        """Adds an user to the group

        :param user: the User to add
        :return: Whether the operation succeeded
        """
        log.info("Adding %s to %s", str(user), str(self))
        api_def = api_mgr.get_api_def("Group", c.ADD_MEMBER, self.endpoint.version())
        api, method, params = api_mgr.prep_params(api_def, groupId=self.id, userId=user.id, login=user.login, name=self.name)
        if method == "POST":
            return self.endpoint.post(api, params=params).ok
        else:
            return self.endpoint.patch(api, params=params).ok

    def remove_user(self, user: users.User) -> bool:
        """Removes a user from the group

        :param user: the User to remove
        :raises ObjectNotFound: if user not found in the group
        :return: Whether the operation succeeded
        """
        log.info("Removing %s from %s", user, self)
        if user not in self.members(use_cache=False):
            raise exceptions.ObjectNotFound(user.login or user.id, f"{user} not in {self}")
        api_def = api_mgr.get_api_def("Group", c.REMOVE_MEMBER, self.endpoint.version())
        mb_id = self.__get_membership_id(user)
        api, method, params = api_mgr.prep_params(api_def, id=mb_id, login=user.login, name=self.name)
        if self.endpoint.version() >= c.GROUP_API_V2_INTRO_VERSION and not mb_id:
            raise exceptions.ObjectNotFound(user.login, f"{self} or user id '{user.id}' not found")
        if method == "DELETE":
            return self.endpoint.delete(api=api, params=params).ok
        else:
            return self.endpoint.post(api=api, params=params).ok

    def audit(self, audit_settings: ConfigSettings = None) -> list[Problem]:
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

    def to_json(self, full_specs: bool = False) -> ObjectJsonRepr:
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


def search(endpoint: Platform, params: ApiParams = None) -> dict[str, Group]:
    """Search groups

    :params Platform endpoint: Reference to the SonarQube platform
    :return: dict of groups with group name as key
    """
    api_version = 1 if endpoint.version() < c.GROUP_API_V2_INTRO_VERSION else 2
    return Group.search_objects(endpoint=endpoint, params=params, api_version=api_version)


def get_list(endpoint: Platform) -> dict[str, Group]:
    """Returns the list of groups

    :params Platform endpoint: Reference to the SonarQube platform
    :return: The list of groups
    :rtype: dict
    """
    log.info("Listing groups")
    return dict(sorted(search(endpoint).items()))


def export(endpoint: Platform, export_settings: ConfigSettings, **kwargs) -> ObjectJsonRepr:
    """Exports groups representation in JSON

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings export_settings: Export parameters
    :rtype: ObjectJsonRepr
    """

    log.info("Exporting groups")
    g_list = []
    for g_name, g_obj in get_list(endpoint=endpoint).items():
        if not export_settings.get("FULL_EXPORT", False) and g_obj.is_default():
            continue
        g_list.append({"name": g_name, "description": g_obj.description or ""})
    log.info("%s groups to export", len(g_list))
    if write_q := kwargs.get("write_q", None):
        write_q.put(g_list)
        write_q.put(sutil.WRITE_END)
    return g_list


def audit(endpoint: Platform, audit_settings: ConfigSettings, **kwargs) -> list[Problem]:
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


def get_object_from_id(endpoint: Platform, id: str) -> Group:
    """Searches a Group object from its id - SonarQube 10.4+"""
    if endpoint.version() < c.GROUP_API_V2_INTRO_VERSION:
        raise exceptions.UnsupportedOperation("Operation unsupported before SonarQube 10.4")
    if len(Group.CACHE) == 0:
        get_list(endpoint)
    if gr := next((o for o in Group.CACHE.values() if o.id == id), None):
        return gr
    raise exceptions.ObjectNotFound(id, message=f"Group '{id}' not found")


def create_or_update(endpoint: Platform, name: str, description: str) -> Group:
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


def import_config(endpoint: Platform, config_data: ObjectJsonRepr, key_list: KeyList = None) -> None:
    """Imports a group configuration in SonarQube

    :param Platform endpoint: reference to the SonarQube platform
    :param dict config_data: the configuration to import
    :return: Nothing
    """
    if "groups" not in config_data:
        log.info("No groups to import")
        return
    log.info("Importing groups")
    converted_data = util.list_to_dict(config_data["groups"], "name")
    for name, data in converted_data.items():
        create_or_update(endpoint, name, data["description"])


def exists(endpoint: Platform, name: str) -> bool:
    """
    :param endpoint: reference to the SonarQube platform
    :param name: group name to check
    :return: whether the group exists
    """
    return Group.get_object(endpoint=endpoint, name=name) is not None


def convert_groups_json(old_json: dict[str, Any]) -> dict[str, Any]:
    """Converts sonar-config old groups JSON report format to new format"""
    return util.dict_to_list(old_json, "name", "description")
