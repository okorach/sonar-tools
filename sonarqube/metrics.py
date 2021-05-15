#
# sonar-tools
# Copyright (C) 2019-2021 Olivier Korach
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
import sonarqube.env as env
import sonarqube.sqobject as sq
import sonarqube.utilities as util


class Metric(sq.SqObject):
    Count = None
    Inventory = {}
    MAX_PAGE_SIZE = 500
    SEARCH_API = 'metrics/search'
    MAIN_METRICS = 'ncloc,bugs,reliability_rating,vulnerabilities,security_rating,code_smells,' + \
        'sqale_rating,sqale_index,coverage,duplicated_lines_density,new_bugs,new_vulnerabilities,new_code_smells,' + \
        'new_technical_debt,new_maintainability_rating,coverage,duplicated_lines_density,' + \
        'new_coverage,new_duplicated_lines_density'

    def __init__(self, key=None, endpoint=None, data=None):
        super().__init__(key=key, env=endpoint)
        self.id = None
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
            resp = env.get(Metric.SEARCH_API, params={'ps': 500}, ctxt=self.env)
            data_json = json.loads(resp.text)
            for m in data_json['metrics']:
                if self.key == m['key']:
                    data = m
                    break
        if data is None:
            return False
        util.logger.debug('Lading metric %s', str(data))
        self.id = data.get('id', None)
        self.type = data['type']
        self.name = data['name']
        self.description = data.get('description', '')
        self.domain = data.get('domain', '')
        self.qualitative = data['qualitative']
        self.hidden = data['hidden']
        self.custom = data['custom']
        return True

    def is_a_rating(self):
        return re.match(r"^(new_)?(security|security_review|reliability|maintainability)_rating$", self.key)


def count(endpoint):
    if Metric.Count is None:
        resp = env.get(Metric.SEARCH_API, params={'ps':1}, ctxt=endpoint)
        data = json.loads(resp.text)
        Metric.Count = data['total']
    return Metric.Count


def search(endpoint=None, page=None):
    if Metric.Inventory:
        return Metric.Inventory
    m_list = {}
    if page is not None:
        resp = env.get(Metric.SEARCH_API, params={'ps': 500, 'p': page}, ctxt=endpoint)
        data = json.loads(resp.text)
        for m in data['metrics']:
            m_list[m['key']] = Metric(key=m['key'], endpoint=endpoint, data=m)
    else:
        nb_metrics = count(endpoint)
        nb_pages = (nb_metrics + Metric.MAX_PAGE_SIZE - 1) // Metric.MAX_PAGE_SIZE
        for p in range(nb_pages):
            m_list.update(search(endpoint=endpoint, page=p + 1))
        Metric.Inventory = m_list
    return m_list


def as_csv(metric_list, separator=','):
    csv = ''
    for metric in metric_list:
        if metric.key == 'new_development_cost':
            # Skip new_development_cost metric to work around a SonarQube 7.9 bug
            continue
        csv = csv + "{0}{1}".format(metric.key, separator)
    return csv[:-1]


def is_a_rating(metric):
    return re.match(r"^(new_)?(security|security_review|reliability|maintainability)_rating$", metric)
