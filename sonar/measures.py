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

"""Abstraction of the SonarQube measure concept"""

from __future__ import annotations
from typing import Any, Optional, Union, TYPE_CHECKING

import json

from sonar.sqobject import SqObject
from sonar import metrics, exceptions
from sonar.api.manager import ApiOperation as Oper
from sonar.util import cache
import sonar.logging as log
import sonar.util.misc as util
import sonar.utilities as sutil

if TYPE_CHECKING:
    from sonar.util.types import ApiPayload, ApiParams, KeyList, ConcernedObject
    from sonar.platform import Platform

ALT_COMPONENTS = ("project", "application", "portfolio", "key")

DATETIME_METRICS = ("last_analysis", "createdAt", "updatedAt", "creation_date", "modification_date")


class Measure(SqObject):
    """Abstraction of the SonarQube "measure" concept"""

    CACHE = cache.Cache()
    __CONCERNED_OBJECT = "concerned_object"

    def __init__(self, endpoint: Platform, data: ApiPayload) -> None:
        """Constructor"""
        super().__init__(endpoint, data)
        self.value: Optional[Any] = None  #: Measure value
        self.key = f'{data["metric"]} of {data.get(self.__class__.__CONCERNED_OBJECT)}'
        self.metric = data["metric"]  #: Measure metric
        self.component_key = data.get(self.__class__.__CONCERNED_OBJECT)
        self.branch = None
        self.pull_request = None
        self.value = self.__converted_value(data.get("value") or data["period"].get("value"))

    @classmethod
    def get_object(cls, endpoint: Platform, metric_key: str, component: ConcernedObject, use_cache: bool = True) -> Measure:
        """Returns the project object from its project key"""
        return cls.search(component, [metric_key])[metric_key]

    @staticmethod
    def hash_payload(data: ApiPayload) -> tuple[Any, ...]:
        """Returns the hash items for a given object search payload"""
        return (data["metric"], data[Measure.__CONCERNED_OBJECT], data["branch"], data["pull_request"])

    def hash_object(self) -> tuple[Any, ...]:
        """Returns the hash elements for a given object"""
        return (self.metric, self.component_key, self.branch, self.pull_request)

    def reload(self, data: ApiPayload) -> Measure:
        """Reloads a Measure object from API data"""
        super().reload(data)
        self.value = self.__converted_value(data["value"])
        return self

    def refresh(self) -> Measure:
        """Refreshes a measure by re-reading it in SonarQube"""
        return self.__class__.get_object(self.endpoint, self.metric, self.concerned_object, use_cache=False)

    def __converted_value(self, value: Any) -> Any:
        value = sutil.string_to_date(value) if self.metric in DATETIME_METRICS else util.convert_to_type(value)
        if self.is_a_rating():
            value = int(float(value))
        return value

    def count_history(self, params: Optional[ApiParams] = None) -> int:
        """Returns the number of measures in history of the metric"""
        new_params = params or {}
        new_params |= {"component": self.concerned_object.key, "metrics": self.metric, "ps": 1}
        api, _, new_params, _ = self.endpoint.api.get_details(self, Oper.GET_HISTORY, **new_params)
        return sutil.nbr_total_elements(json.loads(self.endpoint.get(api, params=new_params).text))

    def search_history(self, params: Optional[ApiParams] = None) -> dict[str, Any]:
        """Searches the history of the measure

        :param params: List of search parameters to narrow down the search, defaults to None
        :return: The history of the metric, attached to the given component
        """
        __MAX_PAGE_SIZE = 1000
        measures = {}
        page, nbr_pages = 1, 1
        p_field = self.endpoint.api.page_field(self, Oper.GET_HISTORY)
        new_params = params or {}
        new_params |= {"component": self.concerned_object.key, "metrics": self.metric, "ps": __MAX_PAGE_SIZE}
        api, _, new_params, ret = self.endpoint.api.get_details(self, Oper.GET_HISTORY, **new_params)
        while page <= nbr_pages:
            data = json.loads(self.endpoint.get(api, params=new_params | {p_field: page}).text)
            measures |= {m["date"]: m["value"] for m in data[ret][0]["history"]}
            nbr_pages = sutil.nbr_pages(data)
            page += 1
        return measures

    def is_a_rating(self) -> bool:
        return metrics.Metric.get_object(self.endpoint, self.metric).is_a_rating()

    def is_a_percent(self) -> bool:
        return metrics.Metric.get_object(self.endpoint, self.metric).is_a_percent()

    def is_an_effort(self) -> bool:
        return metrics.Metric.get_object(self.endpoint, self.metric).is_an_effort()

    def format(self, ratings: str = "letters", percents: str = "float") -> Any:
        return format(self.endpoint, self.metric, self.value, ratings=ratings, percents=percents)

    @classmethod
    def search(cls, concerned_object: ConcernedObject, metrics_list: KeyList, use_cache: bool = True, **search_params: Any) -> dict[str, Measure]:
        """Reads a list of measures of a component (project, branch, pull request, application or portfolio)

        :param Component concerned_object: Concerned object (project, branch, pull request, application or portfolio)
        :param KeyList metrics_list: List of metrics to read
        :param kwargs: List of filters to search for the measures, defaults to None
        :type kwargs: dict, optional
        :return: Dict of found measures
        :rtype: dict{<metric>: <value>}
        """
        log.debug("Searching measures with %s", search_params)
        branch = pull_request = None
        key = concerned_object.key
        if concerned_object.__class__.__name__ in ("Branch", "ApplicationBranch"):
            key = concerned_object.concerned_object.key
            branch = concerned_object.name
        elif concerned_object.__class__.__name__ == "PullRequest":
            key = concerned_object.concerned_object.key
            pull_request = concerned_object.key
        params = search_params | {"component": key, "metricKeys": util.list_to_csv(metrics_list), "branch": branch, "pullRequest": pull_request}
        api, _, params, ret = concerned_object.endpoint.api.get_details(cls, Oper.SEARCH, **params)
        response_data = json.loads(concerned_object.endpoint.get(api, params=params).text)[ret]
        measures_data = response_data["measures"]
        log.debug("Measures data = %s", util.json_dump(measures_data))

        # Determine branch and pull_request from concerned_object
        branch = pull_request = None
        component_key = concerned_object.key
        if concerned_object.__class__.__name__ == "Branch":
            component_key = concerned_object.concerned_object.key
            branch = concerned_object.name
        elif concerned_object.__class__.__name__ == "PullRequest":
            component_key = concerned_object.concerned_object.key
            pull_request = concerned_object.key

        m_dict = dict.fromkeys(metrics_list, None)
        addon_data = {cls.__CONCERNED_OBJECT: component_key, "branch": branch, "pull_request": pull_request}
        for m in measures_data:
            measure_obj = cls.load(concerned_object.endpoint, m | addon_data)
            measure_obj.concerned_object = concerned_object
            m_dict[m["metric"]] = measure_obj
        return m_dict


