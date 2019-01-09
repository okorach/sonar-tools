#!python3

import json
import requests
from sonarqube.env import get_url, get_credentials, json_dump_debug
import sys

class Project:

    def __init__(self):
        self.name = ''
        self.key = ''
    
    def get_name(self):
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

def get_projects(include_applications, page_size=500, page_nbr=1):
    qualifiers = "TRK,APP" if include_applications else "TRK"
    params = dict(ps=page_size, p=page_nbr, qualifiers=qualifiers)
    resp = requests.get(url=get_url() + '/api/projects/search', auth=get_credentials(), params=params)
    data = json.loads(resp.text)
    return data['components']

def get_projects_list():
    projects = get_projects(False)
    prjlist = []
    for prj in projects:
        prjlist.append(prj['key'])
    return prjlist

def get_project_name(key):
    params = dict(projects=key)
    resp = requests.get(url=get_url() + '/api/projects/search', auth=get_credentials(), params=params)
    data = json.loads(resp.text)
    json_dump_debug(data)
    return data['components'][0]['name']