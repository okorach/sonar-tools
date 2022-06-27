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
from sonar.permissions import permissions

MAX_PERMS = 25

class QualityPermissions(permissions.Permissions):
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
        params["ps"] = MAX_PERMS
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
