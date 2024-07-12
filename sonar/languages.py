#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2022-2024 Olivier Korach
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

from __future__ import annotations

import json
from threading import Lock
from sonar import sqobject, rules
import sonar.platform as pf

#: List of language APIs
APIS = {"list": "languages/list"}

_OBJECTS = {}
_CLASS_LOCK = Lock()


class Language(sqobject.SqObject):
    """
    Abstraction of the Sonar language concept
    """

    def __init__(self, endpoint: pf.Platform, key: str, name: str) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.name = name  #: Language name
        self._nb_rules = {"ALL": None, "BUG": None, "VULNERABILITY": None, "COD_SMELL": None, "SECURITY_HOTSPOT": None}
        _OBJECTS[self.uuid()] = self

    @classmethod
    def load(cls, endpoint: pf.Platform, data: dict[str, str]) -> Language:
        uu = sqobject.uuid(data["key"], endpoint.url)
        return _OBJECTS.get(uu, cls(endpoint=endpoint, key=data["key"], name=data["name"]))

    @classmethod
    def read(cls, endpoint: pf.Platform, key: str) -> Language:
        """Reads a language and return the corresponding object
        :return: Language object
        :rtype: Language or None if not found
        """
        get_list(endpoint)
        return _OBJECTS.get(sqobject.uuid(key, endpoint.url), None)

    def number_of_rules(self, rule_type: str = None) -> int:
        """Count rules in the language, optionally filtering on rule type

        :param rule_type: Rule type to filter on, defaults to None
        :type rule_type: str
        :returns: Nbr of rules for that language (and optional type)
        :rtype: int
        """
        if not rule_type or rule_type not in rules.TYPES:
            r_ndx = "_all"
        if not self._nb_rules[r_ndx]:
            self._nb_rules[r_ndx] = rules.search(self.endpoint, languages=self.key, types=rule_type)
        return self._nb_rules[r_ndx]


def read_list(endpoint: pf.Platform) -> dict[str, Language]:
    """Reads the list of languages existing on the SonarQube platform
    :param Platform endpoint: Reference of the SonarQube platform
    :return: List of languages
    :rtype: dict{<language_key>: <language_name>}
    """
    data = json.loads(endpoint.get(APIS["list"]).text)
    for lang in data["languages"]:
        _ = Language(endpoint=endpoint, key=lang["key"], name=lang["name"])
    return _OBJECTS


def get_list(endpoint: pf.Platform, use_cache: bool = True) -> dict[str, Language]:
    """Gets the list of languages existing on the SonarQube platform
    Unlike read_list, get_list() is using a local cache if available (so no API call)
    :param Platform endpoint: Reference of the SonarQube platform
    :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :type use_cache: bool
    :return: List of languages
    :rtype: dict{<language_key>: <language_name>}
    """
    with _CLASS_LOCK:
        if len(_OBJECTS) == 0 or not use_cache:
            read_list(endpoint)
    return _OBJECTS


def exists(endpoint: pf.Platform, language: str) -> bool:
    """Returns whether a language exists
    :param Platform endpoint: Reference of the SonarQube platform
    :param str language: The language key
    :return: Whether the language exists
    """
    return language in [l.name for l in get_list(endpoint).values()]
