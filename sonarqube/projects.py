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

    def export(self, timeout = 180):
        util.logger.info('Exporting project key = %s (synchronously)', self.key)
        resp = self.sqenv.post('/api/project_dump/export', parms={'key':self.key})
        if resp.status_code != 200:
            util.logger.error("/api/project_dump/export returned HTTP status code %d", int(resp.code))
            return {'status' : 'HTTP_ERROR {0}'.format(resp.status_code)}
        data = json.loads(resp.text)
        task_id = data['taskId']
        finished = False
        parms = {'type':'PROJECT_EXPORT', 'status':'PENDING,IN_PROGRESS,SUCCESS,FAILED,CANCELED'}
        if self.sqenv.version_higher_or_equal_than("8.0.0"):
            parms['component'] = self.key
        else:
            parms['q'] = self.key
        wait_time = 0
        sleep_time = 0.5
        while not finished:
            time.sleep(sleep_time)
            wait_time += sleep_time
            sleep_time *= 2
            resp = self.sqenv.get('/api/ce/activity', parms=parms)
            data = json.loads(resp.text)
            for t in data['tasks']:
                if t['id'] != task_id:
                    continue
                status = t['status']
                if status == 'SUCCESS' or status == 'FAILED' or status == 'CANCELED':
                    finished = True
                    break
            util.logger.debug("Task id %s is %s", task_id, status)
            if wait_time >= timeout:
                status = 'TIMEOUT'
                finished = True
        if status != 'SUCCESS':
            util.logger.error("Project key %s export %s", self.key, status)
            return {'status': status}
        resp = self.sqenv.get('/api/project_dump/status', parms={'key':self.key})
        data = json.loads(resp.text)
        dump_file = data['exportedDump']
        util.logger.debug("Project key %s export %s, dump file %s", self.key, status, dump_file)
        return {'status': status, 'file': dump_file}

    def export_async(self):
        util.logger.info('Exporting project key = %s (asynchronously)', self.key)
        resp = self.sqenv.post('/api/project_dump/export', parms={'key':self.key})
        if resp.status_code != 200:
            util.logger.error("/api/project_dump/export returned HTTP status code %d", int(resp.code))
            # TODO handle HTTP error exceptions
            return None
        data = json.loads(resp.text)
        return data['taskId']

    def importproject(self):
        util.logger.info('Importing project key = %s (asynchronously)', self.key)
        resp = self.sqenv.post('/api/project_dump/import', parms={'key':self.key})
        if resp.status_code != 200:
            util.logger.error("/api/project_dump/import returned HTTP status code %d", int(resp.code))
            # TODO handle HTTP error exceptions
            return None
        return resp.status_code

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

def create_project(key, name = None, visibility = 'private', sqenv = None):
    if name is None:
        name = key
    if sqenv is None:
        resp = env.post('/api/projects/create', parms={'project':key, 'name':name, 'visibility':'private'})
    else:
        resp = sqenv.post('/api/projects/create', parms={'project':key, 'name':name, 'visibility':'private'})
    return resp.status_code