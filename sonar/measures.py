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
"""

    Abstraction of the SonarQube "measure" concept

"""
import json
import re
from sonar import env, metrics
import sonar.utilities as util
import sonar.sqobject as sq


class Measure(sq.SqObject):
    API_ROOT = "measures"
    API_COMPONENT = API_ROOT + "/component"
    API_HISTORY = API_ROOT + "/search_history"

    def __init__(self, key=None, value=None, endpoint=None):
        super().__init__(key, endpoint)
        if metrics.is_a_rating(self.key):
            self.value = get_rating_letter(value)
        else:
            self.value = value
        self.history = None

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


def get(comp_key, metrics_list, endpoint=None, branch=None, pr_key=None, as_list=False, **kwargs):
    util.logger.debug(
        "For component %s, branch %s, PR %s, getting measures %s",
        comp_key,
        branch,
        pr_key,
        metrics_list,
    )
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

    resp = env.get(Measure.API_COMPONENT, params={**kwargs, **params}, ctxt=endpoint)
    data = json.loads(resp.text)
    m_dict, m_list = {}, []
    for m in metrics_list:
        m_dict[m] = None
        m_list.append(None)
    for m in data["component"]["measures"]:
        value = m.get("value", "")
        if value == "" and "periods" in m:
            value = m["periods"][0]["value"]
        if metrics.is_a_rating(m["metric"]):
            value = get_rating_letter(value)
        if not as_list:
            m_dict[m["metric"]] = value
        else:
            try:
                m_list[metrics_list.index(m["metric"])] = value
            except ValueError:
                pass

    if as_list:
        return m_list
    else:
        return m_dict


def get_rating_letter(rating_number_str):
    try:
        n_int = int(float(rating_number_str))
        return chr(n_int + 64)
    except ValueError:
        util.logger.error("Wrong numeric rating provided %s", rating_number_str)
        return rating_number_str


def get_rating_number(rating_letter):
    if not isinstance(rating_letter, str):
        return int(rating_letter)
    l = rating_letter.upper()
    if l in ("A", "B", "C", "D", "E"):
        return ord(l) - 64
    return rating_letter


def as_rating_letter(metric, value):
    if metric in metrics.Metric.RATING_METRICS and value not in (
        "A",
        "B",
        "C",
        "D",
        "E",
    ):
        return get_rating_letter(value)
    return value


def as_rating_number(metric, value):
    if metric in metrics.Metric.RATING_METRICS:
        return get_rating_number(value)
    return value


def as_ratio(metric, value):
    try:
        if re.match(r".*(ratio|density)", metric):
            # Return pct with 3 significant digits
            value = int(float(value) * 10) / 1000.0
    except ValueError:
        pass
    return value


def as_percent(metric, value):
    try:
        if re.match(r".*(ratio|density|coverage)", metric):
            # Return pct with 3 significant digits
            value = str(int(float(value) * 10) / 10.0) + "%"
    except ValueError:
        pass
    return value


def convert(metric, value, ratings="letters", percents="float", dates="datetime"):
    value = util.convert_to_type(value)
    if ratings == "numbers":
        value = as_rating_number(metric, value)
    else:
        value = as_rating_letter(metric, value)
    if percents == "percents":
        value = as_percent(metric, value)
    else:
        value = as_ratio(metric, value)
    if dates == "dateonly" and metric in (
        "last_analysis",
        "createdAt",
        "updatedAt",
        "creation_date",
        "modification_date",
    ):
        value = util.date_to_string(util.string_to_date(value), False)
    return value
