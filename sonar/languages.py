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
from typing import Optional, Any, TYPE_CHECKING

import json
from threading import Lock

from sonar.sqobject import SqObject
from sonar import rules
from sonar.util import misc
from sonar.util import cache
import sonar.util.issue_defs as idefs

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload

#: List of language APIs
APIS = {"list": "languages/list"}


_CLASS_LOCK = Lock()


class Language(SqObject):
    """Abstraction of the Sonar language concept"""

    CACHE = cache.Cache()

    def __init__(self, endpoint: Platform, key: str, name: str) -> None:
        """Constructor

        :param endpoint: Reference of the SonarQube platform
        :param key: Language key
        :param name: Language name
        """
        super().__init__(endpoint=endpoint, key=key)
        self.name = name  #: Language name
        self._nb_rules = {"_ALL": None, idefs.TYPE_BUG: None, idefs.TYPE_VULN: None, idefs.TYPE_CODE_SMELL: None, idefs.TYPE_HOTSPOT: None}
        Language.CACHE.put(self)

    @classmethod
    def load(cls, endpoint: Platform, data: ApiPayload) -> Language:
        """Loads a languages from an API payload

        :param endpoint: Reference of the SonarQube platform
        :param data: API payload from api/languages/list
        """
        o = Language.CACHE.get(data["key"], endpoint.local_url)
        if not o:
            o = cls(endpoint=endpoint, key=data["key"], name=data["name"])
        return o

    @classmethod
    def read(cls, endpoint: Platform, key: str) -> Optional[Language]:
        """Reads a language and return the corresponding object

        :param endpoint: Reference of the SonarQube platform
        :param key: The language key"""
        cls.get_list(endpoint)
        return Language.CACHE.get(key, endpoint.local_url)

    @classmethod
    def get_list(cls, endpoint: Platform, use_cache: bool = True) -> dict[str, Language]:
        """Gets the list of languages existing on the SonarQube platform
        Unlike read_list, get_list() is using a local cache if available (so no API call)

        :param endpoint: Reference of the SonarQube platform
        :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
        :return: List of languages
        :rtype: dict{<language_key>: <language_name>}
        """
        with _CLASS_LOCK:
            if len(cls.CACHE) == 0 or not use_cache:
                read_list(endpoint)
        return {o.key: o for o in cls.CACHE.objects.values()}

    def number_of_rules(self, rule_type: Optional[str] = None) -> int:
        """Count rules in the language, optionally filtering on rule type

        :param rule_type: Rule type to filter on, defaults to None
        """
        if rule_type not in (idefs.TYPE_VULN, idefs.TYPE_HOTSPOT, idefs.TYPE_BUG, idefs.TYPE_CODE_SMELL):
            rule_type = None
        if self._nb_rules[rule_type or "_ALL"] is None:
            self._nb_rules[rule_type or "_ALL"] = len(
                rules.Rule.search(self.endpoint, params=misc.remove_nones({"languages": self.key, "types": rule_type}))
            )
        return self._nb_rules[rule_type or "_ALL"]

    @classmethod
    def exists(cls, endpoint: Platform, **kwargs: Any) -> bool:
        """Returns whether a language exists

        :param endpoint: Reference of the SonarQube platform
        :param language: The language key
        """
        return kwargs.get("language") in cls.get_list(endpoint)


def read_list(endpoint: Platform) -> dict[str, Language]:
    """Reads the list of languages existing on the SonarQube platform

    :param endpoint: Reference of the SonarQube platform
    :return: List of languages
    :rtype: dict{<language_key>: <language_name>}
    """
    data = json.loads(endpoint.get(APIS["list"]).text)
    for lang in data["languages"]:
        _ = Language(endpoint=endpoint, key=lang["key"], name=lang["name"])
    return {o.key: o for o in Language.CACHE.objects.values()}