def get_history(concerned_object: object, metrics_list: KeyList, **kwargs) -> list[str, str, str]:
    """Reads the history of measures of a component (project, branch, application or portfolio)

    :param concerned_object: Concerned object (project, branch, pull request, application or portfolio)
    :type concerned_object: Project, Branch, PullRequest, Application or Portfolio
    :param KeyList metrics_list: List of metrics to read
    :param kwargs: List of filters to search for the measures history, defaults to None
    :type kwargs: dict, optional
    :return: List of found history of measures
    :rtype: list[<date>, <metricKey>, <value>]
    """
    # http://localhost:9999/api/measures/search_history?component=okorach_sonar-tools&metrics=ncloc&p=1&ps=1000

    params = kwargs | {"metrics": util.list_to_csv(metrics_list)}
    log.debug("Getting measures history with %s", str(params))
    api, _, params, ret = concerned_object.endpoint.api.get_details(Measure, Oper.GET_HISTORY, **params)
    data = json.loads(concerned_object.endpoint.get(api, params=params).text)[ret]
    res_list = []
    for m in reversed(data):
        res_list += [[dt["date"], m["metric"], dt["value"]] for dt in m["history"] if "value" in dt]
    return res_list


def get_rating_letter(rating: Union[float, str]) -> str:
    """
    :param any rating: The rating as repturned by the API (a str or float)
    :return: The rating converted from number to letter, if number between 1 and 5, else the unchanged rating
    :rtype: str
    """
    try:
        n_int = int(float(rating))
    except ValueError:
        return str(rating)
    return chr(n_int + 64) if 1 <= n_int <= 5 else str(rating)


def get_rating_number(rating_letter: str) -> int:
    """
    :return: The measure converted from letter to number, if letter in [a-eA-E]
    :rtype: int
    """
    if not isinstance(rating_letter, str):
        return int(rating_letter)
    l = rating_letter.upper()
    if l in ("A", "B", "C", "D", "E"):
        return ord(l) - 64
    return rating_letter


def format(endpoint: Platform, metric_key: str, value: Any, ratings: str = "letters", percents: str = "float") -> Any:
    """Formats a measure"""
    try:
        metric = metrics.Metric.get_object(endpoint, metric_key)
    except exceptions.ObjectNotFound:
        return value
    if metric.is_a_rating():
        return chr(int(float(value)) + 64) if ratings == "letters" else int(float(value))
    elif metric.is_a_percent():
        return float(f"{float(value)/100:.3f}") if percents == "float" else f"{float(value):.1f}%"
    return value


def _search_value(data: dict[str, str]) -> Any:
    """Searches a measure value in all possible field of a JSON returned by the Sonar API"""
    value = data.get("value", None)
    if not value and "periods" in data:
        value = data["periods"][0]["value"]
    elif not value and "period" in data:
        value = data["period"]["value"]
    return value
