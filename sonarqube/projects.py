#!python3

import json
import requests
import env

class Project:

    def __init__(self):
        self.name = ''
        self.key = ''

def count(include_applications):
    qualifiers = "TRK,APP" if include_applications else "TRK"
    params = dict(ps=3, qualifiers=qualifiers)
    resp = requests.get(url=env.get_url() + '/api/projects/search', auth=env.get_credentials(), params=params)
    data = json.loads(resp.text)
    return(data['paging']['total'])

def get_projects(include_applications, page_size=500, page_nbr=1):
    qualifiers = "TRK,APP" if include_applications else "TRK"
    params = dict(ps=page_size, p=page_nbr, qualifiers=qualifiers)
    resp = requests.get(url=env.get_url() + '/api/projects/search', auth=env.get_credentials(), params=params)
    data = json.loads(resp.text)
    return data['components']
    