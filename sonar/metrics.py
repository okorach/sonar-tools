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
'''

    Abstraction of the SonarQube "metric" concept

'''
import re
import json
from sonar import env
import sonar.sqobject as sq
import sonar.utilities as util


class Metric(sq.SqObject):
    Count = None
    Inventory = {}
    MAX_PAGE_SIZE = 500
    SEARCH_API = 'metrics/search'
    MAIN_METRICS = (
        'bugs', 'vulnerabilities', 'code_smells', 'security_hotspots',
        'reliability_rating', 'security_rating', 'sqale_rating', 'security_review_rating',
        'sqale_debt_ratio', 'coverage', 'duplicated_lines_density', 'security_hotspots_reviewed',
        'new_bugs', 'new_vulnerabilities', 'new_code_smells', 'new_security_hotspots',
        'new_reliability_rating', 'new_security_rating', 'new_maintainability_rating', 'new_security_review_rating',
        'new_sqale_debt_ratio', 'new_coverage', 'new_duplicated_lines_density', 'new_security_hotspots_reviewed',
        'ncloc'
    )

    RATING_METRICS = ('sqale_rating', 'new_maintainability_rating',
                      'security_rating', 'new_security_rating',
                      'reliability_rating', 'new_reliability_rating',
                      'security_review_rating', 'new_security_review_rating')

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
        self.__load__(data)

    def __load__(self, data):
        if data is None:
            # TODO handle pagination
            resp = env.get(Metric.SEARCH_API, params={'ps': 500}, ctxt=self.endpoint)
            data_json = json.loads(resp.text)
            for m in data_json['metrics']:
                if self.key == m['key']:
                    data = m
                    break
        if data is None:
            return False
        util.logger.debug('Loading metric %s', str(data))
        self.type = data['type']
        self.name = data['name']
        self.description = data.get('description', '')
        self.domain = data.get('domain', '')
        self.qualitative = data['qualitative']
        self.hidden = data['hidden']
        self.custom = data.get('custom', None)
        return True

    def is_a_rating(self):
        return re.match(r"^(new_)?(security|security_review|reliability|maintainability)_rating$", self.key)


def count(endpoint):
    if Metric.Count is None:
        resp = env.get(Metric.SEARCH_API, params={'ps': 1}, ctxt=endpoint)
        data = json.loads(resp.text)
        Metric.Count = data['total']
    return Metric.Count


def search(endpoint=None, page=None, skip_hidden_metrics=True):
    if not Metric.Inventory:
        m_list = {}
        if page is not None:
            resp = env.get(Metric.SEARCH_API, params={'ps': 500, 'p': page}, ctxt=endpoint)
            data = json.loads(resp.text)
            for m in data['metrics']:
                m_list[m['key']] = Metric(key=m['key'], endpoint=endpoint, data=m)
            return m_list
        else:
            nb_metrics = count(endpoint)
            nb_pages = (nb_metrics + Metric.MAX_PAGE_SIZE - 1) // Metric.MAX_PAGE_SIZE
            for p in range(nb_pages):
                m_list.update(search(endpoint=endpoint, page=p + 1))
            Metric.Inventory = m_list
    final_list = {}
    for k, v in Metric.Inventory.items():
        if skip_hidden_metrics and v.hidden:
            continue
        final_list[k] = v
    return final_list


def as_csv(metric_list, separator=','):
    csv = ''
    for metric in metric_list:
        if metric.key == 'new_development_cost':
            # Skip new_development_cost metric to work around a SonarQube 7.9 bug
            continue
        csv = csv + f"{metric.key}{separator}"
    return csv[:-1]


def is_a_rating(metric):
    return re.match(r"^(new_)?(security|security_review|reliability|maintainability)_rating$", metric)
