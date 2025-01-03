#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2022-2025 Olivier Korach
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

"""Abstraction of the SonarQube language concept"""
from __future__ import annotations

import json
from threading import Lock
from sonar import sqobject, rules
import sonar.platform as pf
from sonar.util.types import ApiPayload
from sonar.util import cache

#: List of language APIs
APIS = {"list": "languages/list"}


_CLASS_LOCK = Lock()


class Language(sqobject.SqObject):
    """
    Abstraction of the Sonar language concept
    """

    CACHE = cache.Cache()

    def __init__(self, endpoint: pf.Platform, key: str, name: str) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.name = name  #: Language name
        self._nb_rules = {"_ALL": None, "BUG": None, "VULNERABILITY": None, "CODE_SMELL": None, "SECURITY_HOTSPOT": None}
        Language.CACHE.put(self)

    @classmethod
    def load(cls, endpoint: pf.Platform, data: ApiPayload) -> Language:
        o = Language.CACHE.get(data["key"], endpoint.url)
        if not o:
            o = cls(endpoint=endpoint, key=data["key"], name=data["name"])
        return o

    @classmethod
    def read(cls, endpoint: pf.Platform, key: str) -> Language:
        """Reads a language and return the corresponding object
        :return: Language object
        :rtype: Language or None if not found
        """
        get_list(endpoint)
        return Language.CACHE.get(key, endpoint.url)

    def number_of_rules(self, rule_type: str = None) -> int:
        """Count rules in the language, optionally filtering on rule type

        :param rule_type: Rule type to filter on, defaults to None
        :type rule_type: str
        :returns: Nbr of rules for that language (and optional type)
        :rtype: int
        """
        if not rule_type or rule_type not in rules.LEGACY_TYPES:
            rule_type = "_ALL"
        if not self._nb_rules[rule_type]:
            self._nb_rules[rule_type] = rules.search(self.endpoint, languages=self.key, types=rule_type)
        return self._nb_rules[rule_type]


def read_list(endpoint: pf.Platform) -> dict[str, Language]:
    """Reads the list of languages existing on the SonarQube platform
    :param Platform endpoint: Reference of the SonarQube platform
    :return: List of languages
    :rtype: dict{<language_key>: <language_name>}
    """
    data = json.loads(endpoint.get(APIS["list"]).text)
    for lang in data["languages"]:
        _ = Language(endpoint=endpoint, key=lang["key"], name=lang["name"])
    return {o.key: o for o in Language.CACHE.objects.values()}


def get_list(endpoint: pf.Platform, use_cache: bool = True) -> dict[str, Language]:
    """Gets the list of languages existing on the SonarQube platform
    Unlike read_list, get_list() is using a local cache if available (so no API call)
    :param Platform endpoint: Reference of the SonarQube platform
    :param bool use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :return: List of languages
    :rtype: dict{<language_key>: <language_name>}
    """
    with _CLASS_LOCK:
        if len(Language.CACHE) == 0 or not use_cache:
            read_list(endpoint)
    return {o.key: o for o in Language.CACHE.objects.values()}


def exists(endpoint: pf.Platform, language: str) -> bool:
    """Returns whether a language exists
    :param Platform endpoint: Reference of the SonarQube platform
    :param str language: The language key
    :return: Whether the language exists
    """
    return language in get_list(endpoint)
