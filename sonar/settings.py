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
"""
    Abstraction of the SonarQube setting concept
"""

import re
import json
from sonar import sqobject
import sonar.utilities as util

CATEGORIES = ('general', 'languages', 'scope', 'tests', 'linters', 'authentication', 'sast')

_SETTINGS = {}

_PRIVATE_SETTINGS = (
    'sonaranalyzer', 'sonar.updatecenter', 'sonar.plugins.risk.consent',
    'sonar.core.id', 'sonar.core.startTime', 'sonar.plsql.jdbc.driver.class'
)

_INLINE_SETTINGS = (
    r'^.*\.file\.suffixes$',
    r'^.*\.reportPaths$',
    r'^sonar\.[a-z]+\.exclusions$',
    r'^sonar\.javascript\.(globals|environments)$',
    r'^sonar\.dbcleaner\.branchesToKeepWhenInactive$',
    r'^sonar.rpg.suffixes$'
)

class Setting(sqobject.SqObject):

    def __init__(self, key, endpoint, project=None, data=None):
        super().__init__(key, endpoint)
        self.project = project
        self.value = None
        if data is None:
            params = {'keys': key}
            if project:
                params['component'] = project.key
            resp = self.get('api/settings/values', params=params)
            data = json.loads(resp.text)['settings']

        self.value = util.convert_string(data.get('value', data.get('values', data.get('defaultValue', ''))))
        if 'inherited' in data:
            self.inherited = data['inherited']
        elif 'parentValues' in data or 'parentValue' in data:
            self.inherited = False
        elif 'category' in data:
            self.inherited = True

        if project is None:
            self.inherited = True
        util.logger.debug("Created %s value %s", str(self), str(self.value))
        _SETTINGS[self.uuid()] = self

    def uuid(self):
        return _uuid_p(self.key, self.project)

    def __str__(self):
        if self.project is None:
            return f"setting '{self.key}'"
        else:
            return f"setting '{self.key}' of {str(self.project)}"

    def set(self, value):
        params = {}
        if self.project:
            params['component'] = self.project.key
        return self.post('api/settings/set', params=params)

    def to_json(self):
        val = self.value
        for reg in _INLINE_SETTINGS:
            if re.match(reg, self.key) and isinstance(self.value, list):
                val = ', '.join([v.strip() for v in self.value])
                break
        subval = {'value': val}
        multi = False
        if self.project is not None:
            subval['projectKey'] = self.project.key
            multi = True
        if self.inherited is not None and not self.inherited:
            subval['inherited'] = self.inherited
            multi = True
        if multi:
            return {self.key: subval}
        else:
            return {self.key: val}

    def category(self):
        if re.match(r'^.*([lL]int|govet|flake8|checkstyle|pmd|spotbugs|phpstan|psalm|detekt|bandit|rubocop|scalastyle|scapegoat).*$', self.key):
            return ('linters', None)
        if re.match(r'^.*(\.reports?Paths?$|unit\..*$|cov.*$)', self.key):
            return ('tests', None)
        if re.match(r'^sonar\.security\.config\..+$', self.key):
            return ('sast', None)
        if re.match(r'^.*\.(exclusions$|inclusions$|issue\..+)$', self.key):
            return('scope', None)
        m = re.match(r'^sonar\.(cpd\.)?(abap|apex|cloudformation|c|cpp|cfamily|cobol|cs|css|flex|go|html|java|'
                     r'javascript|json|jsp|kotlin|objc|php|pli|plsql|python|rpg|ruby|scala|swift|terraform|tsql|'
                     r'typescript|vb|vbnet|xml|yaml)\.', self.key)
        if m:
            lang = m.group(2)
            if lang in ('c', 'cpp', 'objc', 'cfamily'):
                lang = 'cfamily'
            return ('languages', lang)
        m = re.match(r'^sonar\.(auth\.|authenticator\.downcase).*$', self.key)
        if m:
            return ('authentication', m.group(1))
        m = re.match(r'^sonar\.forceAuthentication$', self.key)
        if m:
            return ('authentication', None)
        return ('general', None)


def get_object(key, endpoint=None, data=None, project=None):
    if key not in _SETTINGS:
        _ = Setting(key=key, endpoint=endpoint, data=data, project=project)
    return _SETTINGS[_uuid_p(key, project)]


def get_bulk(endpoint, settings_list=None, project=None, include_not_set=False):
    """Gets several settings as bulk (returns a dict)"""
    settings_dict = {}
    if settings_list is None:
        params = {}
    if include_not_set:
        resp = endpoint.get('api/settings/list_definitions', params=params)
        data = json.loads(resp.text)
        settings_dict = {}
        for s in data['definitions']:
            if s['key'].endswith('coverage.reportPath') or s['key'] == 'languageSpecificParameters':
                continue
            o = Setting(s['key'], endpoint=endpoint, data=s, project=project)
            settings_dict[o.uuid()] = o
    elif isinstance(settings_list, list):
        params = {'keys': util.list_to_csv(settings_list)}
    else:
        params = {'keys': util.csv_normalize(settings_list)}
    if project:
        params['component'] = project.key
    resp = endpoint.get('api/settings/values', params=params)
    data = json.loads(resp.text)
    for s in data['settings']:
        skip = False
        for priv in _PRIVATE_SETTINGS:
            if s['key'].startswith(priv):
                skip = True
                break
        if skip:
            util.logger.debug('Skipping private setting %s', s['key'])
            continue
        o = Setting(s['key'], endpoint=endpoint, data=s, project=project)
        settings_dict[o.uuid()] = o
    return settings_dict


def get_all(endpoint, project=None):
    return get_bulk(endpoint, project=project, include_not_set=True)


def uuid(key, project_key=None):
    """Computes uuid for a setting"""
    if project_key is None:
        return key
    else:
        return f"{key}#{project_key}"

def _uuid_p(key, project):
    """Computes uuid for a setting"""
    pk = None if project is None else project.key
    return uuid(key, pk)
