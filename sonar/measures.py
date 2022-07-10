#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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
import re
from sonar import metrics
import sonar.utilities as util
import sonar.sqobject as sq


class Measure(sq.SqObject):
    """
    Abstraction of the SonarQube "measure" concept
    """

    API_ROOT = "measures"
    API_COMPONENT = API_ROOT + "/component"
    API_HISTORY = API_ROOT + "/search_history"

    def __init__(self, key=None, value=None, endpoint=None):
        super().__init__(key, endpoint)
        self.value = None  #: Measure value
        self.value = get_rating_letter(value) if metrics.is_a_rating(self.key) else value

    def read(self, project_key, metric_key):
        resp = self.get(Measure.API_COMPONENT, {"component": project_key, "metricKeys": metric_key})
        data = json.loads(resp.text)
        return data["component"]["measures"]

    def count_history(self, project_key, params=None):
        if params is None:
            params = {}
        params.update({"component": project_key, "metrics": self.key, "ps": 1})
        resp = self.get(Measure.API_HISTORY, params=params)
        data = json.loads(resp.text)
        return data["paging"]["total"]

    def search_history(self, project_key, params=None):
        """Searches the history of the metric, for a given project

        :param project_key: Project key
        :type project_key: str
        :param params: List of search parameters to narrow down the search, defaults to None
        :type params: dict
        :return: The history of the metric, for a given project
        :rtype dict: {<date_str>: <value>}
        """
        __MAX_PAGE_SIZE = 1000
        measures = {}
        new_params = {} if params is None else params.copy()
        new_params.update({"metrics": self.key, "component": project_key})
        if "ps" not in new_params:
            new_params["ps"] = __MAX_PAGE_SIZE
        page, nbr_pages = 1, 1
        while page <= nbr_pages:
            data = json.loads(self.get(Measure.API_HISTORY, params=new_params))
            for m in data["measures"][0]["history"]:
                measures[m["date"]] = m["value"]
            nbr_pages = util.nbr_pages(data)
            page += 1
        return measures


def get(comp_key, metrics_list, endpoint, branch=None, pr_key=None, **kwargs):
    """Reads measures of a component (project or any subcomponent)

    :param comp_key: Component key
    :type comp_key: str
    :param metrics_list: List of metrics to read
    :type metrics_list: list
    :param endpoint: Reference to the SonarQube platform
    :type endpoint: Platform
    :param branch: Branch of the component, defaults to None
    :type branch: str, optional
    :param pr_key: Pull request key of the component, defaults to None
    :type pr_key: str, optional
    :param kwargs: List of filters to search for the measures, defaults to None
    :type kwargs: dict, optional
    :return: Dict of found measures
    :rtype: dict{<metric>: <value>}
    """
    util.logger.debug("For component %s, branch %s, PR %s, getting measures %s", comp_key, branch, pr_key, metrics_list)
    if isinstance(metrics_list, str):
        metrics_str = metrics_list
        metrics_list = util.csv_to_list(metrics_str)
    else:
        metrics_str = util.list_to_csv(metrics_list)
    params = {"component": comp_key, "metricKeys": metrics_str}
    if branch is not None:
        params["branch"] = branch
    elif pr_key is not None:
        params["pullRequest"] = pr_key

    data = json.loads(endpoint.get(Measure.API_COMPONENT, params={**kwargs, **params}).text)
    m_dict = {m: None for m in metrics_list}
    for m in data["component"]["measures"]:
        value = m.get("value", "")
        if value == "" and "periods" in m:
            value = m["periods"][0]["value"]
        if metrics.is_a_rating(m["metric"]):
            value = get_rating_letter(value)
        m_dict[m["metric"]] = value

    return m_dict


def get_rating_letter(rating_number_str):
    """
    :return: The measure converted from number to letter, if number between 1 and 5
    :rtype: str
    """
    try:
        n_int = int(float(rating_number_str))
        return chr(n_int + 64)
    except ValueError:
        util.logger.error("Wrong numeric rating provided %s", rating_number_str)
        return rating_number_str


def get_rating_number(rating_letter):
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


def as_rating_letter(metric, value):
    """
    :param metric: Metric key
    :type metric: str
    :param value: Measure value to convert
    :type value: float or int
    :return: The measure converted from number to letter, if metric is a rating
    :rtype: str
    """
    if metric in metrics.Metric.RATING_METRICS and value not in ("A", "B", "C", "D", "E"):
        return get_rating_letter(value)
    return value


def as_rating_number(metric, value):
    """
    :param metric: Metric key
    :type metric: str
    :param value: Measure value to convert
    :type value: str (A to E)
    :return: The measure converted from letter to number, if metric is a rating
    :rtype: int
    """
    if metric in metrics.Metric.RATING_METRICS:
        return get_rating_number(value)
    return value


def as_ratio(metric, value):
    """Converts a density or ratio metric to float percentage
    :param metric: Metric key
    :type metric: str
    :param value: Measure value to convert
    :type value: int or float
    :return: The converted ratio or density
    :rtype: float between 0 and 1 (0% and 100%)
    """
    try:
        if re.match(r".*(ratio|density|coverage)", metric):
            # Return pct with 3 significant digits
            value = int(float(value) * 10) / 1000.0
    except ValueError:
        pass
    return value


def as_percent(metric, value):
    """Converts a density or ratio metric to string percentage
    :param metric: Metric key
    :type metric: str
    :param value: Measure value to convert
    :type value: int or float
    :return: The converted ratio or density in "x.y%" format
    :rtype: str
    """
    try:
        if re.match(r".*(ratio|density|coverage)", metric):
            # Return pct with one digit after decimals
            value = str(int(float(value) * 10) / 10.0) + "%"
    except ValueError:
        pass
    return value


def convert(metric, value, ratings="letters", percents="float", dates="datetime"):
    """Converts any metric in the teh preferred format for display

    :param metric: Metric key
    :type metric: str
    :param value: Measure value to convert
    :type value: str, int or float
    :param ratings: How to convert ratings
    :type ratings: str, "letters" or "numbers"
    :param percents: How to convert percentages
    :type percents: str, "float" or "percents"
    :param dates: How to convert dates
    :type dates: str, "datetime" or "dateonly"
    :return: The converted measure
    :rtype: str
    """
    value = util.convert_to_type(value)
    value = as_rating_number(metric, value) if ratings == "numbers" else as_rating_letter(metric, value)
    value = as_percent(metric, value) if percents == "percents" else as_ratio(metric, value)
    if dates == "dateonly" and metric in ("last_analysis", "createdAt", "updatedAt", "creation_date", "modification_date"):
        value = util.date_to_string(util.string_to_date(value), False)
    return value
