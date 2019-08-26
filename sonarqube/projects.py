#!python3

import sys
import json
import requests
import sonarqube.env as env
# from sonarqube.env import get_url, get_credentials, json_dump_debug

global PROJECTS

PROJECTS = {}
class Project:

    def __init__(self):
        self.name = ''
        self.key = ''

    def get_name(self):
        params = dict(projets=self.key)
        resp = requests.get(url=get_url() + '/api/projects/search', auth=get_credentials(), params=params)
        data = json.loads(resp.text)
        return data['components']['name']

def count(include_applications, myenv = None):
    qualifiers = "TRK,APP" if include_applications else "TRK"
    params = dict(ps=3, qualifiers=qualifiers)
    if myenv is None:
        resp = env.get('/api/projects/search', params)
    else:
        resp = myenv.get('/api/projects/search', params)
    data = json.loads(resp.text)
    return(data['paging']['total'])

def get_projects(include_applications,  myenv = None, page_size=500, page_nbr=1):
    qualifiers = "TRK,APP" if include_applications else "TRK"
    params = dict(ps=page_size, p=page_nbr, qualifiers=qualifiers)
    if myenv is None:
        resp = env.get('/api/projects/search',  params)
    else:
        resp = myenv.get('/api/projects/search', params)
#        resp = requests.get(url=get_url() + '/api/projects/search', auth=get_credentials(), params=params)
    data = json.loads(resp.text)
    return data['components']

def get_projects_list(sqenv):
    projects = get_projects(include_applications=False, myenv=sqenv)
    prjlist = []
    for prj in projects:
        prjlist.append(prj['key'])
    return prjlist

def get_project_name(key, myenv = None):

    global PROJECTS
    if key in PROJECTS:
        return PROJECTS[key]

    params = dict(projects=key)
    if myenv is None:
        resp = env.get('/api/projects/search', params)
    else:
        resp = myenv.get('/api/projects/search', params)
    data = json.loads(resp.text)
    #env.json_dump_debug(data)
    PROJECTS[key] = data['components'][0]['name']
    return PROJECTS[key]
