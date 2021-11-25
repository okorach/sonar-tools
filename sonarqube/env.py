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

GLOBAL_PERMISSIONS = {
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

class NotSystemInfo(Exception):
    def __init__(self, message):
        super().__init__()
        self.message = message

class Environment:

    def __init__(self, url, token):
        self.root_url = url
        self.token = token
        self._version = None
        self._sys_info = None

    def __str__(self):
        return f"{util.redacted_token(self.token)}@{self.root_url}"

    def set_env(self, url, token):
        self.root_url = url
        self.token = token
        util.logger.debug('Setting environment: %s', str(self))

    def set_token(self, token):
        self.token = token

    def get_token(self):
        return self.token

    def get_credentials(self):
        return (self.token, '')

    def set_url(self, url):
        self.root_url = url

    def get_url(self):
        return self.root_url

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

    def get(self, api, params=None):
        api = __normalize_api__(api)
        util.logger.debug('GET: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.get(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.get(url=self.root_url + api, auth=self.get_credentials(), params=params)
            r.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            __log_and_exit__(r.status_code, errh)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise SystemExit(e)
        return r

    def post(self, api, params=None):
        api = __normalize_api__(api)
        util.logger.debug('POST: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.post(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.post(url=self.root_url + api, auth=self.get_credentials(), params=params)
            r.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            __log_and_exit__(r.status_code, errh)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise SystemExit(e)
        return r

    def delete(self, api, params=None):
        api = __normalize_api__(api)
        util.logger.debug('DELETE: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.delete(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.delete(url=self.root_url + api, auth=self.get_credentials(), params=params)
            r.raise_for_status()
        except requests.exceptions.HTTPError as errh:
            __log_and_exit__(r.status_code, errh)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise SystemExit(e)



    def urlstring(self, api, params):
        first = True
        url = "{0}{1}".format(str(self), api)
        if params is None:
            return url
        for p in params:
            if params[p] is None:
                continue
            sep = '?' if first else '&'
            first = False
            if isinstance(params[p], datetime.date):
                params[p] = util.format_date(params[p])
            url += '{0}{1}={2}'.format(sep, p, params[p])
        return url

    def audit(self, audit_settings=None):
        util.logger.info('--- Auditing global settings ---')
        problems = []
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

        for key in audit_settings:
            if re.match(r'audit.globalSetting.range', key):
                v = __get_multiple_values__(5, audit_settings[key], 'MEDIUM', 'CONFIGURATION')
                if v is None:
                    util.logger.error(WRONG_CONFIG_MSG, key, audit_settings[key])
                    continue
                if v[0] == 'sonar.dbcleaner.daysBeforeDeletingInactiveShortLivingBranches' and \
                    self.version() >= (8, 0, 0):
                    util.logger.error("Setting %s his ineffective on SonaQube 8.0+, skipping audit",
                                      v[0])
                    continue
                problems += __audit_setting_range__(platform_settings, v[0], v[1], v[2], v[3], v[4])
            elif re.match(r'audit.globalSetting.value', key):
                v = __get_multiple_values__(4, audit_settings[key], 'MEDIUM', 'CONFIGURATION')
                if v is None:
                    util.logger.error(WRONG_CONFIG_MSG, key, audit_settings[key])
                    continue
                problems += __audit_setting_value__(platform_settings, v[0], v[1], v[2], v[3])
            elif re.match(r'audit.globalSetting.isSet', key):
                v = __get_multiple_values__(3, audit_settings[key], 'MEDIUM', 'CONFIGURATION')
                if v is None:
                    util.logger.error(WRONG_CONFIG_MSG, key, audit_settings[key])
                    continue
                problems += __audit_setting_is_set__(platform_settings, v[0])
            elif re.match(r'audit.globalSetting.isNotSet', key):
                v = __get_multiple_values__(3, audit_settings[key], 'MEDIUM', 'CONFIGURATION')
                if v is None:
                    util.logger.error(WRONG_CONFIG_MSG, key, audit_settings[key])
                    continue
                problems += __audit_setting_is_not_set__(platform_settings, v[0], v[1], v[2])

        problems += (
            __audit_maintainability_rating_grid__(
                platform_settings['sonar.technicalDebt.ratingGrid'],
                audit_settings)
            + self.__audit_project_default_visibility__()
            + audit_sysinfo(self.sys_info())
            + self.__audit_admin_password__()
            + self.__audit_global_permissions__()
        )
        return problems

    def __audit_project_default_visibility__(self):
        util.logger.info('Auditing project default visibility')
        problems = []
        if self.version() < (8, 7, 0):
            resp = self.get('navigation/organization', params={'organization': 'default-organization'})
            data = json.loads(resp.text)
            visi = data['organization']['projectVisibility']
        else:
            resp = self.get('settings/values', params={'keys': 'projects.default.visibility'})
            data = json.loads(resp.text)
            visi = data['settings'][0]['value']
        util.logger.info('Project default visibility is %s', visi)
        if conf.get_property('checkDefaultProjectVisibility') and visi != 'private':
            rule = rules.get_rule(rules.RuleId.SETTING_PROJ_DEFAULT_VISIBILITY)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msq.format(visi)))
        return problems

    def __audit_admin_password__(self):
        util.logger.info('Auditing admin password')
        problems = []
        try:
            r = requests.get(url=self.root_url + '/api/authentication/validate', auth=('admin', 'admin'))
            data = json.loads(r.text)
            if data.get('valid', False):
                rule = rules.get_rule(rules.RuleId.DEFAULT_ADMIN_PASSWORD)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg))
            else:
                util.logger.info("User 'admin' default password has been changed")
        except requests.RequestException as e:
            util.logger.error("HTTP request exception for %s/%s: %s", self.root_url,
                              'api/authentication/validate', str(e))
            raise
        return problems

    def __get_permissions__(self, perm_type):
        resp = self.get('permissions/{0}'.format(perm_type), params={'ps': 100})
        data = json.loads(resp.text)
        active_perms = []
        for item in data.get(perm_type, []):
            if item['permissions']:
                active_perms.append(item)
        return active_perms

    def __audit_group_permissions__(self):
        util.logger.info('Auditing group global permissions')
        problems = []
        groups = self.__get_permissions__('groups')
        if len(groups) > 10:
            problems.append(
                pb.Problem(typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM,
                           'Too many ({0}) groups with global permissions'.format(len(groups))))
        for gr in groups:
            if gr['name'] == 'Anyone':
                problems.append(pb.Problem(typ.Type.SECURITY, sev.Severity.HIGH,
                                           "Group 'Anyone' should not have any global permission"))
            if gr['name'] == 'sonar-users' and (
                    'admin' in gr['permissions'] or 'gateadmin' in gr['permissions'] or
                    'profileadmin' in gr['permissions'] or 'provisioning' in gr['permissions']):
                rule = rules.get_rule(rules.RuleId.PROJ_PERM_SONAR_USERS_ELEVATED_PERMS)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg))

        perm_counts = __get_permissions_count__(groups)
        maxis = {'admin': 2, 'gateadmin': 2, 'profileadmin': 2, 'scan': 2, 'provisioning': 3}
        for perm in GLOBAL_PERMISSIONS:
            if perm in maxis and perm_counts[perm] > maxis[perm]:
                problems.append(
                    pb.Problem(typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM,
                               'Too many ({}) groups with permission {}, {} max recommended'.format(
                                   perm_counts[perm], GLOBAL_PERMISSIONS[perm], maxis[perm])))
        return problems

    def __audit_user_permissions__(self):
        util.logger.info('Auditing users global permissions')
        problems = []
        users = self.__get_permissions__('users')
        if len(users) > 10:
            problems.append(
                pb.Problem(
                    typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM,
                    'Too many ({}) users with direct global permissions, use groups instead'.format(len(users))))

        perm_counts = __get_permissions_count__(users)
        maxis = {'admin': 3, 'gateadmin': 3, 'profileadmin': 3, 'scan': 3, 'provisioning': 3}
        for perm in GLOBAL_PERMISSIONS:
            if perm in maxis and perm_counts[perm] > maxis[perm]:
                problems.append(
                    pb.Problem(
                        typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM,
                        'Too many ({}) users with permission {}, use groups instead'.format(
                            perm_counts[perm], GLOBAL_PERMISSIONS[perm])))
        return problems

    def __audit_global_permissions__(self):
        util.logger.info('--- Auditing global permissions ---')
        return self.__audit_user_permissions__() + self.__audit_group_permissions__()


