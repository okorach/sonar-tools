#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3

import sys
import re
import json
import requests
import sonarqube.utilities as util

# this is a pointer to the module object instance itself.
this = sys.modules[__name__]
this.token = ''
this.root_url= "http://localhost:9000"

my_debug = False

class Environment:

    def __init__(self, url, token):
        self.root_url = url
        self.token = token

    def __str__(self):
        redacted_token = re.sub(r'(....).*(....)', '\1***\2', self.token)
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

    def get(self, api, parms):
        util.logger.info('GET: %s', self.urlstring(api, parms))
        return requests.get(url=self.root_url + api, auth=self.get_credentials(), params=parms)

    def post(self, api, parms):
        util.logger.info('POST: %s', self.urlstring(api, parms))
        return requests.post(url=self.root_url + api, auth=self.get_credentials(), params=parms)

    def delete(self, api, parms):
        util.logger.info('DELETE: %s', self.urlstring(api, parms))
        return requests.delete(url=self.root_url + api, auth=self.get_credentials(), params=parms)

    def urlstring(self, api, parms):
        first = True
        url = "{0}{1}".format(str(self), api)
        for p in parms:
            sep = '?' if first else '&'
            first = False
            url += '{0}{1}={2}'.format(sep, p, parms[p])
        return url

#--------------------- Static methods, not recommended -----------------
def set_env(url, tok):
    this.root_url = url
    this.token = tok
    util.logger.debug('Setting GLOBAL environment: %s@%s', this.token, this.root_url)

def set_token(tok):
    this.token = tok

def get_token():
    return this.token

def get_credentials():
    return (this.token, '')

def set_url(url):
    this.root_url = url

def get_url():
    return this.root_url

def urlstring(api, parms):
    first = True
    redacted_token = re.sub(r'(....).*(....)', '\1***\2', this.token)
    url = "{0}@{1}{2}".format(redacted_token, this.root_url, api)
    for p in parms:
        sep = '?' if first else '&'
        first = False
        url += '{0}{1}={2}'.format(sep, p, parms[p])
    return url

def get(api, parms):
    util.logger.info('GLOBAL GET: %s', urlstring(api, parms))
    return requests.get(url=this.root_url + api, auth=get_credentials(), params=parms)

def post(api, parms):
    util.logger.info('GLOBAL POST: %s', urlstring(api, parms))
    return requests.post(url=this.root_url + api, auth=get_credentials(), params=parms)

def delete(api, parms):
    util.logger.info('GLOBAL DELETE: %s', urlstring(api, parms))
    return requests.delete(url=this.root_url + api, auth=get_credentials(), params=parms)

def add_standard_arguments(parser):
    parser.add_argument('-t', '--token',
                        help='Token to authenticate to SonarQube - Unauthenticated usage is not possible',
                        required=True)
    parser.add_argument('-u', '--url', help='Root URL of the SonarQube server, default is http://localhost:9000',
                        required=False, default='http://localhost:9000')
    parser.add_argument('-k', '--componentKeys', '--projectKey', '--projectKeys', \
        help='Commas separated key of the components', required=False)
