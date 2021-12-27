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

import re
import json
import sonarqube.sqobject as sq
import sonarqube.utilities as util
import sonarqube.projects as projects

'''
      "key": "AX37OzKIZoChGW6hZPyd",
      "projectKey": "demo:joomla",
      "path": "libraries/src/Filesystem/File.php",
      "lineNumber": "291",
      "message": "Make sure this permission is safe.",
      "status": "TO_REVIEW",
      "author": "rschley@ebay.com",
      "createdAt": "2021-12-27T10:32:51+0100",
      "updatedAt": "2021-12-27T10:32:51+0100",
      "ruleReference": "S2612",
      "comments": [],
      "securityCategory": "auth",
      "vulnerabilityProbability": "HIGH",
      "type": "SECURITY_HOTSPOT"
'''

class Hotspot(sq.SqObject):

    def __init__(self, key, endpoint, data=None, from_findings=False):
        super().__init__(key, endpoint)
        self.url = None
        self.json = None
        self.vuln_probability = None
        self.category = None
        self.author = None
        self.assignee = None
        self.status = None
        self.rule = None
        self.projectKey = None
        self.language = None
        self.line = None
        self.component = None
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

        self.component = jsondata['component']
        self.hash = jsondata.get('hash', None)
        self.branch = jsondata.get('branch', None)

    def __load_finding(self, jsondata):
        self.__load_common(jsondata)
        self.projectKey = jsondata['projectKey']
        self.creation_date = util.string_to_date(jsondata['createdAt'])
        self.modification_date = util.string_to_date(jsondata['updatedAt'])

    def __load_common(self, jsondata):
        self.json = jsondata
        self.vuln_probability = jsondata.get('vulnerabilityProbability', None)
        self.line = jsondata.get('line', jsondata.get('lineNumber', None))
        self.rule = jsondata.get('rule', jsondata.get('ruleReference', None))
        self.message = jsondata.get('message', None)
        self.status = jsondata['status']

    def to_csv(self):
        # id,project,rule,type,severity,status,creation,modification,project,file,line,debt,message
        cdate = self.creation_date.strftime(util.SQ_DATE_FORMAT)
        ctime = self.creation_date.strftime(util.SQ_TIME_FORMAT)
        mdate = self.modification_date.strftime(util.SQ_DATE_FORMAT)
        mtime = self.modification_date.strftime(util.SQ_TIME_FORMAT)
        # Strip timezone
        mtime = re.sub(r"\+.*", "", mtime)
        msg = str.replace('"', '""', self.message)
        line = '-' if self.line is None else self.line
        return ';'.join([str(x) for x in [self.key, self.rule, 'SECURITY_HOTSPOT', self.vuln_probability, self.status,
                                          cdate, ctime, mdate, mtime, self.projectKey,
                                          projects.get(self.projectKey, self.endpoint).name, self.component, line,
                                          '-', '"' + msg + '"']])

    def to_json(self):
        data = vars(self)
        for old_name, new_name in (('line', 'lineNumber'), ('rule', 'ruleReference')):
            data[new_name] = data.pop(old_name, None)
        data['createdAt'] = self.creation_date.strftime(util.SQ_DATETIME_FORMAT)
        data['updatedAt'] = self.modification_date.strftime(util.SQ_DATETIME_FORMAT)
        if data['lineNumber'] is None:
            data.pop('lineNumber')
        if 'path' in self.json:
            data['path'] = self.json['path']
        else:
            util.logger.warning("Can't find file path for %s", str(self))
            data['path'] = 'Unknown'
        for field in ('endpoint', 'json', 'changelog', 'url', 'creation_date', 'modification_date'):
            data.pop(field, None)
        return json.dumps(data, sort_keys=True, indent=3, separators=(',', ': '))