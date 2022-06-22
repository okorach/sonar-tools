#!/usr/local/bin/python3
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

import json

API_LIST = "languages/list"

_OBJECTS = {}


def read_list(endpoint):
    data = json.loads(endpoint.get(API_LIST).text)
    for lang in data["languages"]:
        _OBJECTS[lang["key"]] = lang["name"]
    return _OBJECTS


def get_list(endpoint):
    if len(_OBJECTS) == 0:
        read_list(endpoint)
    return _OBJECTS


def exists(endpoint, language):
    return language in get_list(endpoint)


def get_object(endpoint, language):
    get_list(endpoint)
    return _OBJECTS.get(language, None)
