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


class QualityProfilePermissions(quality_permissions.QualityPermissions):

    API_GET = {"users": "qualityprofiles/search_users", "groups": "qualityprofiles/search_groups"}
    API_SET = {"users": "qualityprofiles/add_user", "groups": "qualityprofiles/add_group"}
    API_REMOVE = {"users": "qualityprofiles/remove_user", "groups": "qualityprofiles/remove_group"}
    API_GET_ID = "qualityProfile"
    API_GET_FIELD = {"users": "login", "groups": "name"}
    API_SET_FIELD = {"users": "login", "groups": "group"}

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
            utilities.logger.debug("Won't read %s since it is built-in", str(self))
            return self
        if self.endpoint.version() < (6, 6, 0):
            utilities.logger.debug("Won't read %s on SonarQube < 6.6", str(self))
            return self
        for p in permissions.normalize(perm_type):
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
        for p in permissions.PERMISSION_TYPES:
            if new_perms is None or p not in new_perms:
                continue
            decoded_perms = permissions.decode(new_perms[p])
            to_remove = permissions.diffarray(self.permissions[p], decoded_perms)
            self._post_api(
                QualityProfilePermissions.API_REMOVE[p],
                QualityProfilePermissions.API_SET_FIELD[p],
                to_remove,
                qualityProfile=self.concerned_object.name,
                language=self.concerned_object.language,
            )
            to_add = permissions.diffarray(decoded_perms, self.permissions[p])
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
            return self.permissions[perm_type] if permissions.is_valid(perm_type) else self.permissions
        perms = {p: utilities.list_to_csv(self.permissions.get(p, None), ", ") for p in permissions.normalize(perm_type) if len(self.permissions.get(p, {})) > 0}
        return perms if len(perms) > 0 else None
