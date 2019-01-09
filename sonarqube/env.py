#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3

import sys
import requests
import json

# this is a pointer to the module object instance itself.
this = sys.modules[__name__]
this.token = ''
this.root_url= "http://localhost:9000"

global my_debug
my_debug = False

class Environment:

    def __init__(self, **kwargs):
        self.root_url = kwargs['url']
        self.token = kwargs['token']

    def set_env(self, url, token):
        self.root_url = url
        self.token = token
        global my_debug
        if my_debug:
            print ('Setting environment: '+ self.token + '@' + self.root_url)

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
        debug('GET: '+ self.urlstring(api, parms))
        return requests.get(url=self.root_url + api, auth=self.get_credentials(), params=parms)

    def post(self, api, parms):
        debug('POST: '+ self.urlstring(api, parms))
        return requests.post(url=self.root_url + api, auth=self.get_credentials(), params=parms)

    def delete(self, api, parms):
        debug('DELETE: '+ self.urlstring(api, parms))
        return requests.delete(url=self.root_url + api, auth=self.get_credentials(), params=parms)

    def to_string(self):
        return "URL = " + self.root_url + "\n" + "TOKEN = " + self.token

    def urlstring(self, api, parms):
        pstr = None
        for p in parms:
            #print(p, '->', parms[p])
            if pstr is None:
                pstr = p + '=' + str(parms[p])
            else:
                pstr = pstr + '&' + p + '=' + str(parms[p])
        urlstring = self.token + '@' + self.root_url + api
        if pstr is not None:
            urlstring = urlstring + '?' + pstr
        return urlstring

#--------------------- Static methods, not recommended -----------------
def set_env(url, tok):
    this.root_url = url
    this.token = tok
    debug('Setting GLOBAL environment: '+ this.token + '@' + this.root_url)

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

def debug(arg1, arg2 = '', arg3 = '', arg4 = '', arg5 = '', arg6 = ''):
    global my_debug
    if my_debug is True:
        print( ' '.join([str(x) for x in [arg1, arg2, arg3, arg4, arg4, arg5, arg6]]))

def json_dump_debug(json):
    global my_debug
    if my_debug is True:
        json.dump(json, sys.stdout, sort_keys=True, indent=3, separators=(',', ': '))

def urlstring(api, parms):
    pstr = None
    for p in parms:
        if pstr is None:
            pstr = p + '=' + str(parms[p])
        else:
            pstr = pstr + '&' + p + '=' + str(parms[p])
    urlstring = this.token + '@' + this.root_url + api
    if pstr is not None:
        urlstring = urlstring + '?' + pstr
    return urlstring

def get(api, parms):
    debug('GLOBAL GET: ' + urlstring(api, parms))
    return requests.get(url=this.root_url + api, auth=get_credentials(), params=parms)

def post(api, parms):
    debug('GLOBAL POST: ' + urlstring(api, parms))
    return requests.post(url=this.root_url + api, auth=get_credentials(), params=parms)

def delete(api, parms):
    debug('GLOBAL DELETE: '+ urlstring(api, parms))
    return requests.delete(url=this.root_url + api, auth=get_credentials(), params=parms)

def add_standard_arguments(parser):
    parser.add_argument('-t', '--token',
                        help='Token to authenticate to SonarQube - Unauthenticated usage is not possible',
                        required=True)
    parser.add_argument('-u', '--url', help='Root URL of the SonarQube server, default is http://localhost:9000',
                        required=False, default='http://localhost:9000')
    parser.add_argument('-k', '--componentKeys', '--projectKey', '--projectKeys', help='Commas separated key of the components', required=False)

