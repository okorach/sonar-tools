#!python3

import sys
import json
import requests
import sonarqube.sqobject as sq
import sonarqube.env as env

class Rule(sq.SqObject):
    def __init__(self, key, sqenv):
        super(Rule, self).__init__(key, sqenv)
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

def count():
    resp = env.get('rules/search', params={'ps':3, 'p':1})
    data = json.loads(resp.text)
    return data['paging']['total']

def get_rules(page_nbr=1, page_size=500):
    resp = env.get('rules/search', params={'ps':page_size, 'p':page_nbr})
    data = json.loads(resp.text)
    return data['rules']

def get_all_rules():
    page_nbr = 1
    page_size = 500
    rules_list = []
    done = False
    while not done:
        resp = env.get('rules/search', params={'ps':page_size, 'p':page_nbr})
        data = json.loads(resp.text)
        for rule in data['rules']:
            rules_list.append(rule['key'])

def get_rules_list():
    rules = get_rules()
    rules_list = []
    for rule in rules:
        rules_list.append(rule['key'])
    return rules_list
