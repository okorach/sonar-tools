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
"""

    Parent module of applications and portfolios

"""

from typing import Optional
import json

import sonar.logging as log
from sonar.util import types
import sonar.platform as pf

import sonar.components as comp
from sonar import utilities
from sonar.audit.rules import get_rule
from sonar.audit.problem import Problem


class Aggregation(comp.Component):
    """Parent class of applications and portfolios"""

    def __init__(self, endpoint: pf.Platform, key: str, data: types.ApiPayload = None) -> None:
        self._nbr_projects = None
        self._permissions = None
        super().__init__(endpoint=endpoint, key=key)

    def reload(self, data: dict[str, any]) -> None:
        """Reloads an Aggregation (Application or Portfolio) from the result of a search or get

        :return: self
        :rtype: None
        """
        super().reload(data)
        for d in ("description", "desc"):
            if d in data:
                self._description = self.sq_json[d]

    def nbr_projects(self) -> int:
        """Returns the number of projects of an Aggregation (Application or Portfolio)
        :return: The number of projects
        :rtype: int
        """
        if self._nbr_projects is None:
            self._nbr_projects = 0
            data = json.loads(
                self.get(
                    "measures/component",
                    params={"component": self.key, "metricKeys": "projects,ncloc"},
                ).text
            )[
                "component"
            ]["measures"]
            for m in data:
                if m["metric"] == "projects":
                    self._nbr_projects = int(m["value"])
                elif m["metric"] == "ncloc":
                    self.ncloc = int(m["value"])
        return self._nbr_projects

    def _audit_aggregation_cardinality(self, sizes: tuple[int], broken_rule: object) -> list[Problem]:
        problems = []
        n = self.nbr_projects()
        if n in sizes:
            problems.append(Problem(get_rule(broken_rule), self, str(self)))
        else:
            log.debug("%s has %d projects", str(self), n)
        return problems

    def _audit_empty_aggregation(self, broken_rule: object) -> list[Problem]:
        return self._audit_aggregation_cardinality((0, None), broken_rule)

    def _audit_singleton_aggregation(self, broken_rule: object) -> list[Problem]:
        return self._audit_aggregation_cardinality((1, 1), broken_rule)

    def permissions(self) -> Optional[object]:
        """Should be implement in child classes"""
        return self._permissions

    def audit(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        if self.permissions() is None:
            return []
        return self.permissions().audit(audit_settings)


def count(api: str, endpoint: pf.Platform, params: types.ApiParams = None) -> int:
    """Returns number of aggregations of a given type (Application OR Portfolio)
    :return: number of Apps or Portfolios
    :rtype: int
    """
    if params is None:
        params = {}
    params["ps"] = 1
    return utilities.nbr_total_elements(json.loads(endpoint.get(api, params=params).text))
