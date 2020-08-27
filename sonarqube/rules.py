#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "rule" concept

'''
import json
import sonarqube.sqobject as sq
import sonarqube.env as env


class Rule(sq.SqObject):
    def __init__(self, key, endpoint, data):
        super().__init__(key, endpoint)
        self.key = key
        self.severity = data['severity']
        self.tags = data['tags']
        self.sys_tags = data['sysTags']
        self.repo = data['repo']
        self.type = data['type']
        self.status = data['status']
        self.scope = data['scope']
        self.html_desc = data['htmlDesc']
        self.md_desc = data['mdDesc']
        self.name = data['name']
        self.language = data['lang']
        self.created_at = data['createdAt']
        self.is_template = data['isTemplate']
        self.template_key = data.get('templateKey', None)


def get_facet(facet, endpoint=None):
    resp = env.get('rules/search', ctxt=endpoint, params={'ps': 1, 'facets': facet})
    data = json.loads(resp.text)
    facet_dict = {}
    for f in data['facets'][0]['values']:
        facet_dict[f['val']] = f['count']
    return facet_dict


def count(endpoint=None, params=None):
    if params is None:
        params = {}
    params['ps'] = 1
    params['p'] = 1
    resp = env.get('rules/search', ctxt=endpoint, params=params)
    data = json.loads(resp.text)
    return data['total']


def search(endpoint=None, params=None):
    resp = env.get('rules/search', ctxt=endpoint, params=params)
    data = json.loads(resp.text)
    rule_list = []
    for rule in data['rules']:
        rule_list.append(Rule(rule['key'], endpoint=endpoint, data=rule))
    return rule_list


def search_all(endpoint=None, params=None):
    params['is_template'] = 'false'
    params['include_external'] = 'true'
    nb_rules = count(endpoint=endpoint, params=params)
    nb_pages = ((nb_rules - 1) // 500) + 1
    params['ps'] = 500
    rule_list = {}
    for page in range(nb_pages):
        params['p'] = page + 1
        for r in search(endpoint=endpoint, params=params):
            rule_list[r['key']] = r
    return rule_list
