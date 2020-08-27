#!/usr/local/bin/python3
'''

    Abstraction of the SonarQube "project" concept

'''
import time
import datetime
import re
import json
import pytz
import sonarqube.env as env
import sonarqube.components as comp
import sonarqube.utilities as util
import sonarqube.audit_problem as pb

PROJECTS = {}

PROJECT_SEARCH_API = 'projects/search'
MAX_PAGE_SIZE = 500
PRJ_QUALIFIER = 'TRK'
APP_QUALIFIER = 'APP'


class Project(comp.Component):

    def __init__(self, key, endpoint, data=None):
        super().__init__(key=key, sqenv=endpoint)
        self.id = None
        self.name = None
        self.visibility = None
        self.main_branch_last_analysis_date = 'undefined'
        self.permissions = None
        self.all_branches_last_analysis_date = 'undefined'
        self.user_permissions = None
        self.group_permissions = None
        self.branches = None
        self.ncloc = None
        self.__load__(data)
        PROJECTS[key] = self

    def __load__(self, data=None):
        ''' Loads a project object with contents of an api/projects/search call '''
        if data is None:
            resp = env.get(PROJECT_SEARCH_API, ctxt=self.env, params={'projects': self.key})
            data = json.loads(resp.text)
            data = data['components'][0]
        self.id = data.get('id', None)
        self.name = data['name']
        self.visibility = data['visibility']
        if 'lastAnalysisDate' in data:
            self.main_branch_last_analysis_date = datetime.datetime.strptime(
                data['lastAnalysisDate'], '%Y-%m-%dT%H:%M:%S%z')
        else:
            self.main_branch_last_analysis_date = None
        self.revision = data.get('revision', None)