# --------------------- Static methods -----------------
# this is a pointer to the module object instance itself.
this = sys.modules[__name__]
this.context = Environment("http://localhost:9000", '')


def set_env(url, token):
    this.context = Environment(url, token)
    util.logger.debug('Setting GLOBAL environment: %s@%s', token, url)


def set_token(token):
    this.context.set_token(token)


def get_token():
    return this.context.token


def get_credentials():
    return (this.context.token, '')


def set_url(url):
    this.context.set_url(url)


def get_url():
    return this.context.root_url


def __normalize_api__(api):
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


def __log_and_exit__(code, err):
    if code == 401:
        util.logger.fatal(AUTHENTICATION_ERROR_MSG)
        raise SystemExit(err)
    if code == 403:
        util.logger.fatal(AUTORIZATION_ERROR_MSG)
        raise SystemExit(err)
    if (code // 100) != 2:
        util.logger.fatal(HTTP_FATAL_ERROR_MSG, code, err)
        raise SystemExit(err)


def get(api, params=None, ctxt=None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.get(api, params)


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


def __get_memory__(setting):
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


def __get_store_size__(setting):
    (val, unit) = setting.split(' ')
    # For decimal separator in some countries
    val = val.replace(',', '.')
    if unit == 'MB':
        return float(val)
    elif unit == 'GB':
        return float(val) * 1024
    return None


def __audit_setting_range__(settings, key, min_val, max_val, severity=sev.Severity.MEDIUM, domain=typ.Type.CONFIGURATION):
    value = float(settings[key])
    min_v = float(min_val)
    max_v = float(max_val)
    util.logger.info("Auditing that setting %s is within recommended range [%f-%f]", key, min_v, max_v)
    problems = []
    if value < min_v or value > max_v:
        problems.append(pb.Problem(
            domain, severity,
            "Setting {} value {} is outside recommended range [{}-{}]".format(
                key, value, min_val, max_val)))
    return problems


def __audit_setting_value__(settings, key, value, severity=sev.Severity.MEDIUM, domain=typ.Type.CONFIGURATION):
    util.logger.info("Auditing that setting %s has common/recommended value '%s'", key, value)
    s = settings.get(key, '')
    problems = []
    if s != value:
        problems.append(pb.Problem(
            domain, severity,
            "Setting {} has potentially incorrect or unsafe value '{}'".format(key, s)))
    return problems


def __audit_setting_is_set__(settings, key):
    util.logger.info("Auditing that setting %s is set", key)
    problems = []
    if key in settings and settings[key] != '':
        util.logger.info("Setting %s is set with value %s", key, settings[key])
    else:
        rule = rules.get_rule(rules.RuleId.SETTING_NOT_SET)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(key)))
    return problems


