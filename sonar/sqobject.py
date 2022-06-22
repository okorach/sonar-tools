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
"""

    Abstraction of the SonarQube general object concept

"""

import json
from sonar import utilities


class SqObject:
    def __init__(self, key, endpoint):
        self.key = key
        self.endpoint = endpoint
        self._json = None

    def uuid(self):
        return self.key

    def set_env(self, endpoint):
        self.endpoint = endpoint

    def get_env(self):
        return self.endpoint

    def get(self, api, params=None, exit_on_error=True):
        return self.endpoint.get(api=api, params=params, exit_on_error=exit_on_error)

    def post(self, api, params=None, exit_on_error=True):
        return self.endpoint.post(api=api, params=params, exit_on_error=exit_on_error)

    def delete(self, api, params=None):
        resp = self.endpoint.delete(api, params)
        return resp.ok


def search_objects(api, endpoint, key_field, returned_field, object_class, params):
    __MAX_SEARCH = 500
    new_params = {} if params is None else params.copy()
    if "ps" not in new_params:
        new_params["ps"] = __MAX_SEARCH
    page, nb_pages = 1, 1
    objects_list = {}
    while page <= nb_pages:
        new_params["p"] = page
        data = json.loads(endpoint.get(api, params=new_params).text)
        for obj in data[returned_field]:
            if object_class.__name__ in ("Portfolio", "Groups"):
                objects_list[obj[key_field]] = object_class.load(name=obj[key_field], endpoint=endpoint, data=obj)
            elif object_class.__name__ == "QualityProfile":
                objects_list[obj[key_field]] = object_class.load(name=obj["name"], language=obj["language"], endpoint=endpoint, data=obj)
            else:
                objects_list[obj[key_field]] = object_class(obj[key_field], endpoint, data=obj)
        nb_pages = utilities.nbr_pages(data)
        page += 1
    return objects_list


def key_of(obj_or_key):
    if isinstance(obj_or_key, str):
        return obj_or_key
    else:
        return obj_or_key.key
