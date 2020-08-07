#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "platform" concept

'''
import sys
import re
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

    def get(self, api, params = None):
        #for k in params:
        #    params[k] = urllib.parse.quote(str(params[k]), safe=':')
        api = normalize_api(api)
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
        api = normalize_api(api)
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
        api = normalize_api(api)
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
                url += '{0}{1}={2}'.format(sep, p, params[p])
        return url

    def __verify_setting__(self, settings, key, value):
        s = settings.get(key, '')
        if s == value:
            util.logger.info("Setting %s has common/recommended value '%s'", key, s)
        else:
            util.logger.warning("Setting %s has potentially incorrect/unsafe value '%s'", key, s)
            return 1
        return 0

    def __verify_setting_defined__(self, settings, key):
        if key in settings and settings[key] != '':
            util.logger.info("Setting %s is set with value %s", key, settings[key])
        else:
            util.logger.warning("Setting %s is not set, although it should", key)
            return 1
        return 0

    def __verify_setting_range__(self, settings, key, min_val, max_val):
        value = int(settings[key])
        if value >= min_val and value <= max_val:
            util.logger.info("Setting %s value %d is within recommended range [%d-%d]", key, value, min_val, max_val)
        else:
            util.logger.warning("Setting %s value %d is outside recommended range [%d-%d]", key, value, min_val, max_val)
            return 1
        return 0

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

    def __check_rating_range__(self, value, min_val, max_val, rating_letter):
        value = float(value)
        if value < min_val or value > max_val:
            util.logger.warning('Maintainability rating threshold %3.0f%% for %s is NOT within recommended range [%3.0f%%-%3.0f%%]',
                                value*100, rating_letter, min_val*100, max_val*100)
            return 1
        else:
            util.logger.info('Maintainability rating threshold %3.0f%% for %s is within recommended range [%3.0f%%-%3.0f%%]',
                             value*100, rating_letter, min_val*100, max_val*100)
        return 0

    def __verify_rating_grid__(self, grid):
        (a, b, c, d) = grid.split(',')
        issues = self.__check_rating_range__(a, 0.03, 0.05, 'A')
        issues += self.__check_rating_range__(b, 0.07, 0.10, 'B')
        issues += self.__check_rating_range__(c, 0.15, 0.20, 'C')
        issues += self.__check_rating_range__(d, 0.40, 0.50, 'D')
        return issues

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
        issues = self.__verify_setting__(settings, 'sonar.forceAuthentication', 'true')
        issues += self.__verify_setting__(settings, 'sonar.cpd.cross_project', 'false')
        issues += self.__verify_setting__(settings, 'sonar.global.exclusions', '')

        if self.get_version() < (8,0,0):
            issues += self.__verify_setting_range__(settings, \
                'sonar.dbcleaner.daysBeforeDeletingInactiveShortLivingBranches', 10, 60)
        issues += self.__verify_setting_range__(settings, \
            'sonar.dbcleaner.daysBeforeDeletingClosedIssues', 10, 60)
        issues += self.__verify_setting_range__(settings, \
            'sonar.dbcleaner.hoursBeforeKeepingOnlyOneSnapshotByDay', 12, 240)
        issues += self.__verify_setting_range__(settings, \
            'sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByWeek', 2, 12)
        issues += self.__verify_setting_range__(settings, \
            'sonar.dbcleaner.weeksBeforeKeepingOnlyOneSnapshotByMonth', 26, 104)
        issues += self.__verify_setting_range__(settings, \
            'sonar.dbcleaner.weeksBeforeDeletingAllSnapshots', 104, 260)
        issues += self.__verify_setting_defined__(settings, 'sonar.core.serverBaseURL')

        issues += self.__verify_rating_grid__(settings['sonar.technicalDebt.ratingGrid'])
        issues += self.__verify_setting_range__(settings, 'sonar.technicalDebt.developmentCost', 20, 30)

        issues += self.__verify_project_default_visibility__()
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

def normalize_api(api):
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
