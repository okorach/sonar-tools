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
    def __init__(self, name, endpoint=None, data=None, create_data=None):
        super().__init__(name, endpoint)
        self.key = None
        self.name = name
        if create_data is not None:
            create_data["name"] = name
            self.post(_CREATE_API, params=create_data)
            data = search_by_name(endpoint, name)
        elif data is None:
            data = search_by_name(endpoint, name)
        self._json = data
        self.key = data["id"]
        self.name = data["name"]
        self.members_count = data["membersCount"]
        self.is_default = data["default"]
        self.description = data.get("description", None)
        _GROUPS[_uuid(self.name, self.key)] = self
        _MAP[self.name] = self.key
        if create_data is None:
            util.logger.debug("Sync'ed %s id '%s'", str(self), self.key)
        else:
            util.logger.debug("Created %s id '%s'", str(self), self.key)

    def __str__(self):
        return f"group '{self.name}'"

    def audit(self, settings=None):
        util.logger.debug("Auditing %s", str(self))
        problems = []
        if settings["audit.groups.empty"] and self.members_count == 0:
            rule = rules.get_rule(rules.RuleId.GROUP_EMPTY)
            problems.append(
                problem.Problem(
                    rule.type,
                    rule.severity,
                    rule.msg.format(str(self)),
                    concerned_object=self,
                )
            )
        return problems

    def to_json(self, full_specs=False):
        if full_specs:
            json_data = {self.name: self._json}
        else:
            json_data = {"name": self.name}
            if self.description is not None and self.description != "":
                json_data["description"] = self.description
            if self.is_default:
                json_data["default"] = True
        return util.remove_nones(json_data)

    def update(self, new_name=None, new_desc=None):
        if new_name is None and new_desc is None:
            return self
        upd = False
        params = {"id": self.key}
        if new_name != self.name:
            params["name"] = new_name
            upd = True
        if new_desc != self.description:
            params["description"] = new_name
            upd = True
        if not upd:
            util.logger.info("Nothing to update for %s", str(self))
            return self
        util.logger.info("Updating %s with %s", str(self), str(params))
        self.post(_UPDATE_API, params=params)
        if new_name is not None:
            _MAP.pop(_uuid(self.name, self.key), None)
            self.name = new_name
            _MAP[_uuid(self.name, self.key)] = self
        if new_desc is not None:
            self.description = new_desc
        return self


def search(endpoint, params=None):
    return sq.search_objects(
        api="user_groups/search",
        params=params,
        key_field="name",
        returned_field="groups",
        endpoint=endpoint,
        object_class=Group,
    )


def search_by_name(endpoint, name):
    return util.search_by_name(endpoint, name, _SEARCH_API, "groups")


def get_list(endpoint, params=None):
    util.logger.info("Listing groups")
    return search(params=params, endpoint=endpoint)


def export(endpoint, full_specs=False):
    util.logger.info("Exporting groups")
    g_list = {}
    for g_name, g_obj in search(endpoint=endpoint).items():
        g_list[g_name] = g_obj.to_json(full_specs=full_specs)
        g_list[g_name].pop("name")
    return g_list


def audit(audit_settings, endpoint=None):
    if not audit_settings["audit.groups"]:
        util.logger.info("Auditing groups is disabled, skipping...")
        return []
    util.logger.info("--- Auditing groups ---")
    problems = []
    for _, g in search(endpoint=endpoint).items():
        problems += g.audit(audit_settings)
    return problems

def get_object(name, endpoint=None):
    if len(_GROUPS) == 0:
        get_list(endpoint)
    if name not in _MAP:
        get_list(endpoint)
    if name not in _MAP:
        return None
    return _GROUPS[_uuid(name, _MAP[name])]


def update(name, endpoint=None, new_name=None, new_desc=None):
    util.logger.info("Update group '%s'", name)
    o = get_object(name=name, endpoint=endpoint)
    if o is None:
        return None
    return o.update(new_name, new_desc)


def create(name, endpoint=None, **kwargs):
    util.logger.info("Create group '%s'", name)
    o = get_object(name=name, endpoint=endpoint)
    if o is None:
        o = Group(name=name, endpoint=endpoint, create_data=kwargs)
    return o


def create_or_update(endpoint, name, **kwargs):
    o = get_object(endpoint=endpoint, name=name)
    if o is None:
        util.logger.debug("Group '%s' does not exist, creating...", name)
        return create(name, endpoint, **kwargs)
    else:
        return update(name, endpoint, new_name=name, new_desc=kwargs.get("desc", None))


def import_config(endpoint, config_data):
    if "groups" not in config_data:
        util.logger.info("No groups groups to import")
        return
    util.logger.info("Importing groups")
    for name, data in config_data["groups"].items():
        create_or_update(endpoint, name, desc=data.get("description"))


def _uuid(name, id):
    return id
