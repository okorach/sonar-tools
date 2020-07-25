#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3

import sys
import re
import json
import requests
import sonarqube.utilities as util

HTTP_ERROR_MSG = "%s%s raised error %s"
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
        redacted_token = re.sub(r'(...).*(...)', '\1***\2', self.token)
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
            version = "{0}.{1}.{2}".format(self.major, self.minor, self.patch)
        return version

    def version_higher_or_equal_than(self, version):
        (major, minor, patch) = version.split('.')
        self.get_version()
        if patch is None:
            patch = 0
        if major > self.major:
            return True
        if major == self.major and minor > self.minor:
            return True
        if major == self.major and minor == self.minor and patch >= self.patch:
            return True
        return False

    def get(self, api, parms = None):
        #for k in parms:
        #    parms[k] = urllib.parse.quote(str(parms[k]), safe=':')
        api = normalize_api(api)
        util.logger.debug('GET: %s', self.urlstring(api, parms))
        try:
            if parms is None:
                r = requests.get(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.get(url=self.root_url + api, auth=self.get_credentials(), params=parms)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise
        if r.status_code != 200:
            util.logger.error(HTTP_ERROR_MSG, this.root_url, api, r.text)
        return r

    def post(self, api, parms = None):
        api = normalize_api(api)
        util.logger.debug('POST: %s', self.urlstring(api, parms))
        try:
            if parms is None:
                r = requests.post(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.post(url=self.root_url + api, auth=self.get_credentials(), params=parms)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise
        if (r.status_code // 100) != 2:
            util.logger.error(HTTP_ERROR_MSG, this.root_url, api, r.text)
        return r

    def delete(self, api, parms = None):
        api = normalize_api(api)
        util.logger.debug('DELETE: %s', self.urlstring(api, parms))
        try:
            if parms is None:
                r = requests.delete(url=self.root_url + api, auth=self.get_credentials())
            else:
                r = requests.delete(url=self.root_url + api, auth=self.get_credentials(), params=parms)
        except requests.RequestException as e:
            util.logger.error(str(e))
            raise
        if (r.status_code // 100) != 2:
            util.logger.error(HTTP_ERROR_MSG, this.root_url, api, r.text)
        return r

    def urlstring(self, api, parms):
        first = True
        url = "{0}{1}".format(str(self), api)
        if parms is not None:
            for p in parms:
                sep = '?' if first else '&'
                first = False
                url += '{0}{1}={2}'.format(sep, p, parms[p])
        return url

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

def get(api, parms = None, ctxt = None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.get(api, parms)

def post(api, parms = None, ctxt = None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.post(api, parms)

def delete(api, parms = None, ctxt = None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.delete(api, parms)

def add_standard_arguments(parser):
    parser.add_argument('-t', '--token', required=True,
                        help='Token to authenticate to SonarQube - Unauthenticated usage is not possible')
    parser.add_argument('-u', '--url', required=False, default=DEFAULT_URL,
                        help='Root URL of the SonarQube server, default is {0}'.format(DEFAULT_URL))
    parser.add_argument('-k', '--componentKeys', '--projectKey', '--projectKeys', \
                        help='Commas separated key of the components', required=False)
