#
# sonar-tools
# Copyright (C) 2019-2026 Olivier Korach
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

"""Abstraction of the SonarQube metric concept"""

from __future__ import annotations
from typing import Optional, Any, TYPE_CHECKING

from sonar.sqobject import SqObject
from sonar.util import cache
from sonar import exceptions
import sonar.utilities as sutil

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiPayload

#: List of what can be considered the main metrics
MAIN_METRICS = (
    "violations",
    "bugs",
    "vulnerabilities",
    "code_smells",
    "security_hotspots",
    "reliability_rating",
    "security_rating",
    "sqale_rating",
    "security_review_rating",
    "sqale_debt_ratio",
    "sqale_index",
    "coverage",
    "duplicated_lines_density",
    "security_hotspots_reviewed",
    "new_violations",
    "new_bugs",
    "new_vulnerabilities",
    "new_code_smells",
    "new_security_hotspots",
    "new_reliability_rating",
    "new_security_rating",
    "new_maintainability_rating",
    "new_security_review_rating",
    "new_sqale_debt_ratio",
    "new_coverage",
    "new_duplicated_lines_density",
    "new_security_hotspots_reviewed",
    "ncloc",
    "false_positive_issues",
    "blocker_violations",
    "critical_violations",
)

MAIN_METRICS_10 = ("accepted_issues", "software_quality_blocker_issues", "software_quality_high_issues")
MAIN_METRICS_ENTERPRISE_10 = ("prioritized_rule_issues",)
MAIN_METRICS_ENTERPRISE_2025_3 = ("contains_ai_code", "sca_count_any_issue", "new_sca_count_any_issue")

#: Dict of metric grouped by type (INT, FLOAT, WORK_DUR etc...)
METRICS_BY_TYPE = {}

MAX_PAGE_SIZE = 500


class Metric(SqObject):
    """Abstraction of the SonarQube "metric" concept"""

    CACHE = cache.Cache()

    def __init__(self, endpoint: Platform, data: ApiPayload = None) -> None:
        """Constructor"""
        super().__init__(endpoint, data)
        self.key = data["key"]
        self.type: Optional[str] = None  #: Type (FLOAT, INT, STRING, WORK_DUR...)
        self.name: Optional[str] = None  #: Name
        self.description: Optional[str] = None  #: Description
        self.domain: Optional[str] = None  #: Domain
        self.direction: Optional[str] = None  #: Directory
        self.qualitative: Optional[bool] = None  #: Qualitative
        self.hidden: Optional[bool] = None  #: Hidden
        self.custom: Optional[bool] = None  #: Custom
        self.reload(data)
        self.__class__.CACHE.put(self)

    @classmethod
    def get_object(cls, endpoint: Platform, key: str, use_cache: bool = True) -> Metric:
        """Returns a Metric object from its key"""
        o = cls.CACHE.get(endpoint.local_url, key)
        if use_cache and o:
            return o
        cls.search(endpoint, include_hidden_metrics=True, use_cache=False)
        return cls.CACHE.get(endpoint.local_url, key)

    @classmethod
    def search(cls, endpoint: Platform, include_hidden_metrics: bool = False, use_cache: bool = False, **search_params: Any) -> dict[str, Metric]:
        """
        :param endpoint: Reference to the SonarQube platform object
        :param include_hidden_metrics: Whether to also include hidden (private) metrics
        :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
        :param search_params: Search filters (see api/metrics/search parameters)
        :return: Dict of metrics indexed by metric key
        """
        if not use_cache or len(search_params) > 0 or len(cls.CACHE.from_platform(endpoint)) == 0:
            cls.get_paginated(endpoint, threads=1)
        return {v.key: v for v in cls.CACHE.from_platform(endpoint).values() if not v.hidden or include_hidden_metrics}

    @classmethod
    def count(cls, endpoint: Platform, **search_params: Any) -> int:
        """Returns the number of public metrics

        :param endpoint: Reference to the SonarQube platform object
        :param include_hidden_metrics: Whether to also include hidden (private) metrics
        :param use_cache: Whether to use local cache or query SonarQube, default True (use cache)
        :return: Number of public metrics
        """
        return len(cls.search(endpoint, include_hidden_metrics=search_params.pop("include_hidden_metrics", False), **search_params))

    def reload(self, data: ApiPayload) -> bool:
        """Reloads a metric from data"""
        self.type = data["type"]
        self.name = data["name"]
        self.description = data.get("description", "")
        self.domain = data.get("domain", "")
        self.qualitative = data["qualitative"]
        self.hidden = data["hidden"]
        self.custom = data.get("custom", None)
        return True

    def is_a_rating(self) -> bool:
        """Whether a metric is a rating"""
        return self.type == "RATING"

    def is_a_percent(self) -> bool:
        """Whether a metric is a percentage (or ratio or density)"""
        return self.type == "PERCENT"

    def is_an_effort(self) -> bool:
        """Whether a metric is an effort"""
        return self.type == "WORK_DUR"
