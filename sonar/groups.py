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


class Group(sq.SqObject):
    def __init__(self, id, name=None, endpoint=None, data=None):
        super().__init__(id, endpoint)
        self.name = name
        self._json = data
        if data is None:
            return
        if name is None:
            self.name = data["name"]
        self.members_count = data["membersCount"]
        self.is_default = data["default"]
        self.description = data.get("description", "")

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
            if self.description != "":
                json_data["description"] = self.description
            if self.is_default:
                json_data["default"] = True
        return util.remove_nones(json_data)


def search(params=None, endpoint=None):
    return sq.search_objects(
        api="user_groups/search",
        params=params,
        key_field="name",
        returned_field="groups",
        endpoint=endpoint,
        object_class=Group,
    )


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
