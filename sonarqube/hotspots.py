#
# sonar-tools
# Copyright (C) 2022 Olivier Korach
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

    Abstraction of the SonarQube "hotspot" concept

'''

import json
import requests.utils
import sonarqube.sqobject as sq
import sonarqube.utilities as util
from sonarqube import env, projects, findings


_JSON_FIELDS_REMAPPED = (
    ('pull_request', 'pullRequest'),
    ('_comments', 'comments')
)

_JSON_FIELDS_PRIVATE = ('endpoint', 'id', '_json', '_changelog', 'assignee', 'hash', 'sonarqube',
    'creation_date', 'modification_date', '_debt', 'component', 'language', 'resolution')

_CSV_FIELDS = ('key', 'rule', 'type', 'severity', 'status', 'createdAt', 'updatedAt', 'projectKey', 'projectName',
            'branch', 'pullRequest', 'file', 'line', 'effort', 'message')

_HOTSPOTS = {}


class TooManyHotspotsError(Exception):
    def __init__(self, nbr_issues, message):
        super().__init__()
        self.nbr_issues = nbr_issues
        self.message = message

class Hotspot(findings.Finding):

    def __init__(self, key, endpoint, data=None, from_export=False):
        super().__init__(key, endpoint, data, from_export)
        self.vulnerabilityProbability = None
        self.securityCategory = None
        self.type = 'SECURITY_HOTSPOT'
        if data is not None:
            self.category = data['securityCategory']
            self.vulnerabilityProbability = data['vulnerabilityProbability']
        _HOTSPOTS[self.uuid()] = self

    def __str__(self):
        return f"Hotspot key '{self.key}'"

    def url(self):
        branch = ''
        if self.branch is not None:
            branch = f'branch={requests.utils.quote(self.branch)}&'
        elif self.pull_request is not None:
            branch = f'pullRequest={requests.utils.quote(self.pull_request)}&'
        return f'{self.endpoint.url}/security_hotspots?{branch}id={self.projectKey}&hotspots={self.key}'

    def to_json(self):
        data = super().to_json()
        data['url'] = self.url()
        return data


def search_by_project(project_key, endpoint=None, branch=None, pull_request=None):
    new_params = {}
    if project_key is None:
        key_list = projects.search(endpoint).keys()
    else:
        key_list = util.csv_to_list(project_key)
    hotspots = {}
    if branch is not None:
        new_params['branch'] = branch
        key_list = [key_list[0]]
    elif pull_request is not None:
        new_params['pullRequest'] = pull_request
        key_list = [key_list[0]]

    for k in key_list:
        util.logger.info("Hotspots search by project %s branch %s PR %s", k, branch, pull_request)
        new_params['projectKey'] = k
        project_hotspots = search(endpoint=endpoint, params=new_params)
        util.logger.info("Project %s branch %s has %d hotspots", k, str(branch), len(project_hotspots))
        hotspots.update(project_hotspots)
    return hotspots


def search(endpoint=None, page=None, params=None):
    if params is None:
        new_params = {}
    else:
        new_params = params.copy()
    new_params['ps'] = 500
    p = 1
    hotspots = {}
    while True:
        if page is None:
            new_params['p'] = p
        else:
            new_params['p'] = page
        resp = env.get('hotspots/search', params=new_params, ctxt=endpoint)
        data = json.loads(resp.text)
        nbr_hotspots = data['paging']['total']
        nbr_pages = (nbr_hotspots + 499) // 500
        util.logger.debug("Number of issues: %d - Page: %d/%d", nbr_hotspots, new_params['p'], nbr_pages)
        if page is None and nbr_hotspots > 10000:
            raise TooManyHotspotsError(nbr_hotspots,
                                     f'{nbr_hotspots} hotpots returned by api/hotspots/search, '
                                     'this is more than the max 10000 possible')

        for i in data['hotspots']:
            hotspots[i['key']] = get_object(i['key'], endpoint=endpoint, data=i)
        if page is not None or p >= nbr_pages:
            break
        p += 1
    return hotspots


def get_object(key, data=None, endpoint=None, from_export=False):
    if key not in _HOTSPOTS:
        _ = Hotspot(key=key, data=data, endpoint=endpoint, from_export=from_export)
    return _HOTSPOTS[key]
