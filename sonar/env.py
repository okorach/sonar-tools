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

    Abstraction of the SonarQube "platform" concept

'''
import sys
import re
import datetime
import json
import requests

import sonar.utilities as util

from sonar.audit import rules, config
import sonar.audit.severities as sev
import sonar.audit.types as typ
import sonar.audit.problem as pb

from sonar import sif

AUTHENTICATION_ERROR_MSG = "Authentication error. Is token valid ?"
AUTORIZATION_ERROR_MSG = "Insufficient permissions to perform operation"
HTTP_FATAL_ERROR_MSG = "HTTP fatal error %d - %s"
WRONG_CONFIG_MSG = "Audit config property %s has wrong value %s, skipping audit"

_NON_EXISTING_SETTING_SKIPPED = "Setting %s does not exist, skipping..."

_APP_NODES = 'Application Nodes'
_ES_NODES = 'Search Nodes'
_SYSTEM = 'System'
_STORE_SIZE = 'Store Size'
_ES_STATE = 'Search State'

_GLOBAL_PERMISSIONS = {
    "admin": "Global Administration",
    "gateadmin": "Administer Quality Gates",
    "profileadmin": "Administer Quality Profiles",
    "provisioning": "Create Projects",
    "portfoliocreator": "Create Portfolios",
    "applicationcreator": "Create Applications",
    "scan": "Run Analysis"
}

class UnsupportedOperation(Exception):
    def __init__(self, message):
        super().__init__()
        self.message = message

class NonExistingObjectError(Exception):
    def __init__(self, key, message):
        super().__init__()
        self.key = key
        self.message = message

class Environment:

    def __init__(self, some_url, some_token):
        self.url = some_url
        self.token = some_token
        self._version = None
        self._sys_info = None

    def __str__(self):
        return f"{util.redacted_token(self.token)}@{self.url}"

    def set_env(self, some_url, some_token):
        self.url = some_url
        self.token = some_token
        util.logger.debug('Setting environment: %s', str(self))

    def set_token(self, some_token):
        self.token = some_token

    def credentials(self):
        return (self.token, '')

    def set_url(self, some_url):
        self.url = some_url

    def version(self, digits=3, as_string=False):
        if self._version is None:
            resp = self.get('/api/server/version')
            self._version = resp.text.split('.')
        if as_string:
            return '.'.join(self._version[0:digits])
        else:
            return tuple(int(n) for n in self._version[0:digits])

    def sys_info(self):
        if self._sys_info is None:
            resp = self.get('system/info')
            self._sys_info = json.loads(resp.text)
        return self._sys_info

    def edition(self):
        return self.sys_info()['Statistics']['edition']

    def database(self):
        return self.sys_info()['Statistics']['database']['name']

    def plugins(self):
        return self.sys_info()['Statistics']['plugins']

    def get(self, api, params=None, exit_on_error=True):
        api = _normalize_api(api)
        util.logger.debug('GET: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.get(url=self.url + api, auth=self.credentials())
            else:
                r = requests.get(url=self.url + api, auth=self.credentials(), params=params)
            r.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            if exit_on_error:
                _log_and_exit(r.status_code, errh)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise SystemExit(e) from e
        return r

    def post(self, api, params=None):
        api = _normalize_api(api)
        util.logger.debug('POST: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.post(url=self.url + api, auth=self.credentials())
            else:
                r = requests.post(url=self.url + api, auth=self.credentials(), params=params)
            r.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            _log_and_exit(r.status_code, errh)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise SystemExit(e) from e
        return r

    def delete(self, api, params=None):
        api = _normalize_api(api)
        util.logger.debug('DELETE: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.delete(url=self.url + api, auth=self.credentials())
            else:
                r = requests.delete(url=self.url + api, auth=self.credentials(), params=params)
            r.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            _log_and_exit(r.status_code, errh)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise SystemExit(e) from e

    def urlstring(self, api, params):
        first = True
        url_prefix = f"{str(self)}{api}"
        if params is None:
            return url_prefix
        for p in params:
            if params[p] is None:
                continue
            sep = '?' if first else '&'
            first = False
            if isinstance(params[p], datetime.date):
                params[p] = util.format_date(params[p])
            url_prefix += f'{sep}{p}={requests.utils.quote(str(params[p]))}'
        return url_prefix

    def __get_platform_settings(self):
        resp = self.get('settings/values')
        json_s = json.loads(resp.text)
        platform_settings = {}
        for s in json_s['settings']:
            if 'value' in s:
                platform_settings[s['key']] = s['value']
            elif 'values' in s:
                platform_settings[s['key']] = ','.join(s['values'])
            elif 'fieldValues' in s:
                platform_settings[s['key']] = s['fieldValues']
        return platform_settings

    def audit(self, audit_settings=None):
        util.logger.info('--- Auditing global settings ---')
        problems = []
        platform_settings = self.__get_platform_settings()
        for key in audit_settings:
            if key.startswith('audit.globalSettings.range'):
                problems += _audit_setting_in_range(key, platform_settings, audit_settings, self.version())
            elif key.startswith('audit.globalSettings.value'):
                problems += _audit_setting_value(key, platform_settings, audit_settings)
            elif key.startswith('audit.globalSettings.isSet'):
                problems += _audit_setting_set(key, True, platform_settings, audit_settings)
            elif key.startswith('audit.globalSettings.isNotSet'):
                problems += _audit_setting_set(key, False, platform_settings, audit_settings)

        problems += (
            _audit_maintainability_rating_grid(platform_settings, audit_settings)
            + self._audit_project_default_visibility()
            + self._audit_admin_password()
            + self._audit_global_permissions()
            + self._audit_lts_latest()
            + sif.Sif(self.sys_info()).audit()
        )
        return problems

    def _audit_project_default_visibility(self):
        util.logger.info('Auditing project default visibility')
        problems = []
        if self.version() < (8, 7, 0):
            resp = self.get('navigation/organization', params={'organization': 'default-organization'})
            visi = json.loads(resp.text)['organization']['projectVisibility']
        else:
            resp = self.get('settings/values', params={'keys': 'projects.default.visibility'})
            visi = json.loads(resp.text)['settings'][0]['value']
        util.logger.info("Project default visibility is '%s'", visi)
        if config.get_property('checkDefaultProjectVisibility') and visi != 'private':
            rule = rules.get_rule(rules.RuleId.SETTING_PROJ_DEFAULT_VISIBILITY)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msq.format(visi)))
        return problems

    def _audit_admin_password(self):
        util.logger.info('Auditing admin password')
        problems = []
        try:
            r = requests.get(url=self.url + '/api/authentication/validate', auth=('admin', 'admin'))
            data = json.loads(r.text)
            if data.get('valid', False):
                rule = rules.get_rule(rules.RuleId.DEFAULT_ADMIN_PASSWORD)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg))
            else:
                util.logger.info("User 'admin' default password has been changed")
        except requests.RequestException as e:
            util.logger.error("HTTP request exception for %s/%s: %s", self.url,
                              'api/authentication/validate', str(e))
            raise
        return problems

    def __get_permissions(self, perm_type):
        resp = self.get(f'permissions/{perm_type}', params={'ps': 100})
        data = json.loads(resp.text)
        active_perms = []
        for item in data.get(perm_type, []):
            if item['permissions']:
                active_perms.append(item)
        return active_perms

    def __audit_group_permissions(self):
        util.logger.info('Auditing group global permissions')
        problems = []
        groups = self.__get_permissions('groups')
        if len(groups) > 10:
            problems.append(
                pb.Problem(typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM,
                           f'Too many ({len(groups)}) groups with global permissions'))
        for gr in groups:
            if gr['name'] == 'Anyone':
                problems.append(pb.Problem(typ.Type.SECURITY, sev.Severity.HIGH,
                                           "Group 'Anyone' should not have any global permission"))
            if gr['name'] == 'sonar-users' and (
                    'admin' in gr['permissions'] or 'gateadmin' in gr['permissions'] or
                    'profileadmin' in gr['permissions'] or 'provisioning' in gr['permissions']):
                rule = rules.get_rule(rules.RuleId.PROJ_PERM_SONAR_USERS_ELEVATED_PERMS)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg))

        perm_counts = _get_permissions_count(groups)
        maxis = {'admin': 2, 'gateadmin': 2, 'profileadmin': 2, 'scan': 2, 'provisioning': 3}
        for key, name in _GLOBAL_PERMISSIONS.items():
            if key in maxis and perm_counts[key] > maxis[key]:
                problems.append(
                    pb.Problem(typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM,
                               f'Too many ({perm_counts[key]}) groups with permission {name}, '
                               f'{maxis[key]} max recommended'))
        return problems

    def __audit_user_permissions(self):
        util.logger.info('Auditing users global permissions')
        problems = []
        users = self.__get_permissions('users')
        if len(users) > 10:
            problems.append(
                pb.Problem(
                    typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM,
                    f'Too many ({len(users)}) users with direct global permissions, use groups instead'))

        perm_counts = _get_permissions_count(users)
        maxis = {'admin': 3, 'gateadmin': 3, 'profileadmin': 3, 'scan': 3, 'provisioning': 3}
        for key, name in _GLOBAL_PERMISSIONS.items():
            if key in maxis and perm_counts[key] > maxis[key]:
                problems.append(
                    pb.Problem(
                        typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM,
                        f'Too many ({perm_counts[key]}) users with permission {name}, use groups instead'))
        return problems

    def _audit_global_permissions(self):
        util.logger.info('--- Auditing global permissions ---')
        return self.__audit_user_permissions() + self.__audit_group_permissions()

    def _audit_lts_latest(self):
        problems = []
        vers = self.version()
        if vers < (8, 9, 0):
            rule = rules.get_rule(rules.RuleId.BELOW_LTS)
            msg = rule.msg.format(str(self))
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        elif vers < (9, 2, 0):
            rule = rules.get_rule(rules.RuleId.BELOW_LATEST)
            msg = rule.msg.format(str(self))
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        return problems


# --------------------- Static methods -----------------
# this is a pointer to the module object instance itself.
this = sys.modules[__name__]
this.context = Environment("http://localhost:9000", '')


def set_env(some_url, some_token):
    this.context = Environment(some_url, some_token)
    util.logger.debug('Setting GLOBAL environment: %s@%s', util.redacted_token(some_token), some_url)


def set_token(some_token):
    this.context.set_token(some_token)


def token():
    return this.context.token


def credentials():
    return this.context.credentials()


def set_url(some_url):
    this.context.set_url(some_url)


def url():
    return this.context.url


def _normalize_api(api):
    api = api.lower()
    if re.match(r'/api', api):
        pass
    elif re.match(r'api', api):
        api = '/' + api
    elif re.match(r'/', api):
        api = '/api' + api
    else:
        api = '/api/' + api
    return api


def _log_and_exit(code, err):
    if code == 401:
        util.logger.fatal(AUTHENTICATION_ERROR_MSG)
        raise SystemExit(err)
    if code == 403:
        util.logger.fatal(AUTORIZATION_ERROR_MSG)
        raise SystemExit(err)
    if (code // 100) != 2:
        util.logger.fatal(HTTP_FATAL_ERROR_MSG, code, err)
        raise SystemExit(err)


def get(api, params=None, ctxt=None, exit_on_error=True):
    if ctxt is None:
        ctxt = this.context
    return ctxt.get(api, params, exit_on_error)


def post(api, params=None, ctxt=None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.post(api, params)

def edition(ctxt=None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.edition()

def version(ctxt=None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.version()


def delete(api, params=None, ctxt=None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.delete(api, params)


def _audit_setting_value(key, platform_settings, audit_settings):
    v = _get_multiple_values(4, audit_settings[key], 'MEDIUM', 'CONFIGURATION')
    if v is None:
        util.logger.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    if v[0] not in platform_settings:
        util.logger.warning(_NON_EXISTING_SETTING_SKIPPED, v[0])
        return []
    util.logger.info("Auditing that setting %s has common/recommended value '%s'", v[0], v[1])
    s = platform_settings.get(v[0], '')
    if s == v[1]:
        return []
    return [pb.Problem(v[2], v[3], f"Setting {v[0]} has potentially incorrect or unsafe value '{s}'")]


def _audit_setting_in_range(key, platform_settings, audit_settings, sq_version):
    v = _get_multiple_values(5, audit_settings[key], 'MEDIUM', 'CONFIGURATION')
    if v is None:
        util.logger.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    if v[0] not in platform_settings:
        util.logger.warning(_NON_EXISTING_SETTING_SKIPPED, v[0])
        return []
    if v[0] == 'sonar.dbcleaner.daysBeforeDeletingInactiveShortLivingBranches' and \
       sq_version >= (8, 0, 0):
        util.logger.error("Setting %s is ineffective on SonaQube 8.0+, skipping audit", v[0])
        return []
    value, min_v, max_v = float(platform_settings[v[0]]), float(v[1]), float(v[2])
    util.logger.info("Auditing that setting %s is within recommended range [%f-%f]", v[0], min_v, max_v)
    if min_v <= value <= max_v:
        return []
    return [pb.Problem(v[4], v[3],
            f"Setting '{v[0]}' value {platform_settings[v[0]]} is outside recommended range [{v[1]}-{v[2]}]")]


def _audit_setting_set(key, check_is_set, platform_settings, audit_settings):
    v = _get_multiple_values(3, audit_settings[key], 'MEDIUM', 'CONFIGURATION')
    if v is None:
        util.logger.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    if key not in platform_settings:
        util.logger.warning(_NON_EXISTING_SETTING_SKIPPED, key)
        return []
    util.logger.info("Auditing whether setting %s is set or not", key)
    problems = []
    if platform_settings[key] == '':
        if check_is_set:
            rule = rules.get_rule(rules.RuleId.SETTING_NOT_SET)
            problems = [pb.Problem(rule.type, rule.severity, rule.msg.format(key))]
        else:
            util.logger.info("Setting %s is not set", key)
    else:
        if not check_is_set:
            util.logger.info("Setting %s is set with value %s", key, platform_settings[key])
        else:
            problems = [pb.Problem(v[1], v[2], f"Setting {key} is set, although it should probably not")]

    return problems


def _audit_maintainability_rating_range(value, range, rating_letter, severity, domain):
    util.logger.debug("Checking that maintainability rating threshold %3.0f%% for '%s' is "
                      "within recommended range [%3.0f%%-%3.0f%%]",
                      value * 100, rating_letter, range[0] * 100, range[1] * 100)
    if range[0] <= value <= range[1]:
        return []
    return [pb.Problem(domain, severity,
        f'Maintainability rating threshold {value * 100}% for {rating_letter} '
        f'is NOT within recommended range [{range[0] * 100}%-{range[1] * 100}%]')]


def _audit_maintainability_rating_grid(platform_settings, audit_settings):
    thresholds = util.csv_to_list(platform_settings['sonar.technicalDebt.ratingGrid'])
    problems = []
    util.logger.debug("Auditing maintainabillity rating grid")
    for key in audit_settings:
        if not key.startswith('audit.globalSettings.maintainabilityRating'):
            continue
        (_, _, _, letter, _, _) = key.split('.')
        if letter not in ['A', 'B', 'C', 'D']:
            util.logger.error("Incorrect audit configuration setting %s, skipping audit", key)
            continue
        value = float(thresholds[ord(letter.upper()) - 65])
        v = _get_multiple_values(4, audit_settings[key], sev.Severity.MEDIUM, typ.Type.CONFIGURATION)
        if v is None:
            continue
        problems += _audit_maintainability_rating_range(value, (float(v[0]), float(v[1])), letter, v[2], v[3])
    return problems


def _get_permissions_count(users_or_groups):
    perm_counts = dict(zip(_GLOBAL_PERMISSIONS.keys(), [0, 0, 0, 0, 0, 0, 0]))
    for user_or_group in users_or_groups:
        for perm in _GLOBAL_PERMISSIONS:
            if perm in user_or_group['permissions']:
                perm_counts[perm] += 1
    return perm_counts


def _get_multiple_values(n, setting, severity, domain):
    values = util.csv_to_list(setting)
    if len(values) < (n - 2):
        return None
    if len(values) == (n - 2):
        values.append(severity)
    if len(values) == (n - 1):
        values.append(domain)
    values[n - 2] = sev.to_severity(values[n - 2])
    values[n - 1] = typ.to_type(values[n - 1])
    # TODO Handle case of too many values
    return values
