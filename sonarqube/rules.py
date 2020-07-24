#!python3

import sys
import json
import requests
from sonarqube.env import get_url, get_credentials


class Rule:

    def __init__(self):
        self.key = None
        self.headline = None
        self.repo = None
        self.severity = None
        self.status = None
        self.actives = None
        self.params = None
        self.rem_fn = None
        self.created_at = None
        self.html_desc = None
        self.debt_rem_fn = None
        self.default_debt_rem_fn = None
        self.default_rem_fn = None
        self.effort_to_fix_desc = None
        self.gap_desc = None
        self.html_note = None
        self.internal_key = None
        self.is_template = None
        self.sys_tags = None
        self.tags = None
        self.template_key = None

    def get_rule(self):
        params = dict(projets=self.key)
        resp = requests.get(url=get_url() + '/api/projects/search', auth=get_credentials(), params=params)
        data = json.loads(resp.text)
        return data['components']['name']

def count(include_applications):
    qualifiers = "TRK,APP" if include_applications else "TRK"
    params = dict(ps=3, qualifiers=qualifiers)
    resp = requests.get(url=get_url() + '/api/projects/search', auth=get_credentials(), params=params)
    data = json.loads(resp.text)
    return data['paging']['total']

def get_rules(page_nbr=1, page_size=500):
    params = dict(ps=page_size, p=page_nbr)
    resp = requests.get(url=get_url() + '/api/rules/search', auth=get_credentials(), params=params)
    data = json.loads(resp.text)
    return data['rules']

def get_all_rules():
    page_nbr = 1
    page_size = 500
    rules_list = []
    done = False
    while not done:
        params = dict(ps=page_size, p=page_nbr)
        resp = requests.get(url=get_url() + '/api/rules/search', auth=get_credentials(), params=params)
        data = json.loads(resp.text)
        for rule in data['rules']:
            rules_list.append(rule['key'])

def get_rules_list():
    rules = get_rules()
    rules_list = []
    for rule in rules:
        rules_list.append(rule['key'])
    return rules_list

