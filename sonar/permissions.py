#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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

AGGREGATION_PERMISSIONS = {
    "user": "Browse",
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
MAX_QG_PERMS = 25


class Permissions(ABC):
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.permissions = None
        self.read()

    def to_json(self, perm_type=None, csv=False):
        if not csv:
            return self.permissions[perm_type] if _is_valid(perm_type) else self.permissions
        perms = {}
        for p in _normalize(perm_type):
            dperms = self.permissions.get(p, None)
            if dperms is not None and len(dperms) > 0:
                perms[p] = simplify(dperms)
        return perms if len(perms) > 0 else None
        # return {p: simplify(self.permissions.get(p, None)) for p in _normalize(perm_type) if self.permissions.get(p, None) is not None}

    def export(self):
        return self.to_json(csv=True)

    @abstractmethod
    def __str__(self):
        pass

    @abstractmethod
    def read(self, perm_type=None):
        pass

    @abstractmethod
    def set(self, new_perms):
        pass

    def set_user_permissions(self, user_perms):
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
        self.set({"users": {}, "groups": {}})

    def users(self):
        if self.permissions is None:
            self.read()
        return self.to_json(perm_type="users")

    def groups(self):
        if self.permissions is None:
            self.read()
        return self.to_json(perm_type="groups")

    def added_permissions(self, other_perms):
        return diff(self.permissions, other_perms)

    def removed_permissions(self, other_perms):
        return diff(other_perms, self.permissions)

    def compare(self, other_perms):
        return {"added": diff(self.permissions, other_perms), "removed": diff(other_perms, self.permissions)}

    def _remove_aggregations_creator(self):
        # Hack: SonarQube returns application/portfoliocreator even for objects that don't have this permission
        # so these perms needs to be removed manually
        for p in PERMISSION_TYPES:
            for u, perms in self.permissions[p].items():
                self.permissions[p][u] = _permission_filter(perms, ("applicationcreator", "portfoliocreator"), black_list=True)

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


class GlobalPermissions(Permissions):
    API_GET = {"users": "permissions/users", "groups": "permissions/groups"}
    API_SET = {"users": "permissions/add_user", "groups": "permissions/add_group"}
    API_REMOVE = {"users": "permissions/remove_user", "groups": "permissions/remove_group"}
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

    def __str__(self):
        return "global permissions"

    def read(self, perm_type=None):
        self.permissions = NO_PERMISSIONS
        for ptype in _normalize(perm_type):
            self.permissions[ptype] = self._get_api(GlobalPermissions.API_GET[ptype], ptype, GlobalPermissions.API_GET_FIELD[ptype], ps=MAX_PERMS)
        return self

    def set(self, new_perms):
        utilities.logger.debug("Setting %s to %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        ed = self.endpoint.edition()
        for perm_type in PERMISSION_TYPES:
            if new_perms is None or perm_type not in new_perms:
                continue
            decoded_perms = {k: decode(v) for k, v in new_perms[perm_type].items()}
            to_remove = diff(self.permissions[perm_type], decoded_perms)
            for p in to_remove.copy():
                if ed == "community" and p in ("portfoliocreator", "applicationcreator") or ed == "developer" and p == "portfoliocreator":
                    utilities.logger.warning("Can't remove permission '%s' on a %s edition", perm_type, ed)
                    to_remove.remove(p)
            self._post_api(GlobalPermissions.API_REMOVE[perm_type], GlobalPermissions.API_SET_FIELD[perm_type], to_remove)
            to_add = diff(decoded_perms, self.permissions[perm_type])
            for p in to_add.copy():
                if ed == "community" and p in ("portfoliocreator", "applicationcreator") or ed == "developer" and p == "portfoliocreator":
                    utilities.logger.warning("Can't add permission '%s' on a %s edition", perm_type, ed)
                    to_add.remove(p)
            self._post_api(GlobalPermissions.API_SET[perm_type], GlobalPermissions.API_SET_FIELD[perm_type], to_add)
        return self.read()


class TemplatePermissions(Permissions):
    API_GET = {"users": "permissions/template_users", "groups": "permissions/template_groups"}
    API_SET = {"users": "permissions/add_user_to_template", "groups": "permissions/add_group_to_template"}
    API_REMOVE = {"users": "permissions/remove_user_from_template", "groups": "permissions/remove_group_from_template"}
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

    def __init__(self, concerned_object):
        self.concerned_object = concerned_object
        super().__init__(concerned_object.endpoint)

    def __str__(self):
        return f"permissions of {str(self.concerned_object)}"

    def read(self, perm_type=None):
        self.permissions = NO_PERMISSIONS
        for p in _normalize(perm_type):
            self.permissions[p] = self._get_api(
                TemplatePermissions.API_GET[p],
                p,
                TemplatePermissions.API_GET_FIELD[p],
                templateId=self.concerned_object.key,
                ps=MAX_PERMS,
            )
        self._remove_aggregations_creator()
        return self

    def set(self, new_perms):
        utilities.logger.debug("Setting %s with %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        for p in PERMISSION_TYPES:
            if new_perms is None or p not in new_perms:
                continue
            decoded_perms = {k: decode(v) for k, v in new_perms[p].items()}
            to_remove = diff(self.permissions[p], decoded_perms)
            self._post_api(TemplatePermissions.API_REMOVE[p], TemplatePermissions.API_SET_FIELD[p], to_remove, templateId=self.concerned_object.key)
            to_add = diff(decoded_perms, self.permissions[p])
            self._post_api(TemplatePermissions.API_SET[p], TemplatePermissions.API_SET_FIELD[p], to_add, templateId=self.concerned_object.key)
        return self.read()


class QualityGatePermissions(Permissions):
    API_GET = {"users": "qualitygates/search_users", "groups": "qualitygates/search_groups"}
    API_SET = {"users": "qualitygates/add_user", "groups": "qualitygates/add_group"}
    API_REMOVE = {"users": "qualitygates/remove_user", "groups": "qualitygates/remove_group"}
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

    def __init__(self, concerned_object):
        self.concerned_object = concerned_object
        super().__init__(concerned_object.endpoint)

    def __str__(self):
        return f"permissions of {str(self.concerned_object)}"

    def _post_api(self, api, set_field, perms_dict, **extra_params):
        if perms_dict is None:
            return True
        result = False
        params = extra_params.copy()
        for u in perms_dict:
            params[set_field] = u
            r = self.endpoint.post(api, params=params)
            result = result and r.ok
        return result

    def read(self, perm_type=None):
        self.permissions = {p: [] for p in PERMISSION_TYPES}
        if self.concerned_object.is_built_in:
            utilities.logger.debug("Won't read %s because it's built-in", str(self))
            return self
        if self.endpoint.version() < (9, 2, 0):
            utilities.logger.debug("Won't read %s on SonarQube < 9.2", str(self))
            return self
        for p in _normalize(perm_type):
            self.permissions[p] = self._get_api(
                QualityGatePermissions.API_GET[p], p, QualityGatePermissions.API_GET_FIELD[p], gateName=self.concerned_object.name
            )
        return self

    def set(self, new_perms):
        if self.concerned_object.is_built_in:
            utilities.logger.debug("Can't set %s because it's built-in", str(self))
            self.permissions = {p: [] for p in PERMISSION_TYPES}
            return self
        if self.endpoint.version() < (9, 2, 0):
            utilities.logger.debug("Can set %s on SonarQube < 9.2", str(self))
            self.permissions = {p: [] for p in PERMISSION_TYPES}
            return self
        utilities.logger.debug("Setting %s with %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        for p in PERMISSION_TYPES:
            if new_perms is None or p not in new_perms:
                continue
            decoded_perms = decode(new_perms[p])
            to_remove = diffarray(self.permissions[p], decoded_perms)
            self._post_api(
                QualityGatePermissions.API_REMOVE[p], QualityGatePermissions.API_SET_FIELD[p], to_remove, gateName=self.concerned_object.name
            )
            to_add = diffarray(decoded_perms, self.permissions[p])
            self._post_api(QualityGatePermissions.API_SET[p], QualityGatePermissions.API_SET_FIELD[p], to_add, gateName=self.concerned_object.name)
        return self.read()

    def to_json(self, perm_type=None, csv=False):
        if not csv:
            return self.permissions[perm_type] if _is_valid(perm_type) else self.permissions
        perms = {}
        for p in _normalize(perm_type):
            dperms = self.permissions.get(p, None)
            if dperms is not None and len(dperms) > 0:
                perms[p] = encode(self.permissions.get(p, None))
        return perms if len(perms) > 0 else None

    def _get_api(self, api, perm_type, ret_field, **extra_params):
        perms = []
        params = extra_params.copy()
        params["ps"] = MAX_QG_PERMS
        page, nbr_pages = 1, 1
        while page <= nbr_pages:
            params["p"] = page
            resp = self.endpoint.get(api, params=params)
            if resp.ok:
                data = json.loads(resp.text)
                perms += [p[ret_field] for p in data[perm_type]]
            elif resp.status_code not in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
                # Hack: Different versions of SonarQube return different codes (400 or 404)
                utilities.exit_fatal(f"HTTP error {resp.status_code} - Exiting", options.ERR_SONAR_API)
            else:
                break
            page, nbr_pages = page + 1, utilities.nbr_pages(data)
        return perms


class QualityProfilePermissions(Permissions):
    API_GET = {"users": "qualityprofiles/search_users", "groups": "qualityprofiles/search_groups"}
    API_SET = {"users": "qualityprofiles/add_user", "groups": "qualityprofiles/add_group"}
    API_REMOVE = {"users": "qualityprofiles/remove_user", "groups": "qualityprofiles/remove_group"}
    API_GET_ID = "qualityProfile"
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "group"}

    def __init__(self, concerned_object):
        self.concerned_object = concerned_object
        super().__init__(concerned_object.endpoint)

    def __str__(self):
        return f"permissions of {str(self.concerned_object)}"

    def _get_api(self, api, perm_type, ret_field, **extra_params):
        perms = []
        params = extra_params.copy()
        params["ps"] = MAX_QG_PERMS
        page, nbr_pages = 1, 1
        while page <= nbr_pages:
            params["p"] = page
            resp = self.endpoint.get(api, params=params)
            if resp.ok:
                data = json.loads(resp.text)
                perms += [p[ret_field] for p in data[perm_type]]
            elif resp.status_code not in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
                # Hack: Different versions of SonarQube return different codes (400 or 404)
                utilities.exit_fatal(f"HTTP error {resp.status_code} - Exiting", options.ERR_SONAR_API)
            else:
                break
            page, nbr_pages = page + 1, utilities.nbr_pages(data)
        return perms

    def _post_api(self, api, set_field, perms_dict, **extra_params):
        if perms_dict is None:
            return True
        result = False
        params = extra_params.copy()
        for u in perms_dict:
            params[set_field] = u
            r = self.endpoint.post(api, params=params)
            result = result and r.ok
        return result

    def read(self, perm_type=None):
        self.permissions = {p: [] for p in PERMISSION_TYPES}
        if self.concerned_object.is_built_in:
            utilities.logger.debug("Won't read %s since it is built-in", str(self))
            return self
        if self.endpoint.version() < (6, 6, 0):
            utilities.logger.debug("Won't read %s on SonarQube < 6.6", str(self))
            return self
        for p in _normalize(perm_type):
            self.permissions[p] = self._get_api(
                QualityProfilePermissions.API_GET[p],
                p,
                QualityProfilePermissions.API_GET_FIELD[p],
                qualityProfile=self.concerned_object.name,
                language=self.concerned_object.language,
            )
        return self

    def set(self, new_perms):
        if self.concerned_object.is_built_in:
            utilities.logger.debug("Can set %s because it's built-in", str(self))
            return self
        if self.endpoint.version() < (6, 6, 0):
            utilities.logger.debug("Can set %s on SonarQube < 6.6", str(self))
            return self
        utilities.logger.debug("Setting %s with %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        for p in PERMISSION_TYPES:
            if new_perms is None or p not in new_perms:
                continue
            decoded_perms = decode(new_perms[p])
            to_remove = diffarray(self.permissions[p], decoded_perms)
            self._post_api(
                QualityProfilePermissions.API_REMOVE[p],
                QualityProfilePermissions.API_SET_FIELD[p],
                to_remove,
                qualityProfile=self.concerned_object.name,
                language=self.concerned_object.language,
            )
            to_add = diffarray(decoded_perms, self.permissions[p])
            return self._post_api(
                QualityProfilePermissions.API_SET[p],
                QualityProfilePermissions.API_SET_FIELD[p],
                to_add,
                qualityProfile=self.concerned_object.name,
                language=self.concerned_object.language,
            )
        return self.read()

    def to_json(self, perm_type=None, csv=False):
        if not csv:
            return self.permissions[perm_type] if _is_valid(perm_type) else self.permissions
        perms = {p: utilities.list_to_csv(self.permissions.get(p, None), ", ") for p in _normalize(perm_type) if len(self.permissions.get(p, {})) > 0}
        return perms if len(perms) > 0 else None


class ProjectPermissions(Permissions):
    API_GET = {"users": "permissions/users", "groups": "permissions/groups"}
    API_SET = {"users": "permissions/add_user", "groups": "permissions/add_group"}
    API_REMOVE = {"users": "permissions/remove_user", "groups": "permissions/remove_group"}
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

    def __init__(self, concerned_object):
        self.concerned_object = concerned_object
        super().__init__(concerned_object.endpoint)

    def __str__(self):
        return f"permissions of {str(self.concerned_object)}"

    def read(self, perm_type=None):
        self.permissions = NO_PERMISSIONS
        for p in _normalize(perm_type):
            self.permissions[p] = self._get_api(
                ProjectPermissions.API_GET[p], p, ProjectPermissions.API_GET_FIELD[p], projectKey=self.concerned_object.key, ps=MAX_PERMS
            )
        self._remove_aggregations_creator()
        return self

    def set(self, new_perms):
        utilities.logger.debug("Setting %s with %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        for p in PERMISSION_TYPES:
            if new_perms is None or p not in new_perms:
                continue
            decoded_perms = {k: decode(v) for k, v in new_perms[p].items()}
            to_remove = diff(self.permissions[p], decoded_perms)
            self._post_api(ProjectPermissions.API_REMOVE[p], ProjectPermissions.API_SET_FIELD[p], to_remove, projectKey=self.concerned_object.key)
            to_add = diff(decoded_perms, self.permissions[p])
            self._post_api(ProjectPermissions.API_SET[p], ProjectPermissions.API_SET_FIELD[p], to_add, projectKey=self.concerned_object.key)
        return self.read()


class AggregationPermissions(ProjectPermissions):
    def __init__(self, concerned_object):
        self.concerned_object = concerned_object
        super().__init__(concerned_object)

    def read(self, perm_type=None):
        super().read(perm_type)
        self._remove_non_aggregation_permissions(perm_type)
        return self

    def set(self, new_perms):
        return super().set(_permission_filter(new_perms, AGGREGATION_PERMISSIONS))

    def _remove_non_aggregation_permissions(self, perm_type=None):
        # Hack: SonarQube return permissions for aggregations that do not exist
        for ptype in _normalize(perm_type):
            for u, perms in self.permissions[ptype].items():
                self.permissions[ptype][u] = _permission_filter(perms, AGGREGATION_PERMISSIONS)


class PortfolioPermissions(AggregationPermissions):
    pass


class ApplicationPermissions(AggregationPermissions):
    pass


def simplify(perms_dict):
    if perms_dict is None or len(perms_dict) == 0:
        return None
    return {k: encode(v) for k, v in perms_dict.items() if len(v) > 0}


def flatten(perm_list):
    flat = []
    for elem, perms in perm_list.items():
        flat += [{elem: p} for p in perms]
    return flat


def import_config(endpoint, config_data):
    permissions = config_data.get("permissions", {})
    if len(permissions) == 0:
        utilities.logger.info("No global permissions in config, skipping import...")
        return
    utilities.logger.info("Importing global permissions")
    global_perms = GlobalPermissions(endpoint)
    global_perms.set(permissions)


def encode(perms_array):
    return utilities.list_to_csv(perms_array, ", ")


def decode(encoded_perms):
    return utilities.csv_to_list(encoded_perms)


def _is_valid(perm_type):
    return perm_type is not None and perm_type in PERMISSION_TYPES


def _normalize(perm_type):
    return (perm_type) if _is_valid(perm_type) else PERMISSION_TYPES


def apply_api(endpoint, api, ufield, uvalue, ofield, ovalue, perm_list):
    for p in perm_list:
        endpoint.post(api, params={ufield: uvalue, ofield: ovalue, "permission": p})


def diff_full(perms_1, perms_2):
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
    diff_perms = perms_1.copy()
    for elem in perms_2:
        if elem in diff_perms:
            diff_perms.remove(elem)
    return diff_perms


def _permission_filter(permissions, permissions_list, black_list=False):
    if black_list:
        return [p for p in permissions if p not in permissions_list]
    else:
        return [p for p in permissions if p in permissions_list]