def __audit_setting_is_not_set__(settings, key, severity=sev.Severity.MEDIUM, domain=typ.Type.CONFIGURATION):
    util.logger.info("Auditing that setting %s is not set", key)
    problems = []
    if key in settings and settings[key] != '':
        problems.append(
            pb.Problem(domain, severity,
                       "Setting {} is set, although it should probably not".format(key)))
    else:
        util.logger.info("Setting %s is not set", key)
    return problems


def __audit_maintainability_rating_range__(value, min_val, max_val, rating_letter,
                                           severity=sev.Severity.MEDIUM, domain=typ.Type.CONFIGURATION):
    util.logger.debug("Checking that maintainability rating threshold %3.0f%% for '%s' is \
within recommended range [%3.0f%%-%3.0f%%]", value * 100, rating_letter, min_val * 100, max_val * 100)
    value = float(value)
    problems = []
    if value < min_val or value > max_val:
        util.logger.warning("Maintainability rating threshold %3.0f%% for '%s' is outside of recommended range [%3.0f%%-%3.0f%%]",
                value * 100, rating_letter, min_val * 100, max_val * 100)
        problems.append(pb.Problem(
            domain, severity,
            'Maintainability rating threshold {}% for {} is NOT within recommended range [{}%-{}%]'.format(
                value * 100, rating_letter, min_val * 100, max_val * 100)))
    return problems


