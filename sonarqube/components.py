#!python3

import json
import requests
import env

class Component:

    def __init__(self):
        self.name = ''
        self.key = ''

def get_components(component_types):
    params = dict(ps=500, qualifiers=component_types)
    resp = requests.get(url=env.get_url() + '/api/projects/search', auth=env.get_credentials(), params=params)
    data = json.loads(resp.text)
    return data['components']
