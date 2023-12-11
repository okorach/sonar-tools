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

import sonar.sqobject as sq
import sonar.utilities as util
from sonar import exceptions

from sonar.audit import rules, problem

SONAR_USERS = "sonar-users"

_SEARCH_API = "user_groups/search"
_CREATE_API = "user_groups/create"
_UPDATE_API = "user_groups/update"
ADD_USER_API = "user_groups/add_user"
REMOVE_USER_API = "user_groups/remove_user"

_OBJECTS = {}
_MAP = {}


class Group(sq.SqObject):
    """
    Abstraction of the SonarQube "group" concept.
    Objects of this class must be created with one of the 3 available class methods. Don't use __init__
    """

    def __init__(self, endpoint, name, data):
        """Do not use, use class methods to create objects"""
        super().__init__(data.get("id", name), endpoint)
        self.name = name  #: Group name
        self.description = data.get("description", "")  #: Group description
        self.__members_count = data.get("membersCount", None)
        self.__is_default = data.get("default", None)
        self._json = data
        _OBJECTS[self.key] = self
        _MAP[self.name] = self.key
        util.logger.debug("Created %s object", str(self))

    @classmethod
    def read(cls, endpoint, name):
        """Creates a Group object corresponding to the group with same name in SonarQube
        :param Platform endpoint: Reference to the SonarQube platform
        :type endpoint:
        :param str name: Group name
        :raises ObjectNotFound: if group name not found
        :return: The group object
        :rtype: Group or None if not found
        """
        util.logger.debug("Reading group '%s'", name)
        if name in _MAP:
            return _OBJECTS[_MAP[name]]
        data = util.search_by_name(endpoint, name, _SEARCH_API, "groups")
        if data is None:
            raise exceptions.UnsupportedOperation(f"Group '{name}' not found.")
        # SonarQube 10 compatibility: "id" field is dropped, use "name" instead
        key = data.get("id", data["name"])
        if key in _OBJECTS:
            return _OBJECTS[key]
        return cls(endpoint, name, data=data)

    @classmethod
    def create(cls, endpoint, name, description=None):
        """Creates a new group in SonarQube and returns the corresponding Group object

        :param endpoint: Reference to the SonarQube platform
        :type endpoint: Platform
        :param name: Group name
        :type name: str
        :param description: Group description
        :type description: str, optional
        :return: The group object
        :rtype: Group or None
        """
        util.logger.debug("Creating group '%s'", name)
        endpoint.post(_CREATE_API, params={"name": name, "description": description})
        return cls.read(endpoint=endpoint, name=name)

    @classmethod
    def load(cls, endpoint, data):
        """Creates a Group object from the result of a SonarQube API group search data

        :param endpoint: Reference to the SonarQube platform
        :type endpoint: Platform
        :param data: The JSON data corresponding to the group
        :type data: dict
        :return: The group object
        :rtype: Group or None
        """
        return cls(name=data["name"], endpoint=endpoint, data=data)

    def __str__(self):
        """
        :return: String formatting of the object
        :rtype: str
        """
        return f"group '{self.name}'"

    def is_default(self):
        """
        :return: whether the group is a default group (sonar-users only for now) or not
        :rtype: bool
        """
        return self.__is_default

    def size(self):
        """
        :return: Number of users members of the group
        :rtype: int
        """
        return self.__members_count

    def url(self):
        """
        :return: the SonarQube permalink URL to the group, actually the global groups page only
                 since this is as close as we can get to the precise group definition
        :rtype: str
        """
        return f"{self.endpoint.url}/admin/groups"

    def add_user(self, user_login):
        """Adds a user in the group

        :param user_login: User login
        :type user_login: str
        :return: Whether the operation succeeded
        :rtype: bool
        """
        return self.post(ADD_USER_API, params={"login": user_login, "name": self.name}).ok

    def remove_user(self, user_login):
        """Removes a user from the group

        :param user_login: User login
        :type user_login: str
        :return: Whether the operation succeeded
        :rtype: bool
        """
        return self.post(REMOVE_USER_API, params={"login": user_login, "name": self.name}).ok

    def audit(self, audit_settings=None):
        """Audits a group and return list of problems found
        Current audit is limited to verifying that the group is not empty

        :param audit_settings: Options of what to audit and thresholds to raise problems, default to None
        :type audit_settings: dict, optional
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        util.logger.debug("Auditing %s", str(self))
        problems = []
        if audit_settings["audit.groups.empty"] and self.__members_count == 0:
            rule = rules.get_rule(rules.RuleId.GROUP_EMPTY)
            problems = [problem.Problem(rule.type, rule.severity, rule.msg.format(str(self)), concerned_object=self)]
        return problems

    def to_json(self, full_specs=False):
        """Returns the group properties (name, description, default) as dict

        :param full_specs: Also include properties that are not modifiable, default to False
        :type full_specs: bool, optional
        :return: Dict of the group
        :rtype: dict
        """
        if full_specs:
            json_data = {self.name: self._json}
        else:
            json_data = {"name": self.name}
            json_data["description"] = self.description if self.description and self.description != "" else None
            if self.__is_default:
                json_data["default"] = True
        return util.remove_nones(json_data)

    def set_description(self, description):
        """Set a group description

        :param description: The new group description
        :type description: str
        :return: Whether the new description was successfully set
        :rtype: bool
        """
        if description is None or description == self.description:
            util.logger.debug("No description to update for %s", str(self))
            return True
        util.logger.debug("Updating %s with description = %s", str(self), description)
        r = self.post(_UPDATE_API, params={"id": self.key, "description": description})
        if r.ok:
            self.description = description
        return r.ok

    def set_name(self, name):
        """Set a group name

        :param name: The new group name
        :type name: str
        :return: Whether the new description was successfully set
        :rtype: bool
        """
        if name is None or name == self.name:
            util.logger.debug("No name to update for %s", str(self))
            return True
        util.logger.debug("Updating %s with name = %s", str(self), name)
        r = self.post(_UPDATE_API, params={"id": self.key, "name": name})
        if r.ok:
            _MAP.pop(self.name, None)
            self.name = name
            _MAP[self.name] = self.key
        return r.ok


def search(endpoint, params=None):
    """Search groups

    :params endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :param params: List of parameters to narrow down the search, defaults to None
    :type params: dict, optional
    :return: dict of groups with group name as key
    :rtype: dict{name: Group}
    """
    return sq.search_objects(api=_SEARCH_API, params=params, key_field="name", returned_field="groups", endpoint=endpoint, object_class=Group)


def get_list(endpoint, params=None):
    """Returns the list of groups

    :params endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :param params: The group name
    :type name: str
    :return: The group data as dict
    :rtype: dict
    """
    util.logger.info("Listing groups")
    return search(params=params, endpoint=endpoint)


def export(endpoint):
    """Exports all groups configuration as dict
    Default groups (sonar-users) are not exported

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :return: list of groups
    :rtype: dict{name: description}
    """
    util.logger.info("Exporting groups")
    g_list = {}
    for g_name, g_obj in search(endpoint=endpoint).items():
        if g_obj.is_default():
            continue
        g_list[g_name] = "" if g_obj.description is None else g_obj.description
    return g_list


def audit(audit_settings, endpoint=None):
    """Audits all groups

    :param audit_settings: Configuration of audit
    :type audit_settings: dict
    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :return: list of problems found
    :rtype: list[Problem]
    """
    if not audit_settings["audit.groups"]:
        util.logger.info("Auditing groups is disabled, skipping...")
        return []
    util.logger.info("--- Auditing groups ---")
    problems = []
    for _, g in search(endpoint=endpoint).items():
        problems += g.audit(audit_settings)
    return problems


def get_object(name, endpoint=None):
    """Returns a group object

    :param name: group name
    :type name: str
    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :return: The group
    :rtype: Group
    """
    if len(_OBJECTS) == 0 or name not in _MAP:
        get_list(endpoint)
    if name not in _MAP:
        return None
    return _OBJECTS[_MAP[name]]


def create_or_update(endpoint, name, description):
    """Creates or updates a group

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param name: group name
    :type name: str
    :param description: group description
    :type description: str
    :return: The group
    :rtype: Group
    """
    o = get_object(endpoint=endpoint, name=name)
    if o is None:
        util.logger.debug("Group '%s' does not exist, creating...", name)
        return Group.create(endpoint, name, description)
    else:
        return o.set_description(description)


def import_config(endpoint, config_data):
    """Imports a group configuration in SonarQube

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :param config_data: the configuration to import
    :type config_data: dict
    :return: Nothing
    """
    if "groups" not in config_data:
        util.logger.info("No groups groups to import")
        return
    util.logger.info("Importing groups")
    for name, data in config_data["groups"].items():
        if isinstance(data, dict):
            desc = data["description"]
        else:
            desc = data
        create_or_update(endpoint, name, desc)


def exists(group_name, endpoint):
    """
    :param group_name: group name to check
    :type group_name: str
    :param endpoint: reference to the SonarQube platform
    :type endpoint: Platform
    :return: whether the project exists
    :rtype: bool
    """
    return get_object(name=group_name, endpoint=endpoint) is not None