def __audit_maintainability_rating_grid__(grid, audit_settings):
    thresholds = grid.split(',')
    problems = []
    util.logger.debug("Auditing maintainabillity rating grid")
    for key in audit_settings:
        if not re.match(r'audit.globalSetting.maintainabilityRating', key):
            continue
        util.logger.debug('Unpacking %s', key)
        (_, _, _, letter, _, _) = key.split('.')
        if letter not in ['A', 'B', 'C', 'D']:
            util.logger.error("Incorrect audit configuration setting %s, skipping audit", key)
            continue
        value = thresholds[ord(letter.upper()) - 65]
        (min_val, max_val, severity, domain) = __get_multiple_values__(
            4, audit_settings[key], sev.Severity.MEDIUM, typ.Type.CONFIGURATION)
        problems += __audit_maintainability_rating_range__(
            float(value), float(min_val), float(max_val),
            letter, severity, domain)
    return problems


def __check_log_level__(sysinfo):
    util.logger.debug('Auditing log levels')
    problems = []
    log_level = sysinfo["Web Logging"]["Logs Level"]
    if log_level == "DEBUG":
        util.logger.warning("DEBUG log level is active, revert to INFO fro performance")
        problems.append(pb.Problem(
            typ.Type.PERFORMANCE, sev.Severity.HIGH,
            "Log level is set to DEBUG, this may affect platform performance, \
reverting to INFO is recommended"))
    elif log_level == "TRACE":
        util.logger.warning("TRACE log level is active, revert to INFO fro performance")
        problems.append(pb.Problem(
            typ.Type.PERFORMANCE, sev.Severity.CRITICAL,
            "Log level set to TRACE, this does very negatively affect platform performance, \
reverting to INFO is required"))
    return problems


def __audit_web_settings__(sysinfo):
    util.logger.debug('Auditing Web settings')
    problems = []
    web_ram = __get_memory__(sysinfo['Settings']['sonar.web.javaOpts'])
    if web_ram < 1024 or web_ram > 2048:
        util.logger.warning("sonar.web.javaOpts -Xmx memory setting value is %d MB, "
                         "outside of the recommended range [1024-2048]", web_ram)
        rule = rules.get_rule(rules.RuleId.SETTING_WEB_HEAP)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(web_ram, 1024, 2048)))
    else:
        util.logger.debug("sonar.web.javaOpts -Xmx memory setting value is %d MB, "
                         "within the recommended range [1024-2048]", web_ram)
    return problems


def __audit_ce_settings__(sysinfo):
    util.logger.info('Auditing CE settings')
    problems = []
    ce_ram = __get_memory__(sysinfo['Settings']['sonar.ce.javaOpts'])
    ce_tasks = sysinfo['Compute Engine Tasks']
    ce_workers = ce_tasks['Worker Count']
    MAX_WORKERS = 4
    if ce_workers > MAX_WORKERS:
        util.logger.warning("%d CE workers configured, incorrect compared to the max %d recommended",
                         ce_workers, MAX_WORKERS)
        rule = rules.get_rule(rules.RuleId.SETTING_CE_TOO_MANY_WORKERS)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_workers, MAX_WORKERS)))
    else:
        util.logger.debug("%d CE workers configured, correct compared to the max %d recommended",
                         ce_workers, MAX_WORKERS)

    if ce_ram < 512 * ce_workers or ce_ram > 2048 * ce_workers:
        util.logger.warning("sonar.ce.javaOpts -Xmx memory setting value is %d MB, "
                         "outside recommended range ([512-2048] x %d workers)", ce_ram, ce_workers)
        rule = rules.get_rule(rules.RuleId.SETTING_CE_HEAP)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_ram, 512, 2048, ce_workers)))
    else:
        util.logger.debug("sonar.ce.javaOpts -Xmx memory setting value is %d MB, "
                         "within recommended range ([512-2048] x %d workers)", ce_ram, ce_workers)
    return problems


