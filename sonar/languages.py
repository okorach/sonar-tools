#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2022-2026 Olivier Korach
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
from sonar.sqobject import SqObject
from sonar import rules
from sonar.util import cache
import sonar.util.issue_defs as idefs
from sonar.api.manager import ApiOperation as Oper
import sonar.logging as log

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload


class Language(SqObject):
    """Abstraction of the Sonar language concept"""

    CACHE = cache.Cache()

    def __init__(self, endpoint: Platform, data: ApiPayload) -> None:
        """Constructor

        :param endpoint: Reference of the SonarQube platform
        :param key: Language key
        :param name: Language name
        """
        super().__init__(endpoint, data)
        self.key = data["key"]
        self.name = data["name"]  #: Language name
        self._nb_rules = {"_ALL": None, idefs.TYPE_BUG: None, idefs.TYPE_VULN: None, idefs.TYPE_CODE_SMELL: None, idefs.TYPE_HOTSPOT: None}
        self.__class__.CACHE.put(self)

    @classmethod
    def read(cls, endpoint: Platform, key: str, use_cache: bool = True) -> Optional[Language]:
        """Reads a language and return the corresponding object if it exists, else none

        :param endpoint: Reference of the SonarQube platform
        :param key: The language key
        :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
        """
        cls.search(endpoint, use_cache=use_cache)
        return cls.CACHE.get(endpoint.local_url, key)

    @classmethod
    def search(cls, endpoint: Platform, use_cache: bool = False, **search_params: Any) -> dict[str, Language]:
        """Gets the list of languages existing on the SonarQube platform

        :param endpoint: Reference of the SonarQube platform
        :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
        :param search_params: Search filters (see api/languages/list parameters)
        :return: List of languages
        :rtype: dict{<language_key>: <language_name>}
        """
        if use_cache and len(search_params) == 0 and len(cls.CACHE.from_platform(endpoint)) > 0:
            log.debug("Searching languages from cache")
            return dict(sorted(cls.CACHE.from_platform(endpoint).items()))
        log.debug("Searching languages from SonarQube")
        api, _, params, ret = endpoint.api.get_details(cls, Oper.SEARCH, **search_params)
        data = json.loads(endpoint.get(api, params=params).text)
        return {lang["key"]: Language(endpoint, lang) for lang in data[ret]}

    def number_of_rules(self, rule_type: Optional[str] = None) -> int:
        """Count rules in the language, optionally filtering on rule type

        :param rule_type: Rule type to filter on, defaults to None for all types
        """
        if rule_type is not None and rule_type not in idefs.ALL_TYPES:
            return 0
        if self._nb_rules[rule_type or "_ALL"] is None:
            self._nb_rules[rule_type or "_ALL"] = len(rules.Rule.search(self.endpoint, use_cache=True, languages=self.key, types=rule_type))
        return self._nb_rules[rule_type or "_ALL"]

    @classmethod
    def exists(cls, endpoint: Platform, **kwargs: Any) -> bool:
        """Returns whether a language exists

        :param endpoint: Reference of the SonarQube platform
        :param language: The language key
        """
        return kwargs.get("language") in cls.search(endpoint, use_cache=True)
