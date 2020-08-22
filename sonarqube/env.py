#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "platform" concept

'''
import sys
import re
import datetime
import json
import requests
import sonarqube.utilities as util

HTTP_ERROR_MSG = "%s%s raised error %d: %s"
DEFAULT_URL = 'http://localhost:9000'

class Environment:

    def __init__(self, url, token):
        self.root_url = url
        self.token = token
        self.version = None
        self.major = None
        self.minor = None
        self.patch = None
        self.build = None

    def __str__(self):
        redacted_token = re.sub(r'(...).*(...)', r'\1***\2', self.token)
        return "{0}@{1}".format(redacted_token, self.root_url)

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

    def get_version(self):
        if self.version is None:
            resp = self.get('/api/server/version')
            (self.major, self.minor, self.patch, self.build) = resp.text.split('.')
        return (int(self.major), int(self.minor), int(self.patch))

    def get_sysinfo(self):
        resp = self.get('system/info')
        sysinfo = json.loads(resp.text)
        return sysinfo

    def get(self, api, params = None):
        api = __normalize_api__(api)
        util.logger.debug('GET: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.get(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.get(url=self.root_url + api, auth=self.get_credentials(), params=params)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise
        if (r.status_code // 100) != 2:
            util.logger.error(HTTP_ERROR_MSG, self.root_url, api, r.status_code, r.text)
        return r

    def post(self, api, params = None):
        api = __normalize_api__(api)
        util.logger.debug('POST: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.post(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.post(url=self.root_url + api, auth=self.get_credentials(), params=params)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise
        if (r.status_code // 100) != 2:
            util.logger.error(HTTP_ERROR_MSG, self.root_url, api, r.status_code, r.text)
        return r

    def delete(self, api, params = None):
        api = __normalize_api__(api)
        util.logger.debug('DELETE: %s', self.urlstring(api, params))
        try:
            if params is None:
                r = requests.delete(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.delete(url=self.root_url + api, auth=self.get_credentials(), params=params)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise
        if (r.status_code // 100) != 2:
            util.logger.error(HTTP_ERROR_MSG, self.root_url, api, r.status_code, r.text)
        return r

    def urlstring(self, api, params):
        first = True
        url = "{0}{1}".format(str(self), api)
        if params is not None:
            for p in params:
                sep = '?' if first else '&'
                first = False
                if isinstance(params[p], datetime.date):
                    params[p] = util.format_date(params[p])
                url += '{0}{1}={2}'.format(sep, p, params[p])
        return url

    def __verify_project_default_visibility__(self):
        resp = self.get('navigation/organization', params={'organization':'default-organization'})
        data = json.loads(resp.text)
        visi = data['organization']['projectVisibility']
        if visi == 'private':
            util.logger.info('Project default visibility is private')
        else:
            util.logger.warning('Project default visibility is %s, which can be a security risk', visi)
            return 1
        return 0

    def __check_admin_password__(self):
        try:
            r = requests.get(url=self.root_url + '/api/authentication/validate', auth=('admin','admin'))
            data = json.loads(r.text)
            if data.get('valid', False):
                util.logger.error("User 'admin' still using the default password, this must be changed ASAP")
                return 1
            else:
                util.logger.info("User 'admin' default password has been changed")
        except requests.RequestException as e:
            util.logger.error("HTTP request exception for %s/%s: %s", self.root_url,
                              'api/authentication/validate', str(e))
            raise
        return 0

    def audit(self):
        util.logger.info('Auditing global settings')
        resp = self.get('settings/values')
        json_s = json.loads(resp.text)
        settings = {}
        for s in json_s['settings']:
            if 'value' in s:
                settings[s['key']] = s['value']
            else:
                settings[s['key']] = ','.join(s['values'])
        issues = __check_setting_value__(settings, 'sonar.forceAuthentication', 'true')
        issues += __check_setting_value__(settings, 'sonar.cpd.cross_project', 'false')
        issues += __check_setting_value__(settings, 'sonar.global.exclusions', '')
        if self.get_version() < (8,0,0):
            issues += __check_setting_range__(settings, \
                'sonar.dbcleaner.daysBeforeDeletingInactiveShortLivingBranches', 10, 60)
        issues += __check_setting_range__(settings, \
            'sonar.dbcleaner.daysBeforeDeletingClosedIssues', 10, 60)
        issues += __check_setting_range__(settings, \
            'sonar.dbcleaner.hoursBeforeKeepingOnlyOneSnapshotByDay', 12, 240)
        issues += __check_setting_range__(settings, \
            'sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByWeek', 2, 12)
        issues += __check_setting_range__(settings, \
            'sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByMonth', 26, 104)
        issues += __check_setting_range__(settings, \
            'sonar.dbcleaner.weeksBeforeDeletingAllSnapshots', 104, 260)
        issues += __check_setting_defined__(settings, 'sonar.core.serverBaseURL')

        issues += __check_maintainability_rating_grid__(settings['sonar.technicalDebt.ratingGrid'])
        issues += __check_setting_range__(settings, 'sonar.technicalDebt.developmentCost', 20, 30)

        issues += self.__verify_project_default_visibility__()
        issues += audit_sysinfo(self.get_sysinfo())
        issues += self.__check_admin_password__()
        return issues

#--------------------- Static methods, not recommended -----------------
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

def get(api, params = None, ctxt = None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.get(api, params)

def post(api, params = None, ctxt = None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.post(api, params)

def delete(api, params = None, ctxt = None):
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
    if unit == 'MB':
        return int(val)
    elif unit == 'GB':
        return int(val) * 1024
    return None

def __check_setting_range__(settings, key, min_val, max_val):
    value = int(settings[key])
    if value >= min_val and value <= max_val:
        util.logger.info("Setting %s value %d is within recommended range [%d-%d]",
                         key, value, min_val, max_val)
    else:
        util.logger.warning("Setting %s value %d is outside recommended range [%d-%d]",
                            key, value, min_val, max_val)
        return 1
    return 0

def __check_setting_value__(settings, key, value):
    s = settings.get(key, '')
    if s == value:
        util.logger.info("Setting %s has common/recommended value '%s'", key, s)
    else:
        util.logger.warning("Setting %s has potentially incorrect/unsafe value '%s'", key, s)
        return 1
    return 0

def __check_setting_defined__(settings, key):
    if key in settings and settings[key] != '':
        util.logger.info("Setting %s is set with value %s", key, settings[key])
    else:
        util.logger.warning("Setting %s is not set, although it should", key)
        return 1
    return 0

def __check_maintainability_rating_range__(value, min_val, max_val, rating_letter):
    value = float(value)
    if value < min_val or value > max_val:
        util.logger.warning('Maintainability rating threshold %3.0f%% for %s is \
NOT within recommended range [%3.0f%%-%3.0f%%]', value*100, rating_letter, min_val*100, max_val*100)
        return 1
    else:
        util.logger.info('Maintainability rating threshold %3.0f%% for %s is \
within recommended range [%3.0f%%-%3.0f%%]', value*100, rating_letter, min_val*100, max_val*100)
    return 0

def __check_maintainability_rating_grid__(grid):
    (a, b, c, d) = grid.split(',')
    issues = __check_maintainability_rating_range__(a, 0.03, 0.05, 'A')
    issues += __check_maintainability_rating_range__(b, 0.07, 0.10, 'B')
    issues += __check_maintainability_rating_range__(c, 0.15, 0.20, 'C')
    issues += __check_maintainability_rating_range__(d, 0.40, 0.50, 'D')
    return issues

def __check_log_level__(sysinfo):
    log_level = sysinfo["Web Logging"]["Logs Level"]
    issues = 0
    if log_level == "DEBUG":
        util.logger.warning("Log level is set to DEBUG, this may affect platform performance, \
reverting to INFO is recommended")
        issues += 1
    elif log_level == "TRACE":
        util.logger.warning("Log level set to TRACE, this does very negatively affect platform performance, \
reverting to INFO is required")
        issues += 1
    return issues

def __check_web_settings__(sysinfo):
    util.logger.info('Auditing Web settings')
    issues = 0
    web_ram = __get_memory__(sysinfo['Settings']['sonar.web.javaOpts'])
    if web_ram < 1024 or web_ram > 2048:
        util.logger.warning("sonar.web.javaOpts -Xmx memory setting value is %dM, \
not in recommended range [1024-2048]", web_ram)
        issues += 1
    else:
        util.logger.info("sonar.web.javaOpts -Xmx memory setting value is %dM, \
within the recommended range [1024-2048]", web_ram)
    return issues

def __check_ce_settings__(sysinfo):
    util.logger.info('Auditing CE settings')
    issues = 0
    ce_ram = __get_memory__(sysinfo['Settings']['sonar.ce.javaOpts'])
    ce_tasks = sysinfo['Compute Engine Tasks']
    ce_workers = ce_tasks['Worker Count']
    if ce_workers > 4:
        util.logger.warning("%d CE workers configured, more than the max 4 recommended", ce_workers)
        issues += 1
    else:
        util.logger.info("%d CE workers configured, correct compared to the max 4 recommended", ce_workers)

    if ce_ram < 512 * ce_workers or ce_ram > 2048 * ce_workers:
        util.logger.warning("sonar.ce.javaOpts -Xmx memory setting value is %dM, \
not in recommended range ([512-2048] x %d workers)", ce_ram, ce_workers)
        issues += 1
    else:
        util.logger.info("sonar.ce.javaOpts -Xmx memory setting value is %dM, \
within recommended range ([512-2048] x %d workers)", ce_ram, ce_workers)
    return issues

def __check_ce_background_tasks__(sysinfo):
    util.logger.info('Auditing CE background tasks')
    issues = 0
    ce_tasks = sysinfo['Compute Engine Tasks']
    ce_workers = ce_tasks['Worker Count']
    ce_success = ce_tasks["Processed With Success"]
    ce_error = ce_tasks["Processed With Error"]
    ce_pending = ce_tasks["Pending"]
    failure_rate = ce_error / (ce_success+ce_error)
    if ce_error > 10 and failure_rate > 0.01:
        util.logger.warning('Background task failure rate (%d%%) is high, \
verify failed background tasks', int(failure_rate*100))
        issues += 1
    else:
        util.logger.info('Number of failed background tasks (%d), and failure rate %d%% is OK',
                         ce_error, failure_rate)

    if ce_pending > 100:
        util.logger.warning('Number of pending background tasks (%d) is very high, verify CE dimensioning',
                            ce_pending)
        issues += 1
    elif ce_pending > 20 and ce_pending > (10*ce_workers):
        util.logger.warning('Number of pending background tasks (%d) is high, verify CE dimensioning', ce_pending)
        issues += 1
    else:
        util.logger.info('Number of pending background tasks (%d) is OK', ce_pending)
    return issues

def __check_es_settings__(sysinfo):
    util.logger.info('Auditing Search Server settings')
    issues = 0
    es_ram = __get_memory__(sysinfo['Settings']['sonar.search.javaOpts'])
    index_size = __get_store_size__(sysinfo['Search State']['Store Size'])
    if es_ram < 2 * index_size and es_ram < index_size + 1000:
        util.logger.warning("sonar.search.javaOpts -Xmx memory setting value is %dM,\
too low for index size of %d MB", es_ram, index_size)
        issues += 1
    else:
        util.logger.info("Search server memory %d MB is correct wrt to index size of %d MB", es_ram, index_size)
    return issues

def __check_dce_settings__(sysinfo):
    stats = sysinfo.get('Statistics')
    issues = 0
    if stats is None:
        util.logger.warning("Can't verify edition in System Info File, was it corrupted or redacted ?")
        return 0
    edition = stats.get('edition', None)
    if stats is None:
        util.logger.warning("Can't verify edition in System Info File, was it corrupted or redacted ?")
        return 0
    if edition != "datacenter":
        util.logger.info('Not a Data Center Edition, skipping DCE checks')
        return 0
    # Verify that app nodes have the same plugins installed
    appnodes = sysinfo['Application Nodes']
    ref_plugins = json.dumps(appnodes[0]['Plugins'], sort_keys=True, indent=3, separators=(',', ': '))
    ref_name = appnodes[0]['Name']
    ref_version = appnodes[0]['System']['Version']
    for node in appnodes:
        node_version = node['System']['Version']
        if node_version != ref_version:
            util.logger.error('App nodes %s and %s do not run the same SonarQube versions, this must be corrected ASAP',
                              ref_name, node['Name'])
            issues += 1
        node_plugins = json.dumps(node['Plugins'], sort_keys=True, indent=3, separators=(',', ': '))
        if node_plugins != ref_plugins:
            util.logger.error('Some plugins on app nodes %s and %s are different, this must be corrected ASAP',
                              ref_name, node['Name'])
            issues += 1
        if not node['System']['Official Distribution']:
            util.logger.error('Node %s does not run an official distribution of SonarQube',
                              node['Name'])
            issues += 1
        if node['Health'] != "GREEN":
            util.logger.warning('Node %s health is %s', node['Name'], node['Health'])
            issues += 1
    return issues


def audit_sysinfo(sysinfo):
    issues = 0
    issues += __check_web_settings__(sysinfo)
    issues += __check_ce_settings__(sysinfo)
    issues += __check_ce_background_tasks__(sysinfo)
    issues += __check_es_settings__(sysinfo)
    issues += __check_dce_settings__(sysinfo)
    return issues