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

import re
import sonar.sqobject as sq
import sonar.utilities as util
from sonar import projects

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
        if self.branch is not None:
            self.branch = re.sub("^BRANCH:", "", self.branch)
        self.pull_request = jsondata.get('pullRequest', None)

    def _load_from_export(self, jsondata):
        self._load_common(jsondata)
        self.projectKey = jsondata['projectKey']
        self.creation_date = util.string_to_date(jsondata['createdAt'])
        self.modification_date = util.string_to_date(jsondata['updatedAt'])

    def url(self):
        # Must be implemented in sub classes
        raise NotImplementedError()

    def file(self):
        if 'component' in self._json:
            # FIXME: Adapt to the ugly component structure on branches and PR
            # "component": "src:sonar/hot.py:BRANCH:somebranch",
            return self._json['component'].split(":")[1]
        elif 'path' in self._json:
            return self._json['path']
        else:
            util.logger.warning("Can't find file name for %s", str(self))
            return None

    def to_csv(self, separator=','):
        from sonar.projects import get_object
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

    def changelog(self):
        # Implemented in subclasses, should not reach this
        raise NotImplementedError()

    def comments(self):
        # Implemented in subclasses, should not reach this
        raise NotImplementedError()

    def has_changelog(self):
        util.logger.debug('%s has %d changelogs', str(self), len(self.changelog()))
        return len(self.changelog()) > 0

    def has_comments(self):
        return len(self.comments()) > 0

    def has_changelog_or_comments(self):
        return self.has_changelog() or self.has_comments()

    def modifiers(self):
        """Returns list of users that modified the finding."""
        item_list = []
        for c in self.changelog().values():
            util.logger.debug("Checking author of changelog %s", str(c))
            author = c.author()
            if author is not None and author not in item_list:
                item_list.append(author)
        return item_list

    def commenters(self):
        """Returns list of users that commented the issue."""
        return util.unique_dict_field(self.comments(), 'user')

    def modifiers_and_commenters(self):
        modif = self.modifiers()
        for c in self.commenters():
            if c not in modif:
                modif.append(c)
        return modif

    def modifiers_excluding_service_users(self, service_users):
        mods = []
        for u in self.modifiers():
            if u not in service_users:
                mods.append(u)
        return mods

    def can_be_synced(self, user_list):
        util.logger.debug("Issue %s: Checking if modifiers %s are different from user %s",
            str(self), str(self.modifiers()), str(user_list))
        if user_list is None:
            return not self.has_changelog()
        for u in self.modifiers():
            if u not in user_list:
                return False
        return True

    def strictly_identical_to(self, another_finding, ignore_component=False):
        return (
            self.rule == another_finding.rule and
            self.hash == another_finding.hash and
            self.message == another_finding.message and
            self.file() == another_finding.file() and
            (self.component == another_finding.component or ignore_component)
        )

    def almost_identical_to(self, another_finding, ignore_component=False, **kwargs):
        if self.rule != another_finding.rule or self.hash != another_finding.hash:
            return False
        score = 0
        if self.message == another_finding.message or kwargs.get('ignore_message', False):
            score += 2
        if self.file() == another_finding.file():
            score += 2
        if self.line == another_finding.line or kwargs.get('ignore_line', False):
            score += 1
        if self.component == another_finding.component or ignore_component:
            score += 1
        if self.author == another_finding.author or kwargs.get('ignore_author', False):
            score += 1
        if self.type == another_finding.type or kwargs.get('ignore_type', False):
            score += 1
        if self.severity == another_finding.severity or kwargs.get('ignore_severity', False):
            score += 1
        # Need at least 7 / 9 to match
        return score >= 7

    def search_siblings(self, findings_list, allowed_users=None, ignore_component=False, **kwargs):
        exact_matches = []
        approx_matches = []
        match_but_modified = []
        for key, finding in findings_list.items():
            if key == self.key:
                continue
            if finding.strictly_identical_to(self, ignore_component, **kwargs):
                util.logger.debug("Issues %s and %s are strictly identical", self.key, key)
                if finding.can_be_synced(allowed_users):
                    exact_matches.append(finding)
                else:
                    match_but_modified.append(finding)
            elif finding.almost_identical_to(self, ignore_component, **kwargs):
                util.logger.debug("Issues %s and %s are almost identical", self.key, key)
                if finding.can_be_synced(allowed_users):
                    approx_matches.append(finding)
                else:
                    match_but_modified.append(finding)
            else:
                util.logger.debug("Issues %s and %s are not siblings", self.key, key)
        return (exact_matches, approx_matches, match_but_modified)


def to_csv_header(separator=','):
    return "# " + separator.join(_CSV_FIELDS)


def export(project_key, endpoint):
    if endpoint.version() < (9, 1, 0) or endpoint.edition() not in ('enterprise', 'datacenter'):
        return {}
    return projects.get_object(project_key, endpoint)
