#!python3

import sys

# this is a pointer to the module object instance itself.
this = sys.modules[__name__]
this.token = ''
this.root_url= "http://localhost:9000"

class Environment:

    def __init__(self):
        self.root_url = ''
        self.token = ''

    def set_token(self, token):
        self.token = token

    def get_token(self):
        return self.token

    def get_credentials(self):
        return (self.token, '')

    def set_url(self, url):
        self.root_url = url

    def get_root_url(self):
        return self.root_url
    

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