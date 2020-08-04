#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "quality profile" concept

'''
import sys
import datetime
import re
import json
import pytz
import sonarqube.sqobject as sq
import sonarqube.env as env
import sonarqube.rules as rules
import sonarqube.utilities as util

class QualityGate(sq.SqObject):

    def __init__(self, key, endpoint, data=None):
        super().__init__(key=key, env=endpoint)
        if data is not None:
            self.name = data['name']
            self.is_default = data['setAsDefault']
            self.is_built_in = data['isBuiltIn']

    def last_used_date(self):
        last_use = None
        return last_use

    def last_updated_date(self):
        last_use = None
        return last_use

    def number_associated_projects(self):
        return 0

    def audit(self):
        issues = 0
        if self.is_built_in:
            return 0
        return issues

def count(endpoint=None, params=None):
    if params is None:
        params = {}
    params['gateId'] = self.key
    params['ps'] = 1
    resp = env.get('qualitygates/search', ctxt=endpoint, params=params)
    data = json.loads(resp.text)
    return data['paging']['total']

def search(endpoint=None, page=0, params=None):
    params['ps'] = 500
    if page != 0:
        params['p'] = page
        resp = env.get('qualitygates/search', ctxt=endpoint, params=params)
        data = json.loads(resp.text)
        return data['results']

    nb_proj = count(endpoint=endpoint, params=params)
    nb_pages = (nb_proj+499)//500
    prj_list = {}
    for page in range(nb_pages):
        params['p'] = page+1
        for p in search(endpoint=endpoint, page=page+1, params=params):
            prj_list[p['key']] = p
    return prj_list

def list_qg(endpoint=None):
    resp = env.get('qualitygates/search', ctxt=endpoint)
    data = json.loads(resp.text)
    qg_list = {}
    for qg in data['qualitygates']:
        qg_list[qg['id']] = QualityGate(key=qg['id'], endpoint=endpoint, data=qg)
    return qg_list

def audit(endpoint=None):
    issues = 0
    langs = {}
    for qp in search(endpoint):
        issues += qp.audit()
        langs[qp.language] = langs.get(qp.language, 0) + 1
    for lang in langs:
        if langs[lang] > 5:
            util.logger.warning("Language %s has %d quality profiles. This is more than the recommended 5 max",
                                lang, langs[lang])
    return issues