def __audit_ce_background_tasks__(sysinfo):
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
        util.logger.warning('Number of failed background tasks (%d), and failure rate %d%% is high',
                         ce_error, int(failure_rate * 100))
        rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_FAILURE_RATE_HIGH)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(int(failure_rate * 100))))
    else:
        util.logger.debug('Number of failed background tasks (%d), and failure rate %d%% is OK',
                         ce_error, int(failure_rate * 100))

    if ce_pending > 100:
        util.logger.warning('Number of pending background tasks (%d) is very high', ce_pending)
        rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_PENDING_QUEUE_VERY_LONG)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_pending)))
    elif ce_pending > 20 and ce_pending > (10*ce_workers):
        util.logger.warning('Number of pending background tasks (%d) is high', ce_pending)
        rule = rules.get_rule(rules.RuleId.BACKGROUND_TASKS_PENDING_QUEUE_LONG)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(ce_pending)))
    else:
        util.logger.debug('Number of pending background tasks (%d) is OK', ce_pending)
    return problems


def __audit_es_settings__(sysinfo):
    util.logger.info('Auditing Search Server settings')
    problems = []
    es_ram = __get_memory__(sysinfo['Settings']['sonar.search.javaOpts'])
    index_size = __get_store_size__(sysinfo['Search State']['Store Size'])
    if es_ram < 2 * index_size and es_ram < index_size + 1000:
        util.logger.warning("Search server memory %d MB is inconsystent wrt to index size of %d MB", es_ram, index_size)
        rule = rules.get_rule(rules.RuleId.SETTING_ES_HEAP)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(es_ram, index_size)))
    else:
        util.logger.debug("Search server memory %d MB is correct wrt to index size of %d MB", es_ram, index_size)
    return problems


def __audit_jdbc_url__(sysinfo):
    util.logger.info('Auditing JDBC settings')
    problems = []
    stats = sysinfo.get('Settings')
    if stats is None:
        util.logger.error("Can't verify Database settings in System Info File, was it corrupted or redacted ?")
        return problems
    url = stats.get('sonar.jdbc.url', None)
    util.logger.debug('JDBC URL = %s', str(url))
    if url is None:
        rule = rules.get_rule(rules.RuleId.SETTING_JDBC_URL_NOT_SET)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg))
    elif re.search(r':(postgresql://|sqlserver://|oracle:thin:@)(localhost|127\.0+\.0+\.1)[:;/]', url):
        rule = rules.get_rule(rules.RuleId.SETTING_DB_ON_SAME_HOST)
        problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(url)))
    return problems

def __audit_dce_settings__(sysinfo):
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
        __audit_web_settings__(sysinfo) +
        __audit_ce_settings__(sysinfo) +
        __audit_ce_background_tasks__(sysinfo) +
        __audit_es_settings__(sysinfo) +
        __audit_dce_settings__(sysinfo) +
        __audit_jdbc_url__(sysinfo)
    )


def __get_permissions_count__(users_or_groups):
    perm_counts = dict(zip(GLOBAL_PERMISSIONS.keys(), [0, 0, 0, 0, 0, 0, 0]))
    for user_or_group in users_or_groups:
        for perm in GLOBAL_PERMISSIONS:
            if perm in user_or_group['permissions']:
                perm_counts[perm] += 1
    return perm_counts


def __get_multiple_values__(n, setting, severity, domain):
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
