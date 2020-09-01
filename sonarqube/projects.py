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

import sonarqube.audit_severities as sev
import sonarqube.audit_types as typ
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb
import sonarqube.permissions as perms
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

    def __str__(self):
        return "Project key '{}'".format(self.key)

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
        permissions = []
        for page in range(nb_pages):
            resp = env.get('permissions/{0}'.format(perm_type), ctxt=self.env,
                           params={'projectKey': self.key, 'ps': MAX_PERMISSION_PAGE_SIZE, 'p': page + 1})
            data = json.loads(resp.text)
            for p in data[perm_type]:
                permissions.append(p)
        if perm_type == 'group':
            self.group_permissions = permissions
        else:
            self.user_permissions = permissions
        return permissions

    def delete(self, api='projects/delete', params=None):
        confirmed = False
        loc = int(self.get_measure('ncloc'))
        if util.get_run_mode() == util.DRY_RUN:
            util.logger.info("DRY-RUN: Project key %s (%d LoC) deleted")
            return True
        elif util.get_run_mode() == util.CONFIRM:
            text = input('Please confirm deletion y/n [n]')
            confirmed = (text == 'y')
        elif util.get_run_mode() == util.BATCH:
            confirmed = True
        if not confirmed:
            return False
        util.logger.debug("Deleting project key %s", self.key)
        if not super().post('projects/delete', params={'project': self.key}):
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

    def __audit_user_permissions__(self, audit_settings):
        problems = []
        counts = __get_permissions_counts__(self.get_permissions('users'))

        max_users = int(audit_settings.get('audit.projects.permissions.maxUsers', '5'))
        if counts['overall'] > max_users:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_USERS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['overall']),
                concerned_object=self))

        max_admins = int(audit_settings.get('audit.projects.permissions.maxAdminUsers', '2'))
        if counts['admin'] > max_admins:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ADM_USERS)
            problems.append(pb.Problem(
                rule.type, rule.severity, rule.msg.format(self.key, counts['admin'], max_admins),
                concerned_object=self))

        return problems

    def __audit_group_permissions__(self, audit_settings):
        problems = []
        groups = self.get_permissions('groups')
        counts = __get_permissions_counts__(groups)
        for gr in groups:
            p = gr['permissions']
            if not p:
                continue
            # -- Checks for Anyone, sonar-user
            if (gr['name'] != 'Anyone' and gr['id'] != 2):
                continue
            if "issueadmin" in p or "scan" in p or "securityhotspotadmin" in p or "admin" in p:
                if gr['name'] == 'Anyone':
                    rule = rules.get_rule(rules.RuleId.PROJ_PERM_ANYONE)
                else:
                    rule = rules.get_rule(rules.RuleId.PROJ_PERM_SONAR_USERS_ELEVATED_PERMS)
                problems.append(pb.Problem(
                    rule.type, rule.severity, rule.msg.format(gr['name'], self.key),
                    concerned_object=self))
            else:
                util.logger.info("Group '%s' has browse permissions on project '%s'. \
Is this normal ?", gr['name'], self.key)

        max_perms = int(audit_settings.get('audit.projects.permissions.maxGroups', '5'))
        if counts['overall'] > max_perms:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_GROUPS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['overall'], max_perms),
                concerned_object=self))
        max_scan = int(audit_settings.get('audit.projects.permissions.maxScanGroups', '1'))
        if counts['scan'] > max_scan:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_SCAN_GROUPS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['scan'], max_scan),
                concerned_object=self))
        max_issue_adm = int(audit_settings.get('audit.projects.permissions.maxIssueAdminGroups', '2'))
        if counts['issueadmin'] > max_issue_adm:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ISSUE_ADM_GROUPS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['issueadmin'], max_issue_adm),
                concerned_object=self))
        max_spots_adm = int(audit_settings.get('audit.projects.permissions.maxHotspotAdminGroups', '2'))
        if counts['securityhotspotadmin'] > max_spots_adm:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_HOTSPOT_ADM_GROUPS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['securityhotspotadmin'], max_spots_adm),
                concerned_object=self))
        max_admins = int(audit_settings.get('audit.projects.permissions.maxAdminGroups', '2'))
        if counts['admin'] > max_admins:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ADM_GROUPS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['admin'], max_admins),
                concerned_object=self))
        return problems

    def __audit_permissions__(self, audit_settings):
        if not audit_settings.get('audit.projects.permissions', ''):
            util.logger.info('Auditing project permissions is disabled by configuration, skipping')
            return []
        util.logger.info("Auditing permissions for project '%s'", self.key)
        problems = (self.__audit_user_permissions__(audit_settings)
                    + self.__audit_group_permissions__(audit_settings))
        if not problems:
            util.logger.info("No issue found in project '%s' permissions", self.key)
        return problems

    def __audit_last_analysis__(self, audit_settings):
        util.logger.info("Auditing project '%s' last analysis date", self.key)
        age = self.age_of_last_analysis()
        if age is None:
            if not audit_settings.get('audit.projects.neverAnalyzed', True):
                util.logger.info("Auditing of never analyzed projects is disabled, skipping")
                return []
            rule = rules.get_rule(rules.RuleId.PROJ_NOT_ANALYZED)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(self.key), concerned_object=self)]
        if age > audit_settings.get('audit.projects.maxLastAnalysisAge', 180):
            if not audit_settings.get('audit.projects.lastAnalysisDate', True):
                util.logger.info("Auditing of projects with old analysis date is disabled, skipping")
                return []
            rule = rules.get_rule(rules.RuleId.PROJ_LAST_ANALYSIS)
            severity = sev.Severity.HIGH if age > 365 else rule.severity
            return [pb.Problem(rule.type, severity, rule.msg.format(self.key, age), concerned_object=self)]

        util.logger.info("Project %s last analysis is %d days old", self.key, age)
        return []

    def __audit_visibility__(self, audit_settings):
        if not audit_settings.get('audit.projects.visibility', True):
            util.logger.info("Project visibility audit is disabled by configuration, skipping...")
            return []
        util.logger.info("Auditing Project '%s' visibility", self.key)
        resp = env.get('navigation/component', ctxt=self.env, params={'component': self.key})
        data = json.loads(resp.text)
        visi = data['visibility']
        if visi != 'private':
            rule = rules.get_rule(rules.RuleId.PROJ_VISIBILITY)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(self.key, visi),
                               concerned_object=self)]

        util.logger.info("Project '%s' visibility is private", self.key)
        return []

    def __audit_languages__(self, audit_settings):
        if not audit_settings.get('audit.xmlLoc.suspicious', False):
            util.logger.info('XML LoCs count audit disabled by configuration, skipping')
            return []
        util.logger.info('Auditing suspicious XML LoC count')

        total_locs = 0
        languages = {}
        resp = self.get_measure('ncloc_language_distribution')
        if resp is None:
            return []
        for lang in self.get_measure('ncloc_language_distribution').split(';'):
            (lang, ncloc) = lang.split('=')
            languages[lang] = int(ncloc)
            total_locs += int(ncloc)
        if total_locs > 100000 and 'xml' in languages and (languages['xml'] / total_locs) > 0.5:
            rule = rules.get_rule(rules.RuleId.PROJ_XML_LOCS)
            return [pb.Problem(rule.type, rule.severity, rule.format(self.key, languages['xml']),
                               concerned_object=self)]
        util.logger.info('XML LoCs count seems reasonable')
        return []

    def audit(self, audit_settings):
        util.logger.info("Auditing project %s", self.key)
        return (
            self.__audit_last_analysis__(audit_settings)
            + self.__audit_visibility__(audit_settings)
            + self.__audit_languages__(audit_settings)
            + self.__audit_permissions__(audit_settings)
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


def __get_permissions_counts__(entities):
    counts = {}
    counts['overall'] = 0
    for permission in perms.PROJECT_PERMISSIONS:
        counts[permission] = 0
    util.logger.debug("PERMS for %s", str(entities))
    for gr in entities:
        p = gr['permissions']
        if not p:
            continue
        counts['overall'] += 1
        for perm in perms.PROJECT_PERMISSIONS:
            if perm in p:
                counts[perm] += 1
    return counts


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


def audit(audit_settings, endpoint=None):
    plist = search(endpoint)
    problems = []
    for key, p in plist.items():
        problems += p.audit(audit_settings)
        if audit_settings.get('audit.projects.duplicates', 'yes') != 'yes':
            continue
        if not audit_settings.get('audit.projects.duplicates', True):
            util.logger.info("Auditing for potential duplicate projects is disabled, skipping")
        util.logger.info("Auditing for potential duplicate projects")
        for key2 in plist:
            if key2 != key and re.match(key2, key):
                problems.append(pb.Problem(
                    typ.Type.OPERATIONS, sev.Severity.MEDIUM,
                    "Project '{}' is likely to be a branch of '{}', and if so should be deleted".format(key, key2),
                    concerned_object=p))
    if audit_settings.get('audit.projects.duplicates', 'yes') != 'yes':
        util.logger.info("Project duplicates auditing was disabled by configuration")
    return problems
