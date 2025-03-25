#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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

"""Abstract permissions class, parent of sub-objects permissions classes"""

from __future__ import annotations
from typing import Optional

import json
from abc import ABC, abstractmethod
from requests import RequestException

import sonar.logging as log
from sonar import utilities
from sonar.util import types
from sonar.audit.rules import get_rule, RuleId
from sonar.audit.problem import Problem

COMMUNITY_GLOBAL_PERMISSIONS = {
    "admin": "Administer System",
    "gateadmin": "Administer Quality Gates",
    "profileadmin": "Administer Quality Profiles",
    "provisioning": "Create Projects",
    "scan": "Execute Analysis",
}
DEVELOPER_GLOBAL_PERMISSIONS = {**COMMUNITY_GLOBAL_PERMISSIONS, **{"applicationcreator": "Create Applications"}}
ENTERPRISE_GLOBAL_PERMISSIONS = {**DEVELOPER_GLOBAL_PERMISSIONS, **{"portfoliocreator": "Create Portfolios"}}

PROJECT_PERMISSIONS = {
    "user": "Browse",
    "codeviewer": "See source code",
    "issueadmin": "Administer Issues",
    "securityhotspotadmin": "Create Projects",
    "scan": "Execute Analysis",
    "admin": "Administer Project",
}

_GLOBAL = 0
_PROJECTS = 1
_TEMPLATES = 2
_QG = 3
_QP = 4
_APPS = 5
_PORTFOLIOS = 6

OBJECTS_WITH_PERMISSIONS = (_GLOBAL, _PROJECTS, _TEMPLATES, _QG, _QP, _APPS, _PORTFOLIOS)
PERMISSION_TYPES = ("users", "groups")
NO_PERMISSIONS = {"users": None, "groups": None}

MAX_PERMS = 100


