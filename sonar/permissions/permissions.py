#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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
from abc import ABC, abstractmethod
from sonar import utilities, options

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

    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.permissions = None
        self.read()

    def to_json(self, perm_type=None, csv=False):
        """
        :return: The permissions as dict
        :rtype: dict {"users": {<login>: [<perm>, <perm>, ...], ...}, "groups": {<name>: [<perm>, <perm>, ...], ...}}
        """
        if not csv:
            return self.permissions[perm_type] if is_valid(perm_type) else self.permissions
        perms = {}
        for p in normalize(perm_type):
            dperms = self.permissions.get(p, None)
            if dperms is not None and len(dperms) > 0:
                perms[p] = simplify(dperms)
        return perms if len(perms) > 0 else None
        # return {p: simplify(self.permissions.get(p, None)) for p in _normalize(perm_type) if self.permissions.get(p, None) is not None}

    def export(self):
        """
        :return: The permissions as dict
        :rtype: dict {"users": {<login>: [<perm>, <perm>, ...], ...}, "groups": {<name>: [<perm>, <perm>, ...], ...}}
        """
        return self.to_json(csv=True)

    @abstractmethod
    def __str__(self):
        pass

    @abstractmethod
    def read(self):
        """
        :return: The concerned object permissions
        :rtype: Permissions
        """

    @abstractmethod
    def set(self, new_perms):
        """Sets permissions of an object

        :param dict new_perms: The permissions as dict
        :rtype: self
        """

    def set_user_permissions(self, user_perms):
        """Sets user permissions of an object

        :param dict new_perms: The user permissions
        :rtype: self
        """
        self.set({"users": user_perms})

    def set_group_permissions(self, group_perms):
        self.set({"groups": group_perms})

    """
    @abstractmethod
    def remove_user_permissions(self, user_perms_dict):
        pass

    @abstractmethod
    def remove_group_permissions(self, group_perms_dict):
        pass


    def remove_permissions(self, perms_dict):
        self.remove_user_permissions(perms_dict.get("users", None))
        self.remove_group_permissions(perms_dict.get("groups", None))
    """

    def clear(self):
        """Clears all permissions of an object
        :return: self
        :rtype: Permissions
        """
        self.set({"users": {}, "groups": {}})

    def users(self):
        """
        :return: User permissions of an object
        :rtype: list (for QualityGate and QualityProfile) or dict (for other objects)
        """
        if self.permissions is None:
            self.read()
        return self.to_json(perm_type="users")

    def groups(self):
        """
        :return: Group permissions of an object
        :rtype: list (for QualityGate and QualityProfile) or dict (for other objects)
        """
        if self.permissions is None:
            self.read()
        return self.to_json(perm_type="groups")

    def added_permissions(self, other_perms):
        return diff(self.permissions, other_perms)

    def removed_permissions(self, other_perms):
        return diff(other_perms, self.permissions)

    def compare(self, other_perms):
        return {"added": diff(self.permissions, other_perms), "removed": diff(other_perms, self.permissions)}

    def black_list(self, disallowed_perms):
        """
        :meta private:
        """
        for p in PERMISSION_TYPES:
            for u, perms in self.permissions[p].items():
                self.permissions[p][u] = black_list(perms, disallowed_perms)

    def white_list(self, allowed_perms):
        """
        :meta private:
        """
        for p in PERMISSION_TYPES:
            for u, perms in self.permissions[p].items():
                self.permissions[p][u] = white_list(perms, allowed_perms)

    def _filter_permissions_for_edition(self, perms):
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
                utilities.logger.warning("Can't set permission '%s' on a %s edition", ENTERPRISE_GLOBAL_PERMISSIONS[p], ed)
                perms.remove(p)
        return perms

    def count(self, perm_type=None, perm_filter=None):
        """Counts number of permissions of an object

        :param perm_type: Optional "users" or "groups", both assumed if not specified.
        :type perm_type: str, optional
        :param perm_filter: Optional filter to count only specific types of permissions, defaults to None.
        :type perm_type: str, Optional
        :return: The number of permissions.
        :rtype: int
        """
        perms = PERMISSION_TYPES if perm_type is None else (perm_type)
        elem_counter, perm_counter = 0, 0
        for ptype in perms:
            for elem_perms in self.permissions.get(ptype, {}).values():
                elem_counter += 1
                if perm_filter is None:
                    continue
                for p in elem_perms:
                    if p in perm_filter:
                        perm_counter += 1
        return elem_counter if perm_filter is None else perm_counter

    def _get_api(self, api, perm_type, ret_field, **extra_params):
        perms = {}
        params = extra_params.copy()
        page, nbr_pages = 1, 1
        counter = 0
        while page <= nbr_pages:
            params["p"] = page
            resp = self.endpoint.get(api, params=params)
            if resp.ok:
                data = json.loads(resp.text)
                # perms.update({p[ret_field]: p["permissions"] for p in data[perm_type]})
                for p in data[perm_type]:
                    if len(p["permissions"]) > 0:
                        perms[p[ret_field]] = p["permissions"]
                        counter = 0
                    else:
                        counter += 1
            elif resp.status_code not in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
                # Hack: Different versions of SonarQube return different codes (400 or 404)
                utilities.exit_fatal(f"HTTP error {resp.status_code} - Exiting", options.ERR_SONAR_API)
            page, nbr_pages = page + 1, utilities.nbr_pages(data)
            if counter > 5 or not resp.ok:
                break
        return perms

    def _post_api(self, api, set_field, perms_dict, **extra_params):
        if perms_dict is None:
            return True
        result = False
        params = extra_params.copy()
        for u, perms in perms_dict.items():
            params[set_field] = u
            filtered_perms = self._filter_permissions_for_edition(perms)
            for p in filtered_perms:
                params["permission"] = p
                r = self.endpoint.post(api, params=params)
                result = result and r.ok
        return result