#    def __del__(self):
#        # del PROJECTS[self.key]

    def get_name(self):
        if self.name is None:
            self.__load__()
        return self.name

    def get_visibility(self):
        if self.visibility is None:
            self.__load__()
        return self.visibility

    def get_last_analysis_date(self, include_branches=False):
        if self.main_branch_last_analysis_date == 'undefined':
            self.__load__()
        if not include_branches:
            return self.main_branch_last_analysis_date
        if self.all_branches_last_analysis_date != 'undefined':
            return self.all_branches_last_analysis_date

        self.all_branches_last_analysis_date = self.main_branch_last_analysis_date
        for b in self.get_branches():
            if 'analysisDate' not in b:
                continue
            b_ana_date = datetime.datetime.strptime(b['analysisDate'], '%Y-%m-%dT%H:%M:%S%z')
            if self.all_branches_last_analysis_date is None or b_ana_date > self.all_branches_last_analysis_date:
                self.all_branches_last_analysis_date = b_ana_date
        return self.all_branches_last_analysis_date

    def get_branches(self):
        if self.branches is not None:
            return self.branches

        resp = env.get('project_branches/list', params={'project': self.key}, ctxt=self.env)
        data = json.loads(resp.text)
        self.branches = data['branches']
        return self.branches

    def get_permissions(self, perm_type):
        MAX_PERMISSION_PAGE_SIZE = 100
        if perm_type == 'user' and self.user_permissions is not None:
            return self.user_permissions
        if perm_type == 'group' and self.group_permissions is not None:
            return self.group_permissions

        resp = env.get('permissions/{0}'.format(perm_type), ctxt=self.env,
                       params={'projectKey': self.key, 'ps': 1})
        data = json.loads(resp.text)
        nb_perms = int(data['paging']['total'])
        nb_pages = (nb_perms + MAX_PERMISSION_PAGE_SIZE - 1) // MAX_PERMISSION_PAGE_SIZE
        perms = []
        for page in range(nb_pages):
            resp = env.get('permissions/{0}'.format(perm_type), ctxt=self.env,
                           params={'projectKey': self.key, 'ps': MAX_PERMISSION_PAGE_SIZE, 'p': page + 1})
            data = json.loads(resp.text)
            for p in data[perm_type]:
                perms.append(p)
        if perm_type == 'group':
            self.group_permissions = perms
        else:
            self.user_permissions = perms
        return perms

    def delete(self, api='projects/delete', params=None):
        confirmed = False
        loc = int(self.get_measure('ncloc'))
        if util.get_run_mode() == util.DRY_RUN:
            print("DRY-RUN: Project key %s (%d LoC) deleted")
            return True
        elif util.get_run_mode() == util.CONFIRM:
            text = input('Please confirm deletion y/n [n]')
            confirmed = (text == 'y')
        elif util.get_run_mode() == util.BATCH:
            confirmed = True
        if not confirmed:
            return False
        util.logger.debug("Deleting project key %s", self.key)
        if not super().delete('projects/delete', params={'project': self.key}):
            util.logger.error("Project key %s deletion failed", self.key)
            return False
        util.logger.info("Successfully deleted project key %s - %d LoCs", self.key, loc)
        print("Successfully deleted project key %s - %d LoCs" % (self.key, loc))
        return True

    def age_of_last_analysis(self):
        today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
        last_analysis = self.get_last_analysis_date(include_branches=True)
        if last_analysis is None:
            return None
        return abs(today - last_analysis).days

    def __audit_user_permissions__(self):
        perms = self.get_permissions('users')
        nb_perms = 0
        problems = []
        admins = []
        for p in perms:
            if p['permissions']:
                nb_perms += 1
            if 'admin' in p['permissions']:
                if 'login' not in p:
                    p['login'] = p['name']
                admins.append(p['login'])
        if nb_perms > 5:
            problems.append(pb.Problem(pb.Type.GOVERNANCE, pb.Severity.MEDIUM,
                "Project '{}' has too many permissions granted through users, \
groups should be favored".format(self.key)))
        if len(admins) > 3:
            problems.append(pb.Problem(pb.Type.GOVERNANCE, pb.Severity.HIGH,
                "Project '{}' has too many users with Administration permission \
({} users)".format(self.key, len(admins))))
        return problems

    def __audit_group_permissions__(self):
        groups = self.get_permissions('groups')
        nb_perms = 0
        problems = []
        nb_admins = 0
        nb_scan = 0
        nb_issue_admin = 0
        nb_hotspot_admin = 0
        for gr in groups:
            p = gr['permissions']
            if not p:
                continue
            nb_perms += 1
            if 'admin' in p:
                nb_admins += 1
            if 'scan' in p:
                nb_scan += 1
            if 'issueadmin' in p:
                nb_issue_admin += 1
            if 'securityhotspotadmin' in p:
                nb_hotspot_admin += 1
            # -- Checks for Anyone, sonar-user
            if (gr['name'] != 'Anyone' and gr['id'] != 2):
                continue
            if "issueadmin" in p or "scan" in p or "securityhotspotadmin" in p or "admin" in p:
                sev = pb.Severity.HIGH if gr['name'] == 'Anyone' else pb.Severity.MEDIUM
                problems.append(pb.Problem(pb.Type.SECURITY, sev,
                    "Group '{}' has elevated (non read-only) permissions on project '{}'".format(gr['name'], self.key)))
            else:
                util.logger.info("Group '%s' has browse permissions on project '%s'. \
Is this normal ?", gr['name'], self.key)

        if nb_perms > 5:
            problems.append(pb.Problem(pb.Type.OPERATIONS, pb.Severity.MEDIUM,
                "Project '{}' has too many group permissions defined ({} groups)".format(self.key, nb_perms)))
        if nb_scan > 1:
            problems.append(pb.Problem(pb.Type.GOVERNANCE, pb.Severity.MEDIUM,
                "Project '{}' has too many groups with 'Execute Analysis' permission ({} groups)".format(self.key, nb_scan)))
        if nb_issue_admin > 2:
            problems.append(pb.Problem(pb.Type.GOVERNANCE, pb.Severity.MEDIUM,
                "Project '{}' has too many groups with 'Issue Admin' permission ({} groups)".format(self.key, nb_issue_admin)))
        if nb_hotspot_admin > 2:
            problems.append(pb.Problem(pb.Type.GOVERNANCE, pb.Severity.MEDIUM,
                "Project '{}' has too many groups with 'Hotspot Admin' permission ({} groups)".format(self.key, nb_hotspot_admin)))
        if nb_admins > 2:
            problems.append(pb.Problem(pb.Type.GOVERNANCE, pb.Severity.HIGH,
                "Project '{}' has too many groups with 'Project Admin' permissions ({} groups)".format(self.key, nb_admins)))
        return problems

    def __audit_permissions__(self):
        util.logger.info("   Auditing permissions for project '%s'", self.key)
        problems = self.__audit_user_permissions__() + self.__audit_group_permissions__()
        if not problems:
            util.logger.info("   No issue found in project '%s' permissions", self.key)
        return problems

    def __audit_last_analysis__(self):
        util.logger.info("   Auditing project '%s' last analysis date", self.key)
        age = self.age_of_last_analysis()
        problems = []
        if age is None:
            problems.append(pb.Problem(pb.Type.OPERATIONS, pb.Severity.LOW,
                "Project '{}' has been created but never been analyzed".format(self.key)))
        elif age > 180:
            # TODO make the 180 days configurable
            sev = pb.Severity.HIGH if age > 365 else pb.Severity.MEDIUM
            problems.append(pb.Problem(pb.Type.OPERATIONS, sev,
                "Project '{}' last analysis is {} days old, it may be deleted".format(self.key, age)))
        else:
            util.logger.info("   Project %s last analysis is %d days old", self.key, age)
        return problems

    def __audit_visibility__(self):
        util.logger.info("   Auditing Project '%s' visibility", self.key)
        problems = []
        resp = env.get('navigation/component', ctxt=self.env, params={'component': self.key})
        data = json.loads(resp.text)
        visi = data['visibility']
        if visi == 'private':
            util.logger.info("   Project '%s' visibility is private", self.key)
        else:
            problems.append(pb.Problem(pb.Type.SECURITY, pb.Severity.LOW,
                "Project '{}' visibility is {}, which can be a security risk".format(self.key, visi)))
        return problems

    def __audit_languages__(self):
        total_locs = 0
        languages = {}
        problems = []
        resp = self.get_measure('ncloc_language_distribution')
        if resp is None:
            return problems
        for lang in self.get_measure('ncloc_language_distribution').split(';'):
            (lang, ncloc) = lang.split('=')
            languages[lang] = int(ncloc)
            total_locs += int(ncloc)
        if total_locs > 100000 and 'xml' in languages and (languages['xml'] / total_locs) > 0.5:
            problems.append(pb.Problem(pb.Type.OPERATIONS, pb.Severity.LOW,
                "Project '{}' has {} XML LoCs, this is suspiciously high, verify scanning settings".format(
                    self.key, languages['xml'])))
        return problems

    def audit(self):
        util.logger.info("Auditing project %s", self.key)
        return (
            self.__audit_last_analysis__()
            + self.__audit_visibility__()
            + self.__audit_languages__()
            + self.__audit_permissions__()
        )

    def delete_if_obsolete(self, days=180):
        today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
        mindate = today - datetime.timedelta(days=days)
        last_analysis = self.get_last_analysis_date(include_branches=True)
        loc = int(self.get_measure('ncloc'))
        print("Project key %s - %d LoCs - Not analysed for %d days" %
              (self.key, loc, (today - last_analysis).days))
        util.logger.info("Project key %s - %d LoCs - Not analysed for %d days",
                         self.key, loc, (today - last_analysis).days)
        if last_analysis < mindate:
            return self.delete()
        return False

    def __wait_for_task_completion__(self, task_id, params, timeout=180):
        finished = False
        wait_time = 0
        sleep_time = 0.5
        while not finished:
            time.sleep(sleep_time)
            wait_time += sleep_time
            sleep_time *= 2
            resp = env.get('ce/activity', params=params, ctxt=self.env)
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
        return status

    def export(self, timeout=180):
        util.logger.info('Exporting project key = %s (synchronously)', self.key)
        resp = env.post('project_dump/export', params={'key': self.key}, ctxt=self.env)
        if resp.status_code != 200:
            return {'status': 'HTTP_ERROR {0}'.format(resp.status_code)}
        data = json.loads(resp.text)
        params = {'type': 'PROJECT_EXPORT', 'status': 'PENDING,IN_PROGRESS,SUCCESS,FAILED,CANCELED'}
        if self.env.get_version() >= (8, 0, 0):
            params['component'] = self.key
        else:
            params['q'] = self.key
        status = self.__wait_for_task_completion__(data['taskId'], params=params, timeout=timeout)
        if status != 'SUCCESS':
            util.logger.error("Project key %s export %s", self.key, status)
            return {'status': status}
        resp = env.get('project_dump/status', params={'key': self.key}, ctxt=self.env)
        data = json.loads(resp.text)
        dump_file = data['exportedDump']
        util.logger.debug("Project key %s export %s, dump file %s", self.key, status, dump_file)
        return {'status': status, 'file': dump_file}

    def export_async(self):
        util.logger.info('Exporting project key = %s (asynchronously)', self.key)
        resp = env.post('project_dump/export', params={'key': self.key}, ctxt=self.env)
        if resp.status_code != 200:
            return None
        data = json.loads(resp.text)
        return data['taskId']

    def importproject(self):
        util.logger.info('Importing project key = %s (asynchronously)', self.key)
        resp = env.post('project_dump/import', params={'key': self.key}, ctxt=self.env)
        return resp.status_code


