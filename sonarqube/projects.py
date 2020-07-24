#!python3

import sys
import json
import requests
import sonarqube.env as env
import sonarqube.components as comp

PROJECTS = {}

PROJECT_SEARCH_API = '/api/projects/search'

class Project(comp.Component):

    def get_name(self):
        if self.name is None:
            resp = self.sqenv.get( PROJECT_SEARCH_API, parms={'projects':self.key})
            data = json.loads(resp.text)
            self.name = data['components']['name']
        return self.name

    def get_branches(self):
        resp = self.sqenv.get('/api/project_branches/list', parms={'project':self.key})
        data = json.loads(resp.text)
        return data['branches']

    def delete(self):
        resp = self.sqenv.post('/api/projects/delete', parms={'project':self.key})
        return (resp.status_code // 100) == 2

def count(include_applications, myenv = None):
    qualifiers = "TRK,APP" if include_applications else "TRK"
    params = dict(ps=3, qualifiers=qualifiers)
    if myenv is None:
        resp = env.get(PROJECT_SEARCH_API, params)
    else:
        resp = myenv.get(PROJECT_SEARCH_API, params)
    data = json.loads(resp.text)
    return data['paging']['total']

def get_projects(include_applications,  sqenv = None, page_size=500, page_nbr=1):
    qualifiers = "TRK,APP" if include_applications else "TRK"
    params = dict(ps=page_size, p=page_nbr, qualifiers=qualifiers)
    if sqenv is None:
        resp = env.get(PROJECT_SEARCH_API,  params)
    else:
        resp = sqenv.get(PROJECT_SEARCH_API, params)
    data = json.loads(resp.text)
    return data['components']

def get_projects_list(sqenv):
    projects = get_projects(include_applications = False, sqenv = sqenv)
    prjlist = []
    for prj in projects:
        prjlist.append(prj['key'])
    return prjlist

def get_project_name(key, sqenv = None):

    global PROJECTS
    if key in PROJECTS:
        return PROJECTS[key]

    params = dict(projects=key)
    if sqenv is None:
        resp = env.get(PROJECT_SEARCH_API, params)
    else:
        resp = sqenv.get(PROJECT_SEARCH_API, params)
    data = json.loads(resp.text)
    #util.json_dump_debug(data)
    PROJECTS[key] = data['components'][0]['name']
    return PROJECTS[key]
