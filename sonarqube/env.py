#!python3

import sys
import requests

# this is a pointer to the module object instance itself.
this = sys.modules[__name__]
this.token = ''
this.root_url= "http://localhost:9000"
this.debug = True

class Environment:

    def __init__(self):
        self.root_url = ''
        self.token = ''

    def set_env(self, url, token):
        self.root_url = url
        self.token = token
        if (this.debug):
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
    
    def get2(self, api, parms):
        if (this.debug):
            print ('GET environment: '+ self.token + '@' + self.root_url)
        for p in parms:
            print(p + " = " + parms[p])
        return requests.get(url=self.root_url + api, auth=self.get_credentials(), params=parms)

    def get(self, api, parms):
        if (this.debug):
            print ('GET: '+ self.urlstring(api, parms))
        return requests.get(url=this.root_url + api, auth=self.get_credentials(), params=parms)

    def post(self, api, parms):
        if (this.debug):
            print ('POST: '+ self.urlstring(api, parms))
        return requests.post(url=self.root_url + api, auth=self.get_credentials(), params=parms)

    def delete(self, api, parms):
        if (this.debug):
            print ('DELETE: '+ self.urlstring(api, parms))
        return requests.delete(url=self.root_url + api, auth=self.get_credentials(), params=parms)

    def to_string(self):
        return "URL = " + self.root_url + "\n" + "TOKEN = " + self.token

    def urlstring(self, api, parms):
        pstr = None
        for p in parms:
            if pstr is None:
                pstr = p + '=' + parms[p]
            else:
                pstr = pstr + '&' + p + '=' + parms[p]
        return this.token + '@' + this.root_url + api + '?' + pstr

#--------------------- Static methods, not recommended -----------------
def set_env(url, tok):
    this.root_url = url
    this.token = tok
    if (this.debug):
        print ('Setting GLOBAL environment: '+ this.token + '@' + this.root_url)


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

def debug(str):
    if this.debug:
        print(str)

def get(api, parms):
    if (this.debug):
        pstr = ''
        for p in parms:
            pstr = pstr + p + '=' + parms[p] + '&'
        print ('GLOBAL GET: ' + this.token + '@' + this.root_url + api + '?' + pstr)
    return requests.get(url=this.root_url + api, auth=get_credentials(), params=parms)

def post(api, parms):
    if (this.debug):
        pstr = ''
        for p in parms:
            pstr = pstr + p + '=' + parms[p] + '&'
        print ('GLOBAL POST: ' + this.token + '@' + this.root_url + api + '?' + pstr)
    return requests.post(url=this.root_url + api, auth=get_credentials(), params=parms)

def delete(api, parms):
    if (this.debug):
        pstr = ''
        for p in parms:
            pstr = pstr + p + '=' + parms[p] + '&'
        print ('GLOBAL DELETE: ' + this.token + '@' + this.root_url + api + '?' + pstr)
    return requests.delete(url=this.root_url + api, auth=get_credentials(), params=parms)