def simplify(perms_dict):
    if perms_dict is None or len(perms_dict) == 0:
        return None
    return {k: encode(v) for k, v in perms_dict.items() if len(v) > 0}


def encode(perms_array):
    """
    :meta private:
    """
    return utilities.list_to_csv(perms_array, ", ")


def decode(encoded_perms):
    """
    :meta private:
    """
    return utilities.csv_to_list(encoded_perms)


def is_valid(perm_type):
    """
    :param str perm_type:
    :return: Whether that permission type exists
    :rtype: bool
    """
    return perm_type and perm_type in PERMISSION_TYPES


def normalize(perm_type):
    """
    :meta private:
    """
    return (perm_type) if is_valid(perm_type) else PERMISSION_TYPES


def apply_api(endpoint, api, ufield, uvalue, ofield, ovalue, perm_list):
    """
    :meta private:
    """
    for p in perm_list:
        endpoint.post(api, params={ufield: uvalue, ofield: ovalue, "permission": p})


def diff_full(perms_1, perms_2):
    """
    :meta private:
    """
    diff_perms = perms_1.copy()
    for perm_type in ("users", "groups"):
        for elem, perms in perms_2:
            if elem not in perms_1:
                continue
            for p in perms:
                if p not in diff_perms[perm_type][elem]:
                    continue
                diff_perms[perm_type][elem].remove(p)
    return diff_perms


def diff(perms_1, perms_2):
    """
    :meta private:
    """
    diff_perms = perms_1.copy()
    for elem, perms in perms_2.items():
        if elem not in perms_1:
            continue
        for p in perms:
            if p not in diff_perms[elem]:
                continue
            diff_perms[elem].remove(p)
    return diff_perms


def diffarray(perms_1, perms_2):
    """
    :meta private:
    """
    diff_perms = perms_1.copy()
    for elem in perms_2:
        if elem in diff_perms:
            diff_perms.remove(elem)
    return diff_perms


def white_list(perms, allowed_perms):
    """
    :meta private:
    """
    return [p for p in perms if p in allowed_perms]


def black_list(perms, disallowed_perms):
    """
    :meta private:
    """
    return [p for p in perms if p not in disallowed_perms]
