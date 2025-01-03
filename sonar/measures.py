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

from typing import Union

import json
import re
from http import HTTPStatus
from requests import RequestException
from sonar import metrics, exceptions, platform
from sonar.util.types import ApiPayload, ApiParams, KeyList
from sonar.util import cache, constants as c
import sonar.logging as log
import sonar.utilities as util
import sonar.sqobject as sq

ALT_COMPONENTS = ("project", "application", "portfolio", "key")

DATETIME_METRICS = ("last_analysis", "createdAt", "updatedAt", "creation_date", "modification_date")


class Measure(sq.SqObject):
    """
    Abstraction of the SonarQube "measure" concept
    """

    CACHE = cache.Cache()
    API_READ = "measures/component"
    API_HISTORY = "measures/search_history"

    def __init__(self, concerned_object: object, key: str, value: any) -> None:
        """Constructor"""
        super().__init__(endpoint=concerned_object.endpoint, key=key)
        self.value = None  #: Measure value
        self.metric = key  #: Measure metric
        self.concerned_object = concerned_object  #: Object concerned by the measure
        self.value = self.__converted_value(value)

    @classmethod
    def load(cls, concerned_object: object, data: ApiPayload) -> Measure:
        """Loads a measure from data

        :param endpoint: Reference to SonarQube platform
        :type endpoint: Platform
        :paramm data: Data retrieved from a measure search
        :type data: dict
        :return: The created measure
        :rtype: Measure
        """
        metrics.search(concerned_object.endpoint)
        return cls(concerned_object=concerned_object, key=data["metric"], value=_search_value(data))

    def __converted_value(self, value: any) -> any:
        value = util.string_to_date(value) if self.metric in DATETIME_METRICS else util.convert_to_type(value)
        if self.is_a_rating():
            value = int(float(value))
        return value

    def refresh(self) -> any:
        """Refreshes a measure by re-reading it in SonarQube

        :return: The new measure value
        :rtype: int or float or str
        """
        params = util.replace_keys(ALT_COMPONENTS, "component", self.concerned_object.api_params(c.GET))
        data = json.loads(self.get(Measure.API_READ, params=params).text)["component"]["measures"]
        self.value = self.__converted_value(_search_value(data))
        return self.value

    def count_history(self, params: ApiParams = None) -> int:
        if params is None:
            params = {}
        params.update({"component": self.concerned_object.key, "metrics": self.metric, "ps": 1})
        return util.nbr_total_elements(json.loads(self.get(Measure.API_HISTORY, params=params).text))

    def search_history(self, params: ApiParams = None) -> dict[str, any]:
        """Searches the history of the measure

        :param dict params: List of search parameters to narrow down the search, defaults to None
        :return: The history of the metric, attached to the givene component
        :rtype dict: {<date_str>: <value>}
        """
        __MAX_PAGE_SIZE = 1000
        measures = {}
        new_params = {} if params is None else params.copy()
        new_params.update({"metrics": self.key, "component": self.concerned_object.key})
        if "ps" not in new_params:
            new_params["ps"] = __MAX_PAGE_SIZE
        page, nbr_pages = 1, 1
        while page <= nbr_pages:
            data = json.loads(self.get(Measure.API_HISTORY, params=new_params).text)
            for m in data["measures"][0]["history"]:
                measures[m["date"]] = m["value"]
            nbr_pages = util.nbr_pages(data)
            page += 1
        return measures

    def is_a_rating(self) -> bool:
        return metrics.is_a_rating(self.endpoint, self.key)

    def is_a_percent(self) -> bool:
        return metrics.is_a_percent(self.endpoint, self.key)

    def is_an_effort(self) -> bool:
        return metrics.is_an_effort(self.endpoint, self.key)

    def format(self, ratings: str = "letters", percents: str = "float") -> any:
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
    params = util.replace_keys(ALT_COMPONENTS, "component", concerned_object.api_params(c.GET))
    params["metricKeys"] = util.list_to_csv(metrics_list)
    log.debug("Getting measures with %s", str(params))

    try:
        data = json.loads(concerned_object.endpoint.get(Measure.API_READ, params={**kwargs, **params}).text)
    except (ConnectionError, RequestException) as e:
        util.handle_error(e, f"getting measures {str(metrics_list)} of {str(concerned_object)}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
        raise exceptions.ObjectNotFound(concerned_object.key, f"{str(concerned_object)} not found")
    m_dict = {m: None for m in metrics_list}
    for m in data["component"]["measures"]:
        m_dict[m["metric"]] = Measure.load(data=m, concerned_object=concerned_object)
    log.debug("Returning measures %s", str(m_dict))
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

    params = util.replace_keys(ALT_COMPONENTS, "component", concerned_object.api_params(c.GET))
    params["metrics"] = util.list_to_csv(metrics_list)
    log.debug("Getting measures history with %s", str(params))

    try:
        data = json.loads(concerned_object.endpoint.get(Measure.API_HISTORY, params={**kwargs, **params}).text)
    except (ConnectionError, RequestException) as e:
        util.handle_error(e, f"getting measures {str(metrics_list)} history of {str(concerned_object)}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
        raise exceptions.ObjectNotFound(concerned_object.key, f"{str(concerned_object)} not found")
    res_list = []
    for m in reversed(data["measures"]):
        res_list += [[dt["date"], m["metric"], dt["value"]] for dt in m["history"] if "value" in dt]
    return res_list


def get_rating_letter(rating: any) -> str:
    """
    :param any rating: The rating as repturned by the API (a str or float)
    :return: The rating converted from number to letter, if number between 1 and 5, else the unchanged rating
    :rtype: str
    """
    try:
        n_int = int(float(rating))
    except ValueError:
        return rating
    return chr(n_int + 64) if 1 <= n_int <= 5 else rating


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


def format(endpoint: platform.Platform, metric_key: str, value: any, ratings: str = "letters", percents: str = "float") -> any:
    """Formats a measure"""
    try:
        metric = metrics.Metric.get_object(endpoint, metric_key)
    except exceptions.ObjectNotFound:
        return value
    if metric.is_a_rating():
        return chr(int(float(value)) + 64) if ratings == "letters" else int(float(value))
    elif metric.is_a_percent():
        return f"{float(value)/100:.3f}" if percents == "float" else f"{float(value):.1f}%"
    return value


def _search_value(data: dict[str, str]) -> any:
    """Searches a measure value in all possible field of a JSON returned by the Sonar API"""
    value = data.get("value", None)
    if not value and "periods" in data:
        value = data["periods"][0]["value"]
    elif not value and "period" in data:
        value = data["period"]["value"]
    return value
