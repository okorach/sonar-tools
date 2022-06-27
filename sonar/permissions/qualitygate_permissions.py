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
from sonar import utilities, options
from sonar.permissions import permissions, quality_permissions

class QualityGatePermissions(quality_permissions.QualityPermissions):
    API_GET = {"users": "qualitygates/search_users", "groups": "qualitygates/search_groups"}
    API_SET = {"users": "qualitygates/add_user", "groups": "qualitygates/add_group"}
    API_REMOVE = {"users": "qualitygates/remove_user", "groups": "qualitygates/remove_group"}
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "groupName"}

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
        self.permissions = {p: [] for p in permissions.PERMISSION_TYPES}
        if self.concerned_object.is_built_in:
            utilities.logger.debug("Won't read %s because it's built-in", str(self))
            return self
        if self.endpoint.version() < (9, 2, 0):
            utilities.logger.debug("Won't read %s on SonarQube < 9.2", str(self))
            return self
        for p in permissions.normalize(perm_type):
            self.permissions[p] = self._get_api(
                QualityGatePermissions.API_GET[p], p, QualityGatePermissions.API_GET_FIELD[p], gateName=self.concerned_object.name
            )
        return self

    def set(self, new_perms):
        if self.concerned_object.is_built_in:
            utilities.logger.debug("Can't set %s because it's built-in", str(self))
            self.permissions = {p: [] for p in permissions.PERMISSION_TYPES}
            return self
        if self.endpoint.version() < (9, 2, 0):
            utilities.logger.debug("Can set %s on SonarQube < 9.2", str(self))
            self.permissions = {p: [] for p in permissions.PERMISSION_TYPES}
            return self
        utilities.logger.debug("Setting %s with %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        for p in permissions.PERMISSION_TYPES:
            if new_perms is None or p not in new_perms:
                continue
            decoded_perms = permissions.decode(new_perms[p])
            to_remove = permissions.diffarray(self.permissions[p], decoded_perms)
            self._post_api(
                QualityGatePermissions.API_REMOVE[p], QualityGatePermissions.API_SET_FIELD[p], to_remove, gateName=self.concerned_object.name
            )
            to_add = permissions.diffarray(decoded_perms, self.permissions[p])
            self._post_api(QualityGatePermissions.API_SET[p], QualityGatePermissions.API_SET_FIELD[p], to_add, gateName=self.concerned_object.name)
        return self.read()

    def to_json(self, perm_type=None, csv=False):
        if not csv:
            return self.permissions[perm_type] if permissions.is_valid(perm_type) else self.permissions
        perms = {}
        for p in permissions.normalize(perm_type):
            dperms = self.permissions.get(p, None)
            if dperms is not None and len(dperms) > 0:
                perms[p] = permissions.encode(self.permissions.get(p, None))
        return perms if len(perms) > 0 else None

    def _get_api(self, api, perm_type, ret_field, **extra_params):
        perms = []
        params = extra_params.copy()
        params["ps"] = quality_permissions.MAX_PERMS
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
