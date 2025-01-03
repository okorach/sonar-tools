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

"""Parent permissions class for quality gates and quality profiles permissions subclasses"""

from __future__ import annotations
from typing import Optional

import json
from requests import RequestException

from sonar.util import types
import sonar.logging as log
from sonar import utilities
from sonar.permissions import permissions

MAX_PERMS = 25


class QualityPermissions(permissions.Permissions):
    """
    Abstractions of QP and QG permissions
    """

    def _post_api(self, api: str, set_field: str, perms_dict: types.JsonPermissions, **extra_params) -> bool:
        """Runs a post on QG or QP permissions"""
        if perms_dict is None:
            return True
        result = False
        params = extra_params.copy()
        for u in perms_dict:
            params[set_field] = u
            r = self.endpoint.post(api, params=params)
            result = result and r.ok
        return result

    def to_json(self, perm_type: Optional[tuple[str, ...]] = None, csv: bool = False) -> types.ObjectJsonRepr:
        """Returns the JSON representation of permissions"""
        if not csv:
            return self.permissions[perm_type] if permissions.is_valid(perm_type) else self.permissions
        perms = {}
        if not self.permissions:
            return None
        for p in permissions.normalize(perm_type):
            dperms = self.permissions.get(p, None)
            if dperms is not None and len(dperms) > 0:
                perms[p] = permissions.encode(self.permissions.get(p, None))
        return perms if len(perms) > 0 else None

    def _get_api(self, api: str, perm_type: tuple[str, ...], ret_field: str, **extra_params) -> list[str]:
        perms = []
        params = extra_params.copy()
        params["ps"] = MAX_PERMS
        page, nbr_pages = 1, 1
        while page <= nbr_pages:
            params["p"] = page
            try:
                resp = self.endpoint.get(api, params=params)
                data = json.loads(resp.text)
                perms += [p[ret_field] for p in data[perm_type]]
                page, nbr_pages = page + 1, utilities.nbr_pages(data)
            except (ConnectionError, RequestException) as e:
                utilities.handle_error(e, f"getting permissions of {str(self)}", catch_all=True)
                page += 1
        return perms

    def _set_perms(self, new_perms: types.ObjectJsonRepr, apis: dict[str, dict[str, str]], field: str, diff_func: callable, **kwargs) -> bool:
        """Sets permissions of a QG or QP"""
        if self.concerned_object.is_built_in:
            log.debug("Can't set %s because it's built-in", str(self))
            self.permissions = {p: [] for p in permissions.PERMISSION_TYPES}
            return False
        log.debug("Setting %s with %s", str(self), str(new_perms))
        if self.permissions is None:
            self.read()
        for p in permissions.PERMISSION_TYPES:
            if new_perms is None or p not in new_perms:
                continue
            decoded_perms = permissions.decode(new_perms[p])
            to_remove = diff_func(self.permissions[p], decoded_perms)
            self._post_api(apis["remove"][p], field[p], to_remove, **kwargs)
            to_add = diff_func(decoded_perms, self.permissions[p])
            self._post_api(apis["add"][p], field[p], to_add, **kwargs)
        self.read()
        return True

    def _read_perms(self, apis: dict[str, dict[str, str]], field: str, **kwargs) -> types.ObjectJsonRepr:
        """Reads permissions of a QP or QG"""
        self.permissions = {p: [] for p in permissions.PERMISSION_TYPES}
        if self.endpoint.is_sonarcloud():
            log.debug("No permissions for %s because it's SonarCloud", str(self))
        elif self.concerned_object.is_built_in:
            log.debug("No permissions for %s because it's built-in", str(self))
        else:
            for p in permissions.PERMISSION_TYPES:
                self.permissions[p] = self._get_api(apis["get"][p], p, field[p], **kwargs)
        return self.permissions
