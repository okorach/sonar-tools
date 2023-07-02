#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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

DATETIME_METRICS = ("last_analysis", "createdAt", "updatedAt", "creation_date", "modification_date")


class Measure(sq.SqObject):
    """
    Abstraction of the SonarQube "measure" concept
    """

    API_READ = "measures/component"
    API_HISTORY = "measures/search_history"

    @classmethod
    def load(cls, concerned_object, data):
        """Loads a measure from data

        :param endpoint: Reference to SonarQube platform
        :type endpoint: Platform
        :paramm data: Data retrieved from a measure search
        :type data: dict
        :return: The created measure
        :rtype: Measure
        """
        metrics.search(concerned_object.endpoint)
        return cls(key=data["metric"], value=_search_value(data), concerned_object=concerned_object)

    def __init__(self, key, value, concerned_object):
        super().__init__(key, concerned_object.endpoint)
        self.value = None  #: Measure value
        self.metric = key  #: Measure metric
        self.concerned_object = concerned_object  #: Object concerned by the measure
        self.value = util.string_to_date(value) if self.metric in DATETIME_METRICS else util.convert_to_type(value)

    def refresh(self):
        """Refreshes a measure by re-reading it in SonarQube

        :return: The new measure value
        :rtype: int or float or str
        """
        params = util.replace_keys(("project", "application", "portfolio"), "component", self.concerned_object.search_params())
        data = json.loads(self.get(Measure.API_READ, params=params).text)["component"]["measures"]
        self.value = _search_value(data)
        return self.value

    def count_history(self, project_key, params=None):
        if params is None:
            params = {}
        params.update({"component": project_key, "metrics": self.metric, "ps": 1})
        data = json.loads(self.get(Measure.API_HISTORY, params=params).text)
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
            data = json.loads(self.get(Measure.API_HISTORY, params=new_params).text)
            for m in data["measures"][0]["history"]:
                measures[m["date"]] = m["value"]
            nbr_pages = util.nbr_pages(data)
            page += 1
        return measures


def get(concerned_object, metrics_list, **kwargs):
    """Reads a list of measures of a component (project, branch, pull request, application or portfolio)

    :param concerned_object: Concerned object (project, branch, pull request, application or portfolio)
    :type concerned_object: Project, Branch, PullRequest, Application or Portfolio
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
    params = util.replace_keys(("project", "application", "portfolio"), "component", concerned_object.search_params())
    params["metricKeys"] = util.list_to_csv(metrics_list)
    util.logger.debug("Getting measures with %s", str(params))

    data = json.loads(concerned_object.endpoint.get(Measure.API_READ, params={**kwargs, **params}).text)
    m_dict = {m: None for m in metrics_list}
    for m in data["component"]["measures"]:
        m_dict[m["metric"]] = Measure.load(data=m, concerned_object=concerned_object)
    return m_dict


def get_rating_letter(rating):
    """
    :params rating:
    :type rating: int
    :return: The rating converted from number to letter, if number between 1 and 5, else the unchanged rating
    :rtype: str
    """
    try:
        n_int = int(float(rating))
    except ValueError:
        return rating
    return chr(n_int + 64) if 1 <= n_int <= 5 else rating


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
    if metric in metrics.METRICS_BY_TYPE["RATING"] and value not in ("A", "B", "C", "D", "E"):
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
    if metric in metrics.METRICS_BY_TYPE["RATING"]:
        return get_rating_number(value)
    return value


def as_ratio(metric, value):
    """Converts a density or ratio metric to float percentage
    :param metric: Metric key
    :type metric: str
    :param value: Measure value to convert
    :type value: int or float
    :return: The converted ratio or density
    :rtype: float between 0 and 1 (0% and 100%), rounded to first decimal
    """
    if metric in metrics.METRICS_BY_TYPE["PERCENT"]:
        try:
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


def format(metric, value, ratings="letters", percents="float", dates="datetime"):
    """Formats any metric in the the preferred format for display

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
    :return: The formatted measure
    :rtype: str
    """
    if metrics.is_a_rating(metric):
        value = as_rating_letter(metric, value) if ratings == "letters" else as_rating_number(metric, value)
    elif metrics.is_a_percent(metric):
        value = as_percent(metric, value) if percents == "percents" else as_ratio(metric, value)
    elif dates == "dateonly" and metric in ("last_analysis", "createdAt", "updatedAt", "creation_date", "modification_date"):
        value = util.date_to_string(util.string_to_date(value), False)
    return value


def _search_value(data):
    value = data.get("value", None)
    if not value and "periods" in data:
        value = data["periods"][0]["value"]
    elif not value and "period" in data:
        value = data["period"]["value"]
    if metrics.is_a_rating(data["metric"]):
        value = get_rating_letter(value)
    return value