def count(endpoint=None, params=None):
    if params is None:
        params = {}
    params['ps'] = 1
    params['p'] = 1
    resp = env.get(PROJECT_SEARCH_API, ctxt=endpoint, params=params)
    data = json.loads(resp.text)
    return data['paging']['total']


def search(endpoint=None, page=0, params=None):
    if params is None:
        params = {}
        params['qualifiers'] = 'TRK'
    if page != 0:
        params['p'] = page
        if 'ps' in params and params['ps'] == 0:
            params['ps'] = MAX_PAGE_SIZE
        resp = env.get(PROJECT_SEARCH_API, ctxt=endpoint, params=params)
        data = json.loads(resp.text)
        plist = {}
        for prj in data['components']:
            plist[prj['key']] = Project(prj['key'], endpoint=endpoint, data=prj)
        return plist

    nb_projects = count(endpoint=endpoint, params=params)
    nb_pages = ((nb_projects - 1) // MAX_PAGE_SIZE) + 1
    params['ps'] = MAX_PAGE_SIZE
    project_list = {}
    for p in range(nb_pages):
        params['p'] = p + 1
        project_list.update(search(endpoint=endpoint, page=p + 1, params=params))
    return project_list


def get(key, sqenv=None):
    global PROJECTS
    if key not in PROJECTS:
        _ = Project(key=key, endpoint=sqenv)
    return PROJECTS[key]


def create_project(key, name=None, visibility='private', sqenv=None):
    if name is None:
        name = key
    resp = env.post('projects/create', ctxt=sqenv,
                    params={'project': key, 'name': name, 'visibility': visibility})
    return resp.status_code


def delete_old_projects(days=180, endpoint=None):
    '''Deletes all projects whose last analysis date on any branch is older than x days'''
    deleted_projects = 0
    deleted_locs = 0
    for key in search():
        p_obj = Project(key, endpoint=endpoint, data=None)
        loc = int(p_obj.get_measures(['ncloc']))
        if p_obj.delete_if_obsolete(days=days):
            deleted_projects += 1
            deleted_locs += loc
    if util.get_run_mode == util.DRY_RUN:
        print("%d PROJECTS for a total of %d LoCs to delete" % (deleted_projects, deleted_locs))
    else:
        print("%d PROJECTS deleted for a total of %d LoCs" % (deleted_projects, deleted_locs))


def audit(endpoint=None):
    plist = search(endpoint)
    problems = []
    for key, p in plist.items():
        problems += p.audit()
        util.logger.info("   Auditing for potential duplicate projects")
        for key2 in plist:
            if key2 != key and re.match(key, key2):
                problems.append(pb.Problem(pb.Type.OPERATIONS, pb.Severity.MEDIUM,
                    "Project {} is likely to be a branch of {}, and if so should be deleted".format(key2, key)))
    return problems
