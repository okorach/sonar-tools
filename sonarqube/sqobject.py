#
# sonar-tools
# Copyright (C) 2019-2021 Olivier Korach
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
'''

    Abstraction of the SonarQube general object concept

'''
import json
import sonarqube.env as env


class SqObject:

    def __init__(self, key, env):
        self.key = key
        self.env = env

    def set_env(self, env):
        self.env = env

    def get_env(self):
        return self.env

    def get(self, api, params=None):
        return env.get(api, params, self.env)

    def post(self, api, params=None):
        return env.post(api, params, self.env)

    def delete(self, api, params=None):
        resp = env.delete(api, params, self.env)
        return (resp.status_code // 100) == 2

def search_objects(api, params, key_field, returned_field, object_class, p=None, ps=500, endpoint=None):
    if params is None:
        params = {}
    params['ps'] = ps
    resp = env.get(api, params=params, ctxt=endpoint)
    data = json.loads(resp.text)
    #if 'paging' in data['paging'] and 'total' in data['paging'] and data['paging']['total'] > 500:
    #    util.logger.critical("Pagination on applications search is not yet supported "
    #    "and there are more than 500 of them. Will return only 500 first objects")

    objects = {}
    for obj in data[returned_field]:
        objects[obj[key_field]] = object_class(obj[key_field], endpoint=endpoint, data=obj)
    if p is not None:
        return objects

    nb_pages = (data['paging']['total'] + ps - 1) // ps
    p = 2
    while p <= nb_pages:
        params['p'] = p
        resp = env.get(api, params, endpoint)
        data = json.loads(resp.text)
        nb_pages = (data['paging']['total'] + ps - 1) // ps
        for obj in data[returned_field]:
            objects[obj[key_field]] = object_class(obj[key_field], endpoint=endpoint, data=obj)
        p += 1
    return objects
