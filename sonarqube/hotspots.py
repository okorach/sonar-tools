#
# sonar-tools
# Copyright (C) 2021 Olivier Korach
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
import sonarqube.sqobject as sq
import sonarqube.utilities as util
from sonarqube import env, projects


class TooManyHotspotsError(Exception):
    def __init__(self, nbr_issues, message):
        super().__init__()
        self.nbr_issues = nbr_issues
        self.message = message

class Hotspot(sq.SqObject):

    def __init__(self, key, endpoint, data=None, from_findings=False):
        super().__init__(key, endpoint)
        self._url = None
        self._json = None
        self.vulnerabilityProbability = None
        self.securityCategory = None
        self.file = None
        self.author = None
        self.status = None
        self.rule = None
        self.projectKey = None
        self.line = None
        self.message = None
        self.creation_date = None
        self.modification_date = None
        self.author = None
        self.branch = None
        if data is not None:
            if from_findings:
                self.__load_finding(data)
            else:
                self.__load(data)

    def __str__(self):
        return f"Hotspot key '{self.key}'"

    def __load(self, jsondata):
        self.__load_common(jsondata)
        self.author = jsondata['author']
        self.projectKey = jsondata['project']
        self.creation_date = util.string_to_date(jsondata['creationDate'])
        self.modification_date = util.string_to_date(jsondata['updateDate'])
        self.file = jsondata['component'].split(":")[-1]
        self.hash = jsondata.get('hash', None)
        self.branch = jsondata.get('branch', None)
        self.category = jsondata['securityCategory']
        self.vulnerabilityProbability = jsondata['vulnerabilityProbability']

    def __load_finding(self, jsondata):
        self.__load_common(jsondata)
        self.projectKey = jsondata['projectKey']
        self.creation_date = util.string_to_date(jsondata['createdAt'])
        self.modification_date = util.string_to_date(jsondata['updatedAt'])
        self.file = jsondata['path']

    def __load_common(self, jsondata):
        self._json = jsondata
        self.vulnerabilityProbability = jsondata.get('vulnerabilityProbability', None)
        self.line = jsondata.get('line', jsondata.get('lineNumber', None))
        self.rule = jsondata.get('rule', jsondata.get('ruleReference', None))
        self.message = jsondata.get('message', None)
        self.status = jsondata['status']

    def url(self):
        if self._url is None:
            branch = ''
            if self.branch is not None:
                branch = f'branch={self.branch}&'
            self._url = f'{self.endpoint.get_url()}/security_hotspots?{branch}id={self.projectKey}&hotspots={self.key}'
        return self._url

    def to_csv(self):
        # id,project,rule,type,severity,status,creation,modification,project,file,line,debt,message
        cdate = self.creation_date.strftime(util.SQ_DATE_FORMAT)
        ctime = self.creation_date.strftime(util.SQ_TIME_FORMAT)
        mdate = self.modification_date.strftime(util.SQ_DATE_FORMAT)
        mtime = self.modification_date.strftime(util.SQ_TIME_FORMAT)
        # Strip timezone
        mtime = mtime.split('+')[0]
        msg = self.message.replace('"', '""')
        line = '-' if self.line is None else self.line
        return ';'.join([str(x) for x in [self.key, self.rule, 'SECURITY_HOTSPOT', self.vulnerabilityProbability, self.status,
                                          cdate, ctime, mdate, mtime, self.projectKey,
                                          projects.get(self.projectKey, self.endpoint).name, self.file, line,
                                          0, '"' + msg + '"']])

    def to_json(self):
        data = vars(self)
        for old_name, new_name in (('line', 'lineNumber'), ('rule', 'ruleReference'), ('file', 'path')):
            data[new_name] = data.pop(old_name, None)
        data['createdAt'] = self.creation_date.strftime(util.SQ_DATETIME_FORMAT)
        data['updatedAt'] = self.modification_date.strftime(util.SQ_DATETIME_FORMAT)
        data['url'] = self.url()
        if data['path'] is None:
            util.logger.warning("Can't find file path for %s", str(self))
            # data['path'] = 'Unknown'
        for field in ('endpoint', '_json', 'changelog', 'component', '_url', 'creation_date', 'modification_date'):
            data.pop(field, None)
        for k, v in data.copy().items():
            if v is None:
                data.pop(k)
        return json.dumps(data, sort_keys=True, indent=3, separators=(',', ': '))


def search_by_project(project_key, endpoint=None, branch=None):
    new_params = {}
    if project_key is None:
        key_list = projects.search(endpoint).keys()
    else:
        key_list = project_key.split(',')
    hotspots = {}
    for k in key_list:
        util.logger.info("Hotspots search by project %s branch %s", k, str(branch))
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
            hotspots[i['key']] = Hotspot(key=i['key'], endpoint=endpoint, data=i)
        if page is not None or p >= nbr_pages:
            break
        p += 1
    return hotspots
