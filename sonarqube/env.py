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

    Abstraction of the SonarQube "platform" concept

'''
import sys
import re
import datetime
import json
import requests
import sonarqube.utilities as util

import sonarqube.audit_severities as sev
import sonarqube.audit_types as typ
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb
import sonarqube.audit_config as conf

AUTHENTICATION_ERROR_MSG = "Authentication error. Is token valid ?"
AUTORIZATION_ERROR_MSG = "Insufficient permissions to perform operation"
HTTP_FATAL_ERROR_MSG = "HTTP fatal error %d - %s"
WRONG_CONFIG_MSG = "Audit config property %s has wrong value %s, skipping audit"
DEFAULT_URL = 'http://localhost:9000'

_GLOBAL_PERMISSIONS = {
    "admin": "Global Administration",
    "gateadmin": "Administer Quality Gates",
    "profileadmin": "Administer Quality Profiles",
    "provisioning": "Create Projects",
    "portfoliocreator": "Create Portfolios",
    "applicationcreator": "Create Applications",
    "scan": "Run Analysis"
}

_JVM_OPTS = ('sonar.{}.javaOpts', 'sonar.{}.javaAdditionalOpts')

class UnsupportedOperation(Exception):
    def __init__(self, message):
        super().__init__()
        self.message = message

class NotSystemInfo(Exception):
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
            url_prefix += f'{sep}{p}={params[p]}'
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
            + audit_sysinfo(self.sys_info())
            + self._audit_admin_password()
            + self._audit_global_permissions()
            + self._audit_lts_latest()
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
        if conf.get_property('checkDefaultProjectVisibility') and visi != 'private':
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
    return this.context.url()


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


def __get_memory(setting):
    for s in setting.split(' '):
        if re.match('-Xmx', s):
            val = int(s[4:-1])
            unit = s[-1].upper()
            if unit == 'M':
                return val
            elif unit == 'G':
                return val * 1024
            elif unit == 'K':
                return val // 1024
    return None


def _get_store_size(setting):
    (val, unit) = setting.split(' ')
    # For decimal separator in some countries
    val = val.replace(',', '.')
    if unit == 'MB':
        return float(val)
    elif unit == 'GB':
        return float(val) * 1024
    return None


def _audit_setting_value(key, platform_settings, audit_settings):
    v = _get_multiple_values(4, audit_settings[key], 'MEDIUM', 'CONFIGURATION')
    if v is None:
        util.logger.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    if v[0] not in platform_settings:
        util.logger.warning("Setting %s does not exist, skipping...", v[0])
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
        util.logger.warning("Setting %s does not exist, skipping...", v[0])
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
        util.logger.warning("Setting %s does not exist, skipping...", key)
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
    thresholds = platform_settings['sonar.technicalDebt.ratingGrid'].split(',')
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


def _audit_log_level(sysinfo):
    util.logger.debug('Auditing log levels')
    log_level = sysinfo["Web Logging"]["Logs Level"]
    if log_level not in ("DEBUG", "TRACE"):
        return []
    if log_level == "TRACE":
        return [pb.Problem(typ.Type.PERFORMANCE, sev.Severity.CRITICAL,
            "Log level set to TRACE, this does very negatively affect platform performance, "
            "reverting to INFO is required")]
    if log_level == "DEBUG":
        return [pb.Problem(typ.Type.PERFORMANCE, sev.Severity.HIGH,
            "Log level is set to DEBUG, this may affect platform performance, "
            "reverting to INFO is recommended")]
    return []


def __sif_version(sif, digits=3, as_string=False):
    vers = sif['System']['Version'].split('.')
    if as_string:
        return '.'.join(vers[0:digits])
    else:
        return tuple(int(n) for n in vers[0:digits])


def _audit_web_settings(sysinfo):
    util.logger.debug('Auditing Web settings')
    problems = []
    opts = [x.format('web') for x in _JVM_OPTS]
    web_settings = sysinfo['Settings'][opts[1]] + " " + sysinfo['Settings'][opts[0]]
    web_ram = __get_memory(web_settings)
    if web_ram < 1024 or web_ram > 2048:
        rule = rules.get_rule(rules.RuleId.SETTING_WEB_HEAP)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(web_ram, 1024, 2048)))
    else:
        util.logger.debug("sonar.web.javaOpts -Xmx memory setting value is %d MB, "
                         "within the recommended range [1024-2048]", web_ram)

    problems += __audit_log4shell(__sif_version(sysinfo), web_settings, rules.RuleId.LOG4SHELL_WEB)
    return problems


def _audit_ce_settings(sysinfo):
    util.logger.info('Auditing CE settings')
    problems = []
    opts = [x.format('ce') for x in _JVM_OPTS]
    ce_settings = sysinfo['Settings'][opts[1]] + " " + sysinfo['Settings'][opts[0]]
    ce_ram = __get_memory(ce_settings)
    ce_tasks = sysinfo['Compute Engine Tasks']
    ce_workers = ce_tasks['Worker Count']
    MAX_WORKERS = 4
    if ce_workers > MAX_WORKERS:
        rule = rules.get_rule(rules.RuleId.SETTING_CE_TOO_MANY_WORKERS)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_workers, MAX_WORKERS)))
    else:
        util.logger.debug("%d CE workers configured, correct compared to the max %d recommended",
                         ce_workers, MAX_WORKERS)

    if ce_ram < 512 * ce_workers or ce_ram > 2048 * ce_workers:
        rule = rules.get_rule(rules.RuleId.SETTING_CE_HEAP)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_ram, 512, 2048, ce_workers)))
    else:
        util.logger.debug("sonar.ce.javaOpts -Xmx memory setting value is %d MB, "
                          "within recommended range ([512-2048] x %d workers)", ce_ram, ce_workers)

    problems += __audit_log4shell(__sif_version(sysinfo), ce_settings, rules.RuleId.LOG4SHELL_CE)
    return problems


def _audit_ce_background_tasks(sysinfo):
    util.logger.debug('Auditing CE background tasks')
    problems = []
    ce_tasks = sysinfo['Compute Engine Tasks']
    ce_workers = ce_tasks['Worker Count']
    ce_success = ce_tasks["Processed With Success"]
    ce_error = ce_tasks["Processed With Error"]
    ce_pending = ce_tasks["Pending"]
    if ce_success == 0 and ce_error == 0:
        failure_rate = 0
    else:
        failure_rate = ce_error / (ce_success+ce_error)
    if ce_error > 10 and failure_rate > 0.01:
        rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_FAILURE_RATE_HIGH)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(int(failure_rate * 100))))
    else:
        util.logger.debug('Number of failed background tasks (%d), and failure rate %d%% is OK',
                         ce_error, int(failure_rate * 100))

    if ce_pending > 100:
        rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_PENDING_QUEUE_VERY_LONG)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_pending)))
    elif ce_pending > 20 and ce_pending > (10*ce_workers):
        rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_PENDING_QUEUE_LONG)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_pending)))
    else:
        util.logger.debug('Number of pending background tasks (%d) is OK', ce_pending)
    return problems


def _audit_es_settings(sysinfo):
    util.logger.info('Auditing Search Server settings')
    problems = []
    opts = [x.format('ce') for x in _JVM_OPTS]
    es_settings = sysinfo['Settings'][opts[1]] + " " + sysinfo['Settings'][opts[0]]
    es_ram = __get_memory(es_settings)
    index_size = _get_store_size(sysinfo['Search State']['Store Size'])
    if es_ram < 2 * index_size and es_ram < index_size + 1000:
        rule = rules.get_rule(rules.RuleId.SETTING_ES_HEAP)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(es_ram, index_size)))
    else:
        util.logger.debug("Search server memory %d MB is correct wrt to index size of %d MB", es_ram, index_size)
    problems += __audit_log4shell(__sif_version(sysinfo), es_settings, rules.RuleId.LOG4SHELL_ES)
    return problems


def __audit_log4shell(sq_version, jvm_settings, broken_rule):
    util.logger.debug('Auditing log4shell vulnerability fix')
    if sq_version < (8, 9, 6) or ((9, 0, 0) <= sq_version < (9, 2, 4)):
        for s in jvm_settings.split(' '):
            if s == '-Dlog4j2.formatMsgNoLookups=true':
                return []
        rule = rules.get_rule(broken_rule)
        return [pb.Problem(rule.type, rule.severity, rule.msg)]
    return []


def _audit_jdbc_url(sysinfo):
    util.logger.info('Auditing JDBC settings')
    problems = []
    stats = sysinfo.get('Settings')
    if stats is None:
        util.logger.error("Can't verify Database settings in System Info File, was it corrupted or redacted ?")
        return problems
    jdbc_url = stats.get('sonar.jdbc.url', None)
    util.logger.debug('JDBC URL = %s', str(jdbc_url))
    if jdbc_url is None:
        rule = rules.get_rule(rules.RuleId.SETTING_JDBC_URL_NOT_SET)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg))
    elif re.search(r':(postgresql://|sqlserver://|oracle:thin:@)(localhost|127\.0+\.0+\.1)[:;/]', jdbc_url):
        rule = rules.get_rule(rules.RuleId.SETTING_DB_ON_SAME_HOST)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(jdbc_url)))
    return problems

def _audit_dce_settings(sysinfo):
    util.logger.info('Auditing DCE settings')
    problems = []
    stats = sysinfo.get('Statistics')
    if stats is None:
        util.logger.error("Can't verify edition in System Info File, was it corrupted or redacted ?")
        return problems
    sq_edition = stats.get('edition', None)
    if sq_edition is None:
        util.logger.error("Can't verify edition in System Info File, was it corrupted or redacted ?")
        return problems
    if sq_edition != "datacenter":
        util.logger.info('Not a Data Center Edition, skipping DCE checks')
        return problems
    # Verify that app nodes have the same plugins installed
    appnodes = sysinfo['Application Nodes']
    ref_plugins = json.dumps(appnodes[0]['Plugins'], sort_keys=True, indent=3, separators=(',', ': '))
    ref_name = appnodes[0]['Name']
    ref_version = appnodes[0]['System']['Version']
    for node in appnodes:
        node_version = node['System']['Version']
        if node_version != ref_version:
            rule = rules.get_rule(rules.RuleId.DCE_DIFFERENT_APP_NODES_VERSIONS)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ref_name, node['Name'])))
        node_plugins = json.dumps(node['Plugins'], sort_keys=True, indent=3, separators=(',', ': '))
        if node_plugins != ref_plugins:
            rule = rules.get_rule(rules.RuleId.DCE_DIFFERENT_APP_NODES_PLUGINS)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ref_name, node['Name'])))
        if not node['System']['Official Distribution']:
            rule = rules.get_rule(rules.RuleId.DCE_APP_NODE_UNOFFICIAL_DISTRO)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(node['Name'])))
        if node['Health'] != "GREEN":
            rule = rules.get_rule(rules.RuleId.DCE_APP_NODE_NOT_GREEN)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(node['Name'], node['Health'])))
    return problems


def is_sysinfo(sysinfo):
    for key in ('Health', 'System', 'Database', 'Settings'):
        if key not in sysinfo:
            return False
    return True


def audit_sysinfo(sysinfo):
    if not is_sysinfo(sysinfo):
        util.logger.critical("Provided JSON does not seem to be a system info")
        raise NotSystemInfo("JSON is not a system info nor a support info")
    util.logger.info("Auditing System Info")
    return (
        _audit_web_settings(sysinfo) +
        _audit_ce_settings(sysinfo) +
        _audit_ce_background_tasks(sysinfo) +
        _audit_es_settings(sysinfo) +
        _audit_dce_settings(sysinfo) +
        _audit_jdbc_url(sysinfo) +
        _audit_log_level(sysinfo)
    )


def _get_permissions_count(users_or_groups):
    perm_counts = dict(zip(_GLOBAL_PERMISSIONS.keys(), [0, 0, 0, 0, 0, 0, 0]))
    for user_or_group in users_or_groups:
        for perm in _GLOBAL_PERMISSIONS:
            if perm in user_or_group['permissions']:
                perm_counts[perm] += 1
    return perm_counts


def _get_multiple_values(n, setting, severity, domain):
    values = [x.strip() for x in setting.split(',')]
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