class Permissions(ABC):
    """
    Abstraction of sonar objects permissions
    """

    def __init__(self, concerned_object: object) -> None:
        self.concerned_object = concerned_object
        self.endpoint = concerned_object.endpoint
        self.permissions = None
        self.read()

    def __str__(self) -> str:
        return f"permissions of {str(self.concerned_object)}"

    def to_json(self, perm_type: str | None = None, csv: bool = False) -> types.JsonPermissions:
        """Converts a permission object to JSON"""
        if not csv:
            return self.permissions.get(perm_type, {}) if is_valid(perm_type) else self.permissions
        perms = {}
        for p in normalize(perm_type):
            if p not in self.permissions or len(self.permissions[p]) == 0:
                continue
            perms[p] = {k: encode(v) for k, v in self.permissions.get(p, {}).items()}
        return perms if len(perms) > 0 else None

    def export(self, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
        """Exports permissions as JSON"""
        inlined = export_settings.get("INLINE_LISTS", True)
        perms = self.to_json(csv=inlined)
        if not inlined:
            perms = {k: v for k, v in perms.items() if len(v) > 0}
        if not perms or len(perms) == 0:
            return None
        return perms

    @abstractmethod
    def read(self) -> Permissions:
        """
        :return: The concerned object permissions
        :rtype: Permissions
        """

    @abstractmethod
    def set(self, new_perms: types.JsonPermissions) -> Permissions:
        """Sets permissions of an object

        :param JsonPermissions new_perms: The permissions to set
        """

    def set_user_permissions(self, user_perms: dict[str, list[str]]) -> Permissions:
        """Sets user permissions of an object

        :param dict[str, list[str]] user_perms: The user permissions to apply
        """
        return self.set({"users": user_perms})

    def set_group_permissions(self, group_perms: dict[str, list[str]]) -> Permissions:
        """Sets user permissions of an object

        :param dict[str, list[str]] group_perms: The group permissions to apply
        """
        return self.set({"groups": group_perms})

    def clear(self) -> Permissions:
        """Clears all permissions of an object
        :return: self
        :rtype: Permissions
        """
        return self.set({"users": {}, "groups": {}})

    def users(self) -> dict[str, list[str]]:
        """
        :return: User permissions of an object
        :rtype: list (for QualityGate and QualityProfile) or dict (for other objects)
        """
        if self.permissions is None:
            self.read()
        return self.to_json(perm_type="users")

    def groups(self) -> dict[str, list[str]]:
        """
        :return: Group permissions of an object
        :rtype: list (for QualityGate and QualityProfile) or dict (for other objects)
        """
        if self.permissions is None:
            self.read()
        return self.to_json(perm_type="groups")

    def added_permissions(self, other_perms: types.JsonPermissions) -> types.JsonPermissions:
        return diff(self.permissions, other_perms)

    def removed_permissions(self, other_perms: types.JsonPermissions) -> types.JsonPermissions:
        return diff(other_perms, self.permissions)

    def compare(self, other_perms: types.JsonPermissions) -> dict[str, types.JsonPermissions]:
        return {"added": diff(self.permissions, other_perms), "removed": diff(other_perms, self.permissions)}

    def black_list(self, disallowed_perms: list[str]) -> None:
        """
        :meta private:
        """
        self.permissions = black_list(self.permissions, disallowed_perms)

    def white_list(self, allowed_perms: list[str]) -> None:
        """
        :meta private:
        """
        self.permissions = white_list(self.permissions, allowed_perms)

    def _filter_permissions_for_edition(self, perms: types.JsonPermissions) -> types.JsonPermissions:
        ed = self.endpoint.edition()
        allowed_perms = list(PROJECT_PERMISSIONS.keys())
        if ed == "community":
            allowed_perms += list(COMMUNITY_GLOBAL_PERMISSIONS.keys())
        elif ed == "developer":
            allowed_perms += list(DEVELOPER_GLOBAL_PERMISSIONS.keys())
        else:
            allowed_perms += list(ENTERPRISE_GLOBAL_PERMISSIONS.keys())
        for p in perms.copy():
            if p not in allowed_perms:
                log.warning("Can't set permission '%s' on a %s edition", p, ed)
                perms.remove(p)
        return perms

    def audit_nbr_permissions(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits that at least one permission is granted to a user or a group
        and that at least one group or user has admin permission on the object"""
        if self.count() == 0:
            return [Problem(get_rule(RuleId.OBJECT_WITH_NO_PERMISSIONS), self.concerned_object, str(self.concerned_object))]
        elif self.count(perm_filter=["admin"]) == 0:
            return [Problem(get_rule(RuleId.OBJECT_WITH_NO_ADMIN_PERMISSION), self.concerned_object, str(self.concerned_object))]
        return []

    def audit(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        return self.audit_nbr_permissions(audit_settings)

    def count(self, perm_type: Optional[str] = None, perm_filter: Optional[list[str]] = None) -> int:
        """Counts number of permissions of an object

        :param Optional[str] perm_type: Optional "users" or "groups", both assumed if not specified.
        :param Optional[list[str]] perm_filter: Optional filter to count only specific types of permissions, defaults to None.
        :return: The number of permissions.
        """
        perms = PERMISSION_TYPES if perm_type is None else (perm_type,)
        elem_counter, perm_counter = 0, 0
        for ptype in perms:
            for elem_perms in self.permissions.get(ptype, {}).values():
                elem_counter += 1
                if perm_filter is None:
                    continue
                perm_counter += len([1 for p in elem_perms if p in perm_filter])
        return elem_counter if perm_filter is None else perm_counter

    def _get_api(self, api: str, perm_type: str, ret_field: str, **extra_params) -> types.JsonPermissions:
        perms = {}
        params = extra_params.copy()
        page, nbr_pages = 1, 1
        counter = 0
        while page <= nbr_pages and counter <= 5:
            params["p"] = page
            try:
                resp = self.endpoint.get(api, params=params)
                data = json.loads(resp.text)
                # perms.update({p[ret_field]: p["permissions"] for p in data[perm_type]})
                for p in data[perm_type]:
                    if len(p["permissions"]) > 0:
                        perms[p[ret_field]] = p["permissions"]
                        counter = 0
                    else:
                        counter += 1
                page, nbr_pages = page + 1, utilities.nbr_pages(data)
            except (ConnectionError, RequestException) as e:
                utilities.handle_error(e, f"getting permissions of {str(self)}", catch_all=True)
                page += 1
        return perms

    def _post_api(self, api: str, set_field: str, perms_dict: types.JsonPermissions, **extra_params) -> bool:
        if perms_dict is None:
            return True
        result = False
        params = extra_params.copy()
        for u, perms in perms_dict.items():
            params[set_field] = u
            filtered_perms = self._filter_permissions_for_edition(perms)
            for p in filtered_perms:
                params["permission"] = p
                try:
                    r = self.endpoint.post(api, params=params)
                except (ConnectionError, RequestException) as e:
                    utilities.handle_error(e, f"setting permissions of {str(self)}", catch_all=True)
                result = result and r.ok
        return result


def simplify(perms_dict: dict[str, list[str]]) -> Optional[dict[str, str]]:
    """Simplifies permissions by converting to CSV an array"""
    if perms_dict is None or len(perms_dict) == 0:
        return None
    return {k: encode(v) for k, v in perms_dict.items() if len(v) > 0}


def encode(perms_array: dict[str, list[str]]) -> dict[str, str]:
    """
    :meta private:
    """
    return utilities.list_to_csv(perms_array, ", ", check_for_separator=True)


def decode(encoded_perms: dict[str, str]) -> dict[str, list[str]]:
    """
    :meta private:
    """
    return utilities.csv_to_list(encoded_perms)


def decode_full(encoded_perms: dict[str, str]) -> dict[str, list[str]]:
    """Decodes sonar-config encoded perms"""
    decoded_perms = {}
    for ptype in PERMISSION_TYPES:
        if ptype not in encoded_perms:
            continue
        decoded_perms[ptype] = {u: utilities.csv_to_list(v) for u, v in encoded_perms[ptype].items()}
    return decoded_perms


def is_valid(perm_type: str) -> bool:
    """
    :param str perm_type:
    :return: Whether that permission type exists
    :rtype: bool
    """
    return perm_type and perm_type in PERMISSION_TYPES


def normalize(perm_type: str | None) -> tuple[str]:
    """
    :meta private:
    """
    return (perm_type,) if is_valid(perm_type) else PERMISSION_TYPES


def apply_api(endpoint: object, api: str, ufield: str, uvalue: str, ofield: str, ovalue: str, perm_list: list[str]) -> None:
    """
    :meta private:
    """
    for p in perm_list:
        endpoint.post(api, params={ufield: uvalue, ofield: ovalue, "permission": p})


def diff_full(perms_1: types.JsonPermissions, perms_2: types.JsonPermissions) -> types.JsonPermissions:
    """
    :meta private:
    """
    diff_perms = perms_1.copy()
    for perm_type in PERMISSION_TYPES:
        for elem, perms in perms_2:
            if elem not in perms_1:
                continue
            for p in perms:
                if p not in diff_perms[perm_type][elem]:
                    continue
                diff_perms[perm_type][elem].remove(p)
    return diff_perms


def diff(perms_1: types.JsonPermissions, perms_2: types.JsonPermissions) -> types.JsonPermissions:
    """Performs the difference between two permissions dictionaries
    :meta private:
    """
    if not perms_1:
        return {}
    if not perms_2:
        return perms_1
    return {p: diffarray(perms_1[p], perms_2.get(p, [])) for p in perms_1}


def diffarray(perms_1: list[str], perms_2: list[str]) -> list[str]:
    """
    :meta private:
    """
    return list(set(perms_1) - set(perms_2))


def white_list(perms: types.JsonPermissions, allowed_perms: list[str]) -> types.JsonPermissions:
    """Returns permissions filtered from a white list of allowed permissions"""
    resulting_perms = {}
    for perm_type, sub_perms in perms.items():
        # if perm_type not in PERMISSION_TYPES:
        #    continue
        resulting_perms[perm_type] = {}
        for user_or_group, original_perms in sub_perms.items():
            resulting_perms[perm_type][user_or_group] = [p for p in original_perms if p in allowed_perms]
    return resulting_perms


def black_list(perms: types.JsonPermissions, disallowed_perms: list[str]) -> types.JsonPermissions:
    """Returns permissions filtered after a black list of disallowed permissions"""
    resulting_perms = {}
    for perm_type, sub_perms in perms.items():
        # if perm_type not in PERMISSION_TYPES:
        #    continue
        resulting_perms[perm_type] = {}
        for user_or_group, original_perms in sub_perms.items():
            resulting_perms[perm_type][user_or_group] = [p for p in original_perms if p not in disallowed_perms]
    return resulting_perms


def convert_for_yaml(json_perms: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Converts permissions in a format that is more friendly for YAML"""
    converted_perms = []
    for ptype in "groups", "users":
        if ptype in json_perms:
            converted_perms += utilities.dict_to_list(json_perms[ptype], ptype[:-1], "permissions")
    return converted_perms
