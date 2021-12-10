#
# sonar-tools
# Copyright (C) 2019-2021 Olivier Korach
# mailto:olivier.korach AT gmail DOT com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
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
from sonarqube.branches import Branch
from sonarqube.pull_requests import PullRequest

import sonarqube.audit_severities as sev
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb
import sonarqube.permissions as perms
import sonarqube.custom_measures as custom_measures

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
        self.pull_requests = None
        self._ncloc_with_branches = None
        self.__load__(data)
        PROJECTS[key] = self

    def __str__(self):
        return f"Project key '{self.key}'"

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
            self.main_branch_last_analysis_date = util.string_to_date(data['lastAnalysisDate'])
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

    def last_analysis_date(self, include_branches=False):
        if self.main_branch_last_analysis_date == 'undefined':
            self.__load__()
        if not include_branches:
            return self.main_branch_last_analysis_date
        if self.all_branches_last_analysis_date != 'undefined':
            return self.all_branches_last_analysis_date

        self.all_branches_last_analysis_date = self.main_branch_last_analysis_date
        if self.env.version() >= (9, 2, 0):
            # Starting from 9.2 project last analysis date takes into account branches and PR
            return self.all_branches_last_analysis_date

        for b in self.get_branches() + self.get_pull_requests():
            if b.last_analysis_date() is None:
                continue
            b_ana_date = b.last_analysis_date()
            if self.all_branches_last_analysis_date is None or b_ana_date > self.all_branches_last_analysis_date:
                self.all_branches_last_analysis_date = b_ana_date
        return self.all_branches_last_analysis_date

    def ncloc(self, include_branches=True):
        if self._ncloc is None:
            self._ncloc = int(self.get_measure('ncloc', fallback=0))
        if not include_branches:
            return self._ncloc
        if self._ncloc_with_branches is not None:
            return self._ncloc_with_branches
        self._ncloc_with_branches = self._ncloc
        if not self.env.edition() == 'community':
            for b in self.get_branches() + self.get_pull_requests():
                if b.ncloc() > self._ncloc_with_branches:
                    self._ncloc_with_branches = b.ncloc()
        return self._ncloc_with_branches

    def get_branches(self):
        if self.env.edition() == 'community':
            util.logger.warning("Branches not available in Community Edition")
            return []

        if self.branches is None:
            resp = env.get('project_branches/list', params={'project': self.key}, ctxt=self.env)
            data = json.loads(resp.text)
            self.branches = []
            for b in data['branches']:
                self.branches.append(Branch(name=b['name'], project=self, data=b))
        return self.branches

    def get_pull_requests(self):
        if self.env.edition() == 'community':
            util.logger.warning("Pull requests not available in Community Edition")
            return []

        if self.pull_requests is None:
            resp = env.get('project_pull_requests/list', params={'project': self.key}, ctxt=self.env)
            data = json.loads(resp.text)
            self.pull_requests = []
            for p in data['pullRequests']:
                self.pull_requests.append(PullRequest(key=p['key'], project=self, data=p))
        return self.pull_requests

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
            # Workaround for SQ 7.9+, all groups/users even w/o permissions are returned
            # Stop collecting permissions as soon as 5 groups with no permissions are encountered
            no_perms_count = 0
            for p in data[perm_type]:
                if not p['permissions']:
                    no_perms_count = no_perms_count + 1
                else:
                    no_perms_count = 0
                permissions.append(p)
                if no_perms_count >= 5:
                    break
            if no_perms_count >= 5:
                break
        if perm_type == 'group':
            self.group_permissions = permissions
        else:
            self.user_permissions = permissions
        return permissions

    def delete(self, api='projects/delete', params=None):
        loc = int(self.get_measure('ncloc', fallback='0'))
        util.logger.info("Deleting project key '%s', name '%s' with %d LoCs", self.key, self.name, loc)
        if not super().post('projects/delete', params={'project': self.key}):
            util.logger.error("Project key '%s' deletion failed", self.key)
            return False
        util.logger.info("Successfully deleted project key '%s' - %d LoCs", self.key, loc)
        return True

    def age_of_last_analysis(self):
        today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
        last_analysis = self.last_analysis_date(include_branches=True)
        if last_analysis is None:
            return None
        return abs(today - last_analysis).days

    def __audit_user_permissions__(self, audit_settings):
        problems = []
        counts = __get_permissions_counts__(self.get_permissions('users'))

        max_users = audit_settings['audit.projects.permissions.maxUsers']
        if counts['overall'] > max_users:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_USERS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['overall']),
                concerned_object=self))

        max_admins = audit_settings['audit.projects.permissions.maxAdminUsers']
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

        max_perms = audit_settings['audit.projects.permissions.maxGroups']
        if counts['overall'] > max_perms:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_GROUPS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['overall'], max_perms),
                concerned_object=self))
        max_scan = audit_settings['audit.projects.permissions.maxScanGroups']
        if counts['scan'] > max_scan:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_SCAN_GROUPS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['scan'], max_scan),
                concerned_object=self))
        max_issue_adm = audit_settings['audit.projects.permissions.maxIssueAdminGroups']
        if counts['issueadmin'] > max_issue_adm:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ISSUE_ADM_GROUPS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['issueadmin'], max_issue_adm),
                concerned_object=self))
        max_spots_adm = audit_settings['audit.projects.permissions.maxHotspotAdminGroups']
        if counts['securityhotspotadmin'] > max_spots_adm:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_HOTSPOT_ADM_GROUPS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['securityhotspotadmin'], max_spots_adm),
                concerned_object=self))
        max_admins = audit_settings['audit.projects.permissions.maxAdminGroups']
        if counts['admin'] > max_admins:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ADM_GROUPS)
            problems.append(pb.Problem(
                rule.type, rule.severity,
                rule.msg.format(self.key, counts['admin'], max_admins),
                concerned_object=self))
        return problems

    def __audit_permissions__(self, audit_settings):
        if not audit_settings['audit.projects.permissions']:
            util.logger.debug('Auditing project permissions is disabled by configuration, skipping')
            return []
        util.logger.debug("Auditing project '%s' permissions", self.key)
        problems = (self.__audit_user_permissions__(audit_settings)
                    + self.__audit_group_permissions__(audit_settings))
        if not problems:
            util.logger.debug("No issue found in project '%s' permissions", self.key)
        return problems

    def __audit_last_analysis__(self, audit_settings):
        util.logger.debug("Auditing project '%s' last analysis date", self.key)
        problems = []
        age = self.age_of_last_analysis()
        if age is None:
            if not audit_settings['audit.projects.neverAnalyzed']:
                util.logger.debug("Auditing of never analyzed projects is disabled, skipping")
            else:
                rule = rules.get_rule(rules.RuleId.PROJ_NOT_ANALYZED)
                msg = rule.msg.format(self.key)
                util.logger.warning(msg)
                problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
            return problems

        max_age = audit_settings['audit.projects.maxLastAnalysisAge']
        if max_age == 0:
            util.logger.debug("Auditing of projects with old analysis date is disabled, skipping")
        elif age > max_age:
            rule = rules.get_rule(rules.RuleId.PROJ_LAST_ANALYSIS)
            severity = sev.Severity.HIGH if age > 365 else rule.severity
            loc = self.get_measure('ncloc', fallback='0')
            msg = rule.msg.format(self.key, loc, age)
            util.logger.warning(msg)
            problems.append(pb.Problem(rule.type, severity, rule.msg.format(self.key, loc, age), concerned_object=self))

        util.logger.debug("Project '%s' last analysis is %d days old", self.key, age)
        return problems

    def __audit_branches(self, audit_settings):
        if audit_settings['audit.projects.branches.maxLastAnalysisAge'] == 0:
            util.logger.debug("Auditing of branchs last analysis age is disabled, skipping...")
            return []
        util.logger.debug("Auditing project '%s' branches", self.key)
        problems = []
        for branch in self.get_branches():
            problems += branch.audit(audit_settings)
        return problems

    def __audit_pull_requests(self, audit_settings):
        max_age = audit_settings['audit.projects.pullRequests.maxLastAnalysisAge']
        if max_age == 0:
            util.logger.debug("Auditing of pull request last analysis age is disabled, skipping...")
            return []
        problems = []
        for pr in self.get_pull_requests():
            problems += pr.audit(audit_settings)
        return problems

    def __audit_visibility__(self, audit_settings):
        if not audit_settings.get('audit.projects.visibility', True):
            util.logger.debug("Project visibility audit is disabled by configuration, skipping...")
            return []
        util.logger.debug("Auditing project '%s' visibility", self.key)
        resp = env.get('navigation/component', ctxt=self.env, params={'component': self.key})
        data = json.loads(resp.text)
        visi = data['visibility']
        if visi != 'private':
            rule = rules.get_rule(rules.RuleId.PROJ_VISIBILITY)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(self.key, visi),
                               concerned_object=self)]

        util.logger.debug("Project '%s' visibility is private", self.key)
        return []

    def __audit_languages__(self, audit_settings):
        if not audit_settings.get('audit.xmlLoc.suspicious', False):
            util.logger.debug('XML LoCs count audit disabled by configuration, skipping')
            return []
        util.logger.debug("Auditing project '%s' suspicious XML LoC count", self.key)

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
        util.logger.debug("Project '%s' XML LoCs count seems reasonable", self.key)
        return []

    def audit(self, audit_settings):
        util.logger.debug("Auditing project '%s'", self.key)
        return (
            self.__audit_last_analysis__(audit_settings)
            + self.__audit_branches(audit_settings)
            + self.__audit_pull_requests(audit_settings)
            + self.__audit_visibility__(audit_settings)
            + self.__audit_languages__(audit_settings)
            + self.__audit_permissions__(audit_settings)
        )

    def delete_if_obsolete(self, days=180):
        today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
        mindate = today - datetime.timedelta(days=days)
        last_analysis = self.last_analysis_date(include_branches=True)
        loc = int(self.get_measure('ncloc'))
        print("Project key '%s' - %d LoCs - Not analysed for %d days" %
              (self.key, loc, (today - last_analysis).days))
        util.logger.debug("Project key '%s' - %d LoCs - Not analysed for %d days",
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
        if self.env.version() < (9, 2, 0) and self.env.edition() not in ['enterprise', 'datacenter']:
            raise env.UnsupportedOperation("Project export is only available with Enterprise and Datacenter Edition,"
            " or with SonarQube 9.2 or higher for any Edition")
        resp = env.post('project_dump/export', params={'key': self.key}, ctxt=self.env)
        if resp.status_code != 200:
            return {'status': 'HTTP_ERROR {0}'.format(resp.status_code)}
        data = json.loads(resp.text)
        params = {'type': 'PROJECT_EXPORT', 'status': 'PENDING,IN_PROGRESS,SUCCESS,FAILED,CANCELED'}
        if self.env.version() >= (8, 0, 0):
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
        if self.env.edition() not in ['enterprise', 'datacenter']:
            raise env.UnsupportedOperation("Project import is only available with Enterprise and Datacenter Edition")
        resp = env.post('project_dump/import', params={'key': self.key}, ctxt=self.env)
        return resp.status_code

    def search_custom_measures(self):
        return custom_measures.search(self.key, self.env)

def __get_permissions_counts__(entities):
    counts = {}
    counts['overall'] = 0
    for permission in perms.PROJECT_PERMISSIONS:
        counts[permission] = 0
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

    util.logger.debug("Project search returned %d projects", len(project_list))
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


def audit(audit_settings, endpoint=None):
    util.logger.info("--- Auditing projects ---")
    plist = search(endpoint)
    problems = []

    for key, p in plist.items():
        problems += p.audit(audit_settings)
        if not audit_settings['audit.projects.duplicates']:
            continue
        util.logger.debug("Auditing for potential duplicate projects")
        for key2 in plist:
            if key2 != key and re.match(key2, key):
                rule = rules.get_rule(rules.RuleId.PROJ_DUPLICATE)
                util.logger.warning("Project '%s' is likely to be a branch of project '%s'", key, key2)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(key, key2),
                                   concerned_object=p))

    if not audit_settings.get('audit.projects.duplicates', False):
        util.logger.info("Project duplicates auditing was disabled by configuration")
    return problems
