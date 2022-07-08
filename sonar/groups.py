#
# sonar-tools
# Copyright (C) 2022 Olivier Korach
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

    Abstraction of the SonarQube "group" concept

"""
import sonar.sqobject as sq
import sonar.utilities as util

from sonar.audit import rules, problem

_SEARCH_API = "user_groups/search"
_CREATE_API = "user_groups/create"
_UPDATE_API = "user_groups/update"

_GROUPS = {}
_MAP = {}


class Group(sq.SqObject):
    @classmethod

    def read(cls, name, endpoint):
        """Reads a group from SonarQube, and create object

        :param name: Group name
        :type name: str
        :param endpoint: Reference to the SonarQube platform
        :type endpoint: Env
        :return: The group object
        :rtype: Group or None
        """
        util.logger.debug("Reading group '%s'", name)
        data = search_by_name(endpoint=endpoint, name=name)
        if data is None:
            return None
        key = data["id"]
        if key in _GROUPS:
            return _GROUPS[key]
        return cls(name, endpoint, data=data)

    @classmethod
    def create(cls, name, endpoint, description=None):
        """Creates a group in SonarQube

        :param name: Group name
        :type name: str
        :param endpoint: Reference to the SonarQube platform
        :type endpoint: Env
        :param description: Group description
        :type description: str
        :return: The group object
        :rtype: Group or None
        """
        util.logger.debug("Creating group '%s'", name)
        endpoint.post(_CREATE_API, params={"name": name, "description": description})
        return cls.read(name=name, endpoint=endpoint)

    @classmethod
    def load(cls, name, endpoint, data):
        """Reads a group from previously retrieved API call (JSON)

        :param name: Group name
        :type name: str
        :param endpoint: Reference to the SonarQube platform
        :type endpoint: Env
        :param data: The JSON data corresponding to the group
        :type data: dict
        :return: The group object
        :rtype: Group or None
        """
        util.logger.debug("Loading group '%s'", name)
        return cls(name=name, endpoint=endpoint, data=data)

    def __init__(self, name, endpoint, data):
        super().__init__(data["id"], endpoint)
        self.name = name
        self._json = data
        self.members_count = data.get("membersCount", None)
        self.is_default = data.get("default", None)
        self.description = data.get("description", "")
        _GROUPS[self.key] = self
        _MAP[self.name] = self.key
        util.logger.info("Created %s", str(self))

    def __str__(self):
        return f"group '{self.name}'"

    def url(self):
        """
        :return: the SonarQube permalink to the group
        :rtype: str
        """
        return f"{self.endpoint.url}/admin/groups"

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
        if audit_settings["audit.groups.empty"] and self.members_count == 0:
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
            if self.description is not None and self.description != "":
                json_data["description"] = self.description
            if self.is_default:
                json_data["default"] = True
        return util.remove_nones(json_data)

    def set_description(self, description):
        """Set a group description

        :param description: The new group description
        :type description: str
        :return: self
        :rtype: Group
        """
        if description is None or description == self.description:
            util.logger.debug("No description to update for %s", str(self))
            return self
        util.logger.debug("Updating %s with description = %s", str(self), description)
        self.post(_UPDATE_API, params={"id": self.key, "description": description})
        self.description = description
        return self

    def set_name(self, name):
        """Set a group name

        :param name: The new group name
        :type name: str
        :return: self
        :rtype: Group
        """
        if name is None or name == self.name:
            util.logger.debug("No name to update for %s", str(self))
            return self
        util.logger.debug("Updating %s with name = %s", str(self), name)
        self.post(_UPDATE_API, params={"id": self.key, "name": name})
        _MAP.pop(self.name, None)
        self.name = name
        _MAP[self.name] = self.key
        return self


def search(endpoint, params=None):
    """Search groups

    :params endpoint: Reference to the SonarQube platform
    :type endpoint: Env
    :param params: List of parameters to narrow down the search, defaults to None 
    :type params: dict, optional
    :return: dict of groups with group name as key
    :rtype: dict{name: Group}
    """
    return sq.search_objects(api=_SEARCH_API, params=params, key_field="name", returned_field="groups", endpoint=endpoint, object_class=Group)


def search_by_name(endpoint, name):
    """Search a group by its name

    :params endpoint: Reference to the SonarQube platform
    :type endpoint: Env
    :param name: The group name
    :type name: str
    :return: The group data as dict
    :rtype: dict
    """
    return util.search_by_name(endpoint, name, _SEARCH_API, "groups")


def get_list(endpoint, params=None):
    """Returns the list of groups

    :params endpoint: Reference to the SonarQube platform
    :type endpoint: Env
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
    :type endpoint: Env
    :return: list of groups
    :rtype: dict{name: description}
    """
    util.logger.info("Exporting groups")
    g_list = {}
    for g_name, g_obj in search(endpoint=endpoint).items():
        if g_obj.is_default:
            continue
        g_list[g_name] = "" if g_obj.description is None else g_obj.description
    return g_list


def audit(audit_settings, endpoint=None):
    """Audits all groups

    :param audit_settings: Configuration of audit
    :type audit_settings: dict
    :param endpoint: reference to the SonarQube platform
    :type endpoint: Env
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
    :type endpoint: Env
    :return: The group
    :rtype: Group
    """
    if len(_GROUPS) == 0 or name not in _MAP:
        get_list(endpoint)
    if name not in _MAP:
        return None
    return _GROUPS[_MAP[name]]


def create_or_update(endpoint, name, description):
    """Creates or updates a group

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Env
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
        return Group.create(name, endpoint, description)
    else:
        return o.set_description(description)


def import_config(endpoint, config_data):
    """Imports a group configuration in SonarQube

    :param endpoint: reference to the SonarQube platform
    :type endpoint: Env
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
    :type endpoint: Env
    :return: whether the project exists
    :rtype: bool
    """
    return get_object(name=group_name, endpoint=endpoint) is not None
