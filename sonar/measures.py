#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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
from sonar.api.manager import ApiManager as Api, ApiOperation as op
from sonar.util.types import ApiPayload, ApiParams, KeyList
from sonar.util import cache, constants as c
import sonar.logging as log
import sonar.util.misc as util
import sonar.utilities as sutil

if TYPE_CHECKING:
    from sonar.platform import Platform

ALT_COMPONENTS = ("project", "application", "portfolio", "key")

DATETIME_METRICS = ("last_analysis", "createdAt", "updatedAt", "creation_date", "modification_date")


class Measure(SqObject):
    """
    Abstraction of the SonarQube "measure" concept
    """

    CACHE = cache.Cache()

    def __init__(self, concerned_object: object, key: str, value: Any) -> None:
        """Constructor"""
        super().__init__(endpoint=concerned_object.endpoint, key=key)
        self.value: Optional[Any] = None  #: Measure value
        self.metric = key  #: Measure metric
        self.concerned_object = concerned_object  #: Object concerned by the measure
        self.value = self.__converted_value(value)

    @classmethod
    def load(cls, concerned_object: object, data: ApiPayload) -> Measure:
        """Loads a measure from data

        :param endpoint: Reference to SonarQube platform
        :paramm data: Data retrieved from a measure search
        :return: The created measure
        :rtype: Measure
        """
        metrics.Metric.search(concerned_object.endpoint)
        return cls(concerned_object=concerned_object, key=data["metric"], value=_search_value(data))

    def __converted_value(self, value: Any) -> Any:
        value = sutil.string_to_date(value) if self.metric in DATETIME_METRICS else util.convert_to_type(value)
        if self.is_a_rating():
            value = int(float(value))
        return value

    def refresh(self) -> Any:
        """Refreshes a measure by re-reading it in SonarQube

        :return: The new measure value
        :rtype: int or float or str
        """
        params = {"metricKeys": self.metric} | util.replace_keys(ALT_COMPONENTS, "component", self.concerned_object.api_params(op.GET))
        api_def = Api(self, op.READ)
        api, _, params, ret = api_def.get_all(**params)
        data = json.loads(self.endpoint.get(api, params=params).text)[ret]["measures"]
        self.value = self.__converted_value(_search_value(data[0]))
        return self.value

    def count_history(self, params: Optional[ApiParams] = None) -> int:
        """Returns the number of measures in history of the metric"""
        new_params = params or {}
        new_params |= {"component": self.concerned_object.key, "metrics": self.metric, "ps": 1}
        api_def = Api(self, op.GET_HISTORY)
        api, _, new_params, _ = api_def.get_all(**new_params)
        return sutil.nbr_total_elements(json.loads(self.endpoint.get(api, params=new_params).text))

    def search_history(self, params: Optional[ApiParams] = None) -> dict[str, Any]:
        """Searches the history of the measure

        :param params: List of search parameters to narrow down the search, defaults to None
        :return: The history of the metric, attached to the given component
        """
        __MAX_PAGE_SIZE = 1000
        measures = {}
        page, nbr_pages = 1, 1
        api_def = Api(self, op.GET_HISTORY)
        p_field = api_def.page_field()
        new_params = params or {}
        new_params |= {"component": self.concerned_object.key, "metrics": self.metric, "ps": __MAX_PAGE_SIZE}
        api, _, new_params, ret = api_def.get_all(**new_params)
        while page <= nbr_pages:
            data = json.loads(self.endpoint.get(api, params=new_params | {p_field: page}).text)
            measures |= {m["date"]: m["value"] for m in data[ret][0]["history"]}
            nbr_pages = sutil.nbr_pages(data)
            page += 1
        return measures

    def is_a_rating(self) -> bool:
        return metrics.Metric.get_object(self.endpoint, self.key).is_a_rating()

    def is_a_percent(self) -> bool:
        return metrics.Metric.get_object(self.endpoint, self.key).is_a_percent()

    def is_an_effort(self) -> bool:
        return metrics.Metric.get_object(self.endpoint, self.key).is_an_effort()

    def format(self, ratings: str = "letters", percents: str = "float") -> Any:
        return format(self.endpoint, self.key, self.value, ratings=ratings, percents=percents)


def get(concerned_object: object, metrics_list: KeyList, **kwargs) -> dict[str, Measure]:
    """Reads a list of measures of a component (project, branch, pull request, application or portfolio)

    :param Component concerned_object: Concerned object (project, branch, pull request, application or portfolio)
    :param KeyList metrics_list: List of metrics to read
    :param kwargs: List of filters to search for the measures, defaults to None
    :type kwargs: dict, optional
    :return: Dict of found measures
    :rtype: dict{<metric>: <value>}
    """
    params = (
        kwargs | util.replace_keys(ALT_COMPONENTS, "component", concerned_object.api_params(op.GET)) | {"metricKeys": util.list_to_csv(metrics_list)}
    )
    log.debug("Getting measures with %s", params)
    api_def = Api(Measure, op.READ, concerned_object.endpoint)
    api, _, params, ret = api_def.get_all(**params)
    data = json.loads(concerned_object.endpoint.get(api, params=params).text)[ret]["measures"]
    m_dict = dict.fromkeys(metrics_list, None) | {m["metric"]: Measure.load(concerned_object=concerned_object, data=m) for m in data}
    log.debug("Returning measures %s", m_dict)
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

    params = (
        kwargs | util.replace_keys(ALT_COMPONENTS, "component", concerned_object.api_params(op.GET)) | {"metricKeys": util.list_to_csv(metrics_list)}
    )
    log.debug("Getting measures history with %s", str(params))
    api_def = Api(Measure, op.GET_HISTORY, concerned_object.endpoint)
    api, _, params, ret = api_def.get_all(**params)
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
