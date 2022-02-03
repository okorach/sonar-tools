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

    Abstraction of the SonarQube "finding" concept

'''

import sonarqube.sqobject as sq
import sonarqube.utilities as util

_JSON_FIELDS_REMAPPED = (
    ('pull_request', 'pullRequest'),
    ('_comments', 'comments')
)

_JSON_FIELDS_PRIVATE = ('endpoint', 'id', '_json', '_changelog', 'assignee', 'hash', 'sonarqube',
    'creation_date', 'modification_date', '_debt', 'component', 'language', 'resolution')

_CSV_FIELDS = ('key', 'rule', 'type', 'severity', 'status', 'creationDate', 'updateDate', 'projectKey', 'projectName',
            'branch', 'pullRequest', 'file', 'line', 'effort', 'message')


class Finding(sq.SqObject):

    def __init__(self, key, endpoint, data=None, from_export=False):
        super().__init__(key, endpoint)
        self._json = None
        self.severity = None
        self.type = None
        self.author = None
        self.assignee = None
        self.status = None
        self.resolution = None
        self.rule = None
        self.projectKey = None
        self.language = None
        self._changelog = None
        self._comments = None
        self.line = None
        self.component = None
        self.message = None
        self.creation_date = None
        self.modification_date = None
        self.hash = None
        self.branch = None
        self.pull_request = None
        self._load(data, from_export)

    def _load(self, data, from_export=False):
        if data is not None:
            if from_export:
                self._load_from_export(data)
            else:
                self._load_from_search(data)

    def _load_common(self, jsondata):
        if self._json is None:
            self._json = jsondata
        else:
            self._json.update(jsondata)
        self.author = jsondata.get('author', None)
        self.type = jsondata.get('type', None)
        self.severity = jsondata.get('severity', None)

        self.message = jsondata.get('message', None)
        self.status = jsondata['status']
        self.resolution = jsondata.get('resolution', None)
        self.rule = jsondata.get('rule', jsondata.get('ruleReference', None))
        self.line = jsondata.get('line', jsondata.get('lineNumber', None))
        if self.line == "null":
            self.line = None
        if self.line is not None:
            try:
                self.line = int(self.line)
            except ValueError:
                pass

    def _load_from_search(self, jsondata):
        self._load_common(jsondata)
        self.projectKey = jsondata['project']
        self.creation_date = util.string_to_date(jsondata['creationDate'])
        self.modification_date = util.string_to_date(jsondata['updateDate'])
        self.hash = jsondata.get('hash', None)
        self.branch = jsondata.get('branch', None)
        self.pull_request = jsondata.get('pullRequest', None)

    def _load_from_export(self, jsondata):
        self._load_common(jsondata)
        self.projectKey = jsondata['projectKey']
        self.creation_date = util.string_to_date(jsondata['createdAt'])
        self.modification_date = util.string_to_date(jsondata['updatedAt'])

    def url(self):
        # Must be implemented in sub classes
        pass

    def file(self):
        if 'component' in self._json:
            return self._json['component'].split(":")[-1]
        elif 'path' in self._json:
            return self._json['path']
        else:
            util.logger.warning("Can't find file name for %s", str(self))
            return None

    def to_csv(self, separator=','):
        from sonarqube.projects import get_object
        data = self.to_json()
        for field in _CSV_FIELDS:
            if data.get(field, None) is None:
                data[field] = ''
        data['branch'] = util.quote(data['branch'], separator)
        data['message'] = util.quote(data['message'], separator)
        data['projectName'] = get_object(self.projectKey, endpoint=self.endpoint).name
        return separator.join([str(data[field]) for field in _CSV_FIELDS])

    def to_json(self):
        data = vars(self).copy()
        for old_name, new_name in _JSON_FIELDS_REMAPPED:
            data[new_name] = data.pop(old_name, None)
        data['effort'] = ''
        data['file'] = self.file()
        data['creationDate'] = self.creation_date.strftime(util.SQ_DATETIME_FORMAT)
        data['updateDate'] = self.modification_date.strftime(util.SQ_DATETIME_FORMAT)
        for field in _JSON_FIELDS_PRIVATE:
            data.pop(field, None)
        return data

    def is_vulnerability(self):
        return self.type == 'VULNERABILITY'

    def is_hotspot(self):
        return self.type == 'SECURITY_HOTSPOT'

    def is_bug(self):
        return self.type == 'BUG'

    def is_code_smell(self):
        return self.type == 'CODE_SMELL'

    def is_security_issue(self):
        return self.is_vulnerability() or self.is_hotspot()

    def is_closed(self):
        return self.status == 'CLOSED'

def to_csv_header(separator=','):
    return "# " + separator.join(_CSV_FIELDS)
