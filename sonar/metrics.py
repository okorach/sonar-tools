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

    Abstraction of the SonarQube "metric" concept

"""

import json
from sonar import sqobject, utilities

MAIN_METRICS = (
    "bugs",
    "vulnerabilities",
    "code_smells",
    "security_hotspots",
    "reliability_rating",
    "security_rating",
    "sqale_rating",
    "security_review_rating",
    "sqale_debt_ratio",
    "coverage",
    "duplicated_lines_density",
    "security_hotspots_reviewed",
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

METRICS_BY_TYPE = {}

APIS = {
    "search": "metrics/search",
}
__MAX_PAGE_SIZE = 500

_OBJECTS = {}
_VISIBLE_OBJECTS = {}

class Metric(sqobject.SqObject):
    Count = None

    def __init__(self, key=None, endpoint=None, data=None):
        super().__init__(key, endpoint)
        self.type = None
        self.name = None
        self.description = None
        self.domain = None
        self.direction = None
        self.qualitative = None
        self.hidden = None
        self.custom = None
        self.__load(data)
        _OBJECTS[self.key] = self

    def __load(self, data):
        if data is None:
            # TODO handle pagination
            data_json = json.loads(self.get(APIS["search"], params={"ps": 500}).text)
            for m in data_json["metrics"]:
                if self.key == m["key"]:
                    data = m
                    break
        if data is None:
            return False
        utilities.logger.debug("Loading metric %s", str(data))
        self.type = data["type"]
        self.name = data["name"]
        self.description = data.get("description", "")
        self.domain = data.get("domain", "")
        self.qualitative = data["qualitative"]
        self.hidden = data["hidden"]
        self.custom = data.get("custom", None)
        if not self.hidden:
            _VISIBLE_OBJECTS[self.key] = self
        if self.type not in METRICS_BY_TYPE:
            METRICS_BY_TYPE[self.type] = set()
            METRICS_BY_TYPE[self.type].add(self.key)
        return True

    def is_a_rating(self):
        return self.type == "RATING"

    def is_a_percent(self):
        return self.type == "PERCENT"

def is_of_type(metric_key, metric_type):
    return metric_key in METRICS_BY_TYPE[metric_key]

def is_a_rating(metric_key):
    return is_of_type(metric_key, "RATING")

def is_a_percent(metric_key):
    return is_of_type(metric_key, "PERCENT")

def count(endpoint):
    if len(_OBJECTS) is None:
        search(endpoint, True)
    return len(_VISIBLE_OBJECTS)

def search(endpoint, show_hidden_metrics=False):
    if len(_OBJECTS) == 0:
        m_list = {}
        page, nb_pages = 1, 1
        while page <= nb_pages:
            data = json.loads( endpoint.get(APIS["search"], params={"ps": __MAX_PAGE_SIZE, "p": page}).text)
            for m in data["metrics"]:
                m_list[m["key"]] = Metric(key=m["key"], endpoint=endpoint, data=m)
            nb_pages = utilities.nbr_pages(data)
            page += 1

    return _OBJECTS if show_hidden_metrics else _VISIBLE_OBJECTS


def as_csv(metric_list, separator=","):
    return separator.join([m.key for m in metric_list if m.key != "new_development_cost"])
