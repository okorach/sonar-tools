#!python3

import sys
import time
import json
import requests
import sonarqube.env as env
import sonarqube.components as comp
import sonarqube.utilities as util

PROJECTS = {}
class Project(comp.Component):

    def get_name(self):
        if self.name is None:
            params = dict(projects=self.key)
            resp = requests.get(url=env.get_url() + '/api/projects/search', auth=env.get_credentials(), params=params)
            data = json.loads(resp.text)
            self.name = data['components']['name']
        return self.name

    def get_branches(self):
        resp = self.sqenv.get('/api/project_branches/list', parms=dict(project=self.key))
        data = json.loads(resp.text)
        return data['branches']

    def export(self, poll_interval = 1):
        util.logger.info('Exporting project key = %s', self.key)
        resp = self.sqenv.post('/api/project_dump/export', parms={'key':self.key})
        util.logger.debug('Export response = %s', str(resp))
        data = json.loads(resp.text)
        task_id = data['taskId']
        finished = False
        parms = {'type':'PROJECT_EXPORT', 'component':self.key, 'status':'PENDING,IN_PROGRESS,SUCCESS,FAILED,CANCELED'}
        while not finished:
            time.sleep(poll_interval)
            resp = self.sqenv.get('/api/ce/activity', parms=parms)
            data = json.loads(resp.text)
            for t in data['tasks']:
                if t['id'] != task_id:
                    continue
                status = t['status']
                if status == 'SUCCESS' or status == 'FAILED' or status == 'CANCELLED':
                    finished = True
                    break
        if status != 'SUCCESS':
            util.logger.error("Project key %s export %s", self.key, status)
            return False
        resp = self.sqenv.get('/api/project_dump/status', parms={'key':self.key})
        data = json.loads(resp.text)
        dump_file = data['exportedDump']
        util.logger.info("Project key %s export %s, dump file %s", self.key, status, dump_file)
        return dump_file

    def export_async(self):
        util.logger.info('Exporting project key = %s', self.key)
        resp = self.sqenv.post('/api/project_dump/export', parms={'key':self.key})
        util.logger.debug('Export response = %s', str(resp))
        data = json.loads(resp.text)
        return data['taskId']


def count(include_applications, myenv = None):
    qualifiers = "TRK,APP" if include_applications else "TRK"
    params = dict(ps=3, qualifiers=qualifiers)
    if myenv is None:
        resp = env.get('/api/projects/search', params)
    else:
        resp = myenv.get('/api/projects/search', params)
    data = json.loads(resp.text)
    return data['paging']['total']

def get_projects(include_applications,  myenv = None, page_size=500, page_nbr=1):
    qualifiers = "TRK,APP" if include_applications else "TRK"
    params = dict(ps=page_size, p=page_nbr, qualifiers=qualifiers)
    if myenv is None:
        resp = env.get('/api/projects/search',  params)
    else:
        resp = myenv.get('/api/projects/search', params)
    data = json.loads(resp.text)
    return data['components']

def get_projects_list(sqenv):
    projects = get_projects(include_applications=False, myenv=sqenv)
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
        resp = env.get('/api/projects/search', params)
    else:
        resp = sqenv.get('/api/projects/search', params)
    data = json.loads(resp.text)
    #util.json_dump_debug(data)
    PROJECTS[key] = data['components'][0]['name']
    return PROJECTS[key]
