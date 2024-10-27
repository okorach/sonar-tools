#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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
from threading import Lock

import sonar.logging as log
import sonar.platform as pf
from sonar.util.types import ApiPayload
from sonar.util import cache

from sonar import sqobject, utilities

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
)

#: Dict of metric grouped by type (INT, FLOAT, WORK_DUR etc...)
METRICS_BY_TYPE = {}

#: Metrics API
APIS = {
    "search": "metrics/search",
}

__MAX_PAGE_SIZE = 500
_CLASS_LOCK = Lock()


class Metric(sqobject.SqObject):
    """
    Abstraction of the SonarQube "metric" concept
    """

    CACHE = cache.Cache()

    def __init__(self, endpoint: pf.Platform, key: str, data: ApiPayload = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.type = None  #: Type (FLOAT, INT, STRING, WORK_DUR...)
        self.name = None  #: Name
        self.description = None  #: Description
        self.domain = None  #: Domain
        self.direction = None  #: Directory
        self.qualitative = None  #: Qualitative
        self.hidden = None  #: Hidden
        self.custom = None  #: Custom
        self.__load(data)
        Metric.CACHE.put(self)

    def __load(self, data: ApiPayload) -> bool:
        log.debug("Loading metric %s", str(data))
        self.type = data["type"]
        self.name = data["name"]
        self.description = data.get("description", "")
        self.domain = data.get("domain", "")
        self.qualitative = data["qualitative"]
        self.hidden = data["hidden"]
        self.custom = data.get("custom", None)
        if self.type not in METRICS_BY_TYPE:
            METRICS_BY_TYPE[self.type] = set()
        METRICS_BY_TYPE[self.type].add(self.key)
        return True

    def is_a_rating(self) -> bool:
        """
        :returns: Whether a metric is a rating
        :rtype: bool
        """
        return self.type == "RATING"

    def is_a_percent(self) -> bool:
        """
        :returns: Whether a metric is a percentage (or ratio or density)
        :rtype: bool
        """
        return self.type == "PERCENT"

    def is_an_effort(self) -> bool:
        """
        :returns: Whether a metric is an effort
        :rtype: bool
        """
        return self.type == "WORK_DUR"

    def is_of_type(self, metric_type: str) -> bool:
        """
        :param str metric_type:
        :returns: Whether a metric is of a given type (INT, BOOL, FLOAT, WORK_DUR, etc...)
        :rtype: bool
        """
        return metric_type in METRICS_BY_TYPE and self.type in METRICS_BY_TYPE[metric_type]


def is_a_rating(metric_key: str) -> bool:
    """
    :param metric_key: The concerned metric key
    :type metric_key: str
    :returns: Whether a metric is a rating
    :rtype: bool
    """
    return is_of_type(metric_key, "RATING")


def search(endpoint: pf.Platform, show_hidden_metrics: bool = False, use_cache: bool = True) -> dict[str, Metric]:
    """
    :param Platform endpoint: Reference to the SonarQube platform object
    :param bool show_hidden_metrics: Whether to also include hidden (private) metrics
    :param bool use_cache: Whether to use local cache or query SonarQube, default True (use cache)
    :return: List of metrics
    :rtype: dict of Metric
    """
    with _CLASS_LOCK:
        if len(Metric.CACHE) == 0 or not use_cache:
            page, nb_pages = 1, 1
            while page <= nb_pages:
                data = json.loads(endpoint.get(APIS["search"], params={"ps": __MAX_PAGE_SIZE, "p": page}).text)
                for m in data["metrics"]:
                    _ = Metric(endpoint=endpoint, key=m["key"], data=m)
                nb_pages = utilities.nbr_pages(data)
                page += 1
    m_list = {k: v for k, v in Metric.CACHE.items() if not v.hidden or show_hidden_metrics}
    return {m.key: m for m in m_list.values()}


def is_a_percent(metric_key: str) -> bool:
    """
    :param metric_key: The concerned metric key
    :type metric_key: str
    :returns: Whether a metric is a percent
    :rtype: bool
    """
    return is_of_type(metric_key, "PERCENT")


def is_an_effort(metric_key: str) -> bool:
    """
    :param metric_key: The concerned metric key
    :type metric_key: str
    :returns: Whether a metric is an effort
    :rtype: bool
    """
    return is_of_type(metric_key, "WORK_DUR")


def is_of_type(metric_key: str, metric_type: str) -> bool:
    """
    :param str metric_key: The concerned metric key
    :param str metric_type:
    :returns: Whether a metric is of a given type (INT, BOOL, FLOAT, WORK_DUR, etc...)
    :rtype: bool
    """
    return metric_type in METRICS_BY_TYPE and metric_key in METRICS_BY_TYPE[metric_type]


def count(endpoint: pf.Platform, use_cache: bool = True) -> int:
    """
    :param Platform endpoint: Reference to the SonarQube platform object
    :returns: Count of public metrics
    :rtype: int
    """
    with _CLASS_LOCK:
        if len(Metric.CACHE) == 0 or not use_cache:
            search(endpoint, True)
    return len([v for v in Metric.CACHE.values() if not v.hidden])
