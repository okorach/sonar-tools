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

import sonarqube.audit_severities as sev
import sonarqube.audit_types as typ
import sonarqube.audit_rules as rules
import sonarqube.audit_problem as pb
import sonarqube.permissions as perms
import sonarqube.custom_measures as custom_measures

PORTFOLIOS = {}

LIST_API = 'views/list'
SEARCH_API = 'views/search'
GET_API = 'views/show'
MAX_PAGE_SIZE = 500
PORTFOLIO_QUALIFIER = 'VW'


class Portfolio(comp.Component):

    def __init__(self, key, endpoint, data=None):
        super().__init__(key=key, sqenv=endpoint)
        self.id = None
        self.name = None
        self.selection_mode = None
        self.visibility = None
        self.permissions = None
        self.user_permissions = None
        self.group_permissions = None
        self.branches = None
        self.ncloc = None
        self.nbr_projects = None
        self.__load__(data)
        PORTFOLIOS[key] = self

    def __str__(self):
        return f"Portfolio key '{self.key}'"

    def __load__(self, data=None):
        ''' Loads a portfolio object with contents of data '''
        if data is None:
            resp = env.get(GET_API, ctxt=self.env, params={'key': self.key})
            data = json.loads(resp.text)
        self.id = data.get('key', None)
        self.name = data.get('name', None)
        self.visibility = data.get('visibility', None)
        self.selection_mode = data.get('selectionMode', None)

    def get_name(self):
        if self.name is None:
            self.__load__()
        return self.name

    def get_visibility(self):
        if self.visibility is None:
            self.__load__()
        return self.visibility

    def get_selection_mode(self):
        if self.selection_mode is None:
            self.__load__()
        return self.selection_mode

    def get_components(self):
        resp = env.get('measures/component_tree', ctxt=self.env,
            params={'component': self.key, 'metricKeys':'ncloc', 'strategy':'children', 'ps':500})
        comp_list = {}
        for comp in json.loads(resp.text)['components']:
            comp_list[comp['key']] = comp
        return comp_list

    def get_projects_count(self):
        if self.nbr_projects is None:
            data = env.get('measures/components', ctxt=self.env,
                params={'component': self.key, 'metricKeys':'projects,ncloc'})['measures']
            for m in data:
                if m['metric'] == 'projects':
                    self.nbr_projects = m['value']
                elif m['metric'] == 'ncloc':
                    self.ncloc = m['value']
        return self.nbr_projects
  
    def delete(self, api='views/delete', params=None):
        ip = '10.10.1.10'
        resp = env.post('views/delete', ctxt=self.env, params={'key': self.key})
        return True

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
            loc = self.get_measure('ncloc', fallback='0')
            return [pb.Problem(rule.type, severity, rule.msg.format(self.key, loc, age), concerned_object=self)]

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


def count(endpoint=None):
    resp = env.get(SEARCH_API, ctxt=endpoint, params={'ps':1})
    data = json.loads(resp.text)
    return data['paging']['total']

def search(endpoint=None):
    resp = env.get(LIST_API, ctxt=endpoint)
    data = json.loads(resp.text)
    plist = {}
    for p in data['views']:
        plist[p['key']] = Portfolio(p['key'], endpoint=endpoint, data=p)
    return plist


def get(key, sqenv=None):
    global PORTFOLIOS
    if key not in PORTFOLIOS:
        _ = Portfolio(key=key, endpoint=sqenv)
    return PORTFOLIOS[key]


def audit(audit_settings, endpoint=None):
    plist = search(endpoint)
    problems = []
    for key, p in plist.items():
        problems += p.audit(audit_settings)
    return problems
