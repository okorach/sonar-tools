#!python3

import json
import requests
from sonarqube.env import get_url, get_credentials, json_dump_debug
import sys

class Rule:

    def __init__(self):
        self.key = None
        self.headline = None
        self.repo = None
        self.severity = None
        self.status = None
        self.actives = None
        self.params = None
        self.remFn = None
        self.createdAt = None
        self.htmlDesc = None
        self.debtOverloaded = False
        self.debtRemFn = None
        self.defaultDebtRemFn = None
        self.defaultRemFn
        self.effortToFixDescription
        self.gapDescription
        self.htmlNote
        self.internalKey
        self.isTemplate
        self.lang
        self.langName
        self.mdDesc
        self.mdNote
        self.noteLogin
        self.remFnOverloaded
        self.sysTags
        self.tags
        self.templateKey
    
    def get_rule(self, key):
        params = dict(projets=self.key)
        resp = requests.get(url=get_url() + '/api/projects/search', auth=get_credentials(), params=params)
        data = json.loads(resp.text)
        return(data['components']['name'])

def count(include_applications):
    qualifiers = "TRK,APP" if include_applications else "TRK"
    params = dict(ps=3, qualifiers=qualifiers)
    resp = requests.get(url=get_url() + '/api/projects/search', auth=get_credentials(), params=params)
    data = json.loads(resp.text)
    return(data['paging']['total'])

def get_rules(page_nbr=1, page_size=500):
    params = dict(ps=page_size, p=page_nbr, qualifiers=qualifiers)
    resp = requests.get(url=get_url() + '/api/rules/search', auth=get_credentials(), params=params)
    data = json.loads(resp.text)
    return data['rules']

def get_all_rules():
    page_nbr = 1
    page_size = 500
    rules_list = []
    done = False
    while not done:
        params = dict(ps=page_size, p=page_nbr, qualifiers=qualifiers)
        resp = requests.get(url=get_url() + '/api/rules/search', auth=get_credentials(), params=params)
        data = json.loads(resp.text)
        for rule in data['rules']:
            rules_list.append(rules['key'])

def get_rules_list():
    rules = get_rules()
    rules_list = []
    for rule in rules:
        rules_list.append(rules['key'])
    return rules_list

def get_project_name(key):
    params = dict(projects=key)
    resp = requests.get(url=get_url() + '/api/projects/search', auth=get_credentials(), params=params)
    data = json.loads(resp.text)
    json_dump_debug(data)
    return data['components'][0]['name']