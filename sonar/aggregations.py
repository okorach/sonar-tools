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
"""

Parent module of applications and portfolios

"""

from __future__ import annotations
from typing import Optional, Any, TYPE_CHECKING
import json

import sonar.logging as log

import sonar.components as comp
from sonar import exceptions
from sonar.audit.rules import get_rule
from sonar.audit.problem import Problem
from sonar import measures

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload, ConfigSettings


class Aggregation(comp.Component):
    """Parent class of applications and portfolios"""

    def __init__(self, endpoint: Platform, data: ApiPayload) -> None:
        """Constructor"""
        super().__init__(endpoint, data)
        self._nbr_projects: Optional[int] = None
        self._permissions: Optional[object] = None

    def reload(self, data: ApiPayload) -> Aggregation:
        """Reloads an Aggregation (Application or Portfolio) from the result of a search or get

        :param data: Payload from SonarQube API
        """
        super().reload(data)
        for d in ("description", "desc"):
            if d in data:
                self._description = self.sq_json[d]
        return self

    def get_measures_history(self, metrics_list: list[str]) -> dict[str, str]:
        """Returns the history of a project metrics"""
        return measures.get_history(self, metrics_list, component=self.key)

    def get_analyses(self, filter_in: Optional[list[str]] = None, filter_out: Optional[list[str]] = None, **search_params: Any) -> ApiPayload:
        """Returns a projects analyses"""
        raise exceptions.UnsupportedOperation("Aggregations don't have analyses")

    def nbr_projects(self, use_cache: bool = False) -> int:
        """Returns the number of projects of an Aggregation (Application or Portfolio)

        :param use_cache: Whether to use the local cache or call the API every time
        """
        if self._nbr_projects is None or not use_cache:
            self._nbr_projects = 0
            data = json.loads(self.get("measures/component", params={"component": self.key, "metricKeys": "projects,ncloc"}).text)
            for m in data["component"]["measures"]:
                if m["metric"] == "projects":
                    self._nbr_projects = int(m["value"])
                elif m["metric"] == "ncloc":
                    self.ncloc = int(m["value"])
        log.debug("Number of projects of %s is %d from %s", self, self._nbr_projects, data)
        return self._nbr_projects

    def _audit_aggregation_cardinality(self, sizes: tuple[int, int], broken_rule: object) -> list[Problem]:
        problems = []
        n = self.nbr_projects()
        log.debug("Auditing %s cardinality: %d projects vs %s disallowed sizes", str(self), n, str(sizes))
        if n in sizes:
            problems.append(Problem(get_rule(broken_rule), self, str(self)))
        return problems

    def _audit_empty_aggregation(self, broken_rule: object) -> list[Problem]:
        return self._audit_aggregation_cardinality((0, None), broken_rule)

    def _audit_singleton_aggregation(self, broken_rule: object) -> list[Problem]:
        return self._audit_aggregation_cardinality((1,), broken_rule)

    def permissions(self) -> Optional[object]:
        """Should be implement in child classes"""
        return self._permissions

    def audit(self, audit_settings: ConfigSettings) -> list[Problem]:
        """Audits an aggregation (only permissions, the rest is specific to subclasses)"""
        if self.permissions() is None:
            return []
        return self.permissions().audit(audit_settings)
