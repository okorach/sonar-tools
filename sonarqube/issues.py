#!python3

import json
import sys
import env
import requests
import projects
import re

class ApiError(Exception):
    pass


class UnknownIssueError(ApiError):
    pass


class IssueComments:
    def __init__(self, json):
        self.json = json

    def sort(self):
        sorted_comment = dict()
        for comment in self.json:
            sorted_comment[comment['createdAt']] = ('comment', comment)
        return sorted_comment

    def size(self):
        n = 0
        for items in self.json:
            n = n + 1
        return n

    def size2(self):
        return len(self.json)
    
class IssueChangeLog:
    def __init__(self, issue_key, sonarqube):
        env.debug('Getting changelog for issue key ' + issue_key)
        parms = dict(format='json', issue=issue_key)
        if (sonarqube is None):
            resp = env.get('/api/issues/changelog', parms)
        else:
            resp = sonarqube.get('/api/issues/changelog', parms)
        data = json.loads(resp.text)
        self.json = data['changelog']

    def sort(self):
        sorted_log = dict()
        for log in self.json:
            sorted_log[log['creationDate']] = ('log', log)
        return sorted_log

    def size(self):
        n = 0
        for items in self.json:
            n = n + 1
        return n

    def size2(self):
        return len(self.json)

    def to_string(self):
        """Dumps the object in a string"""
        return json.dumps(self.json, sort_keys=True, indent=3, separators=(',', ': '))



    def get_json(self):
        return self.json


class Issue:
    def __init__(self, issue_key):
        self.id = issue_key
        self.json = ''
        self.severity = ''
        self.type = ''
        self.author = ''
        self.assignee = ''
        self.status = ''
        self.resolution = ''
        self.rule = ''
        self.project = ''
        self.language = ''
        self.changelog = None
        self.comments = ''
        self.line = None
        self.component = ''
        self.message = ''
        self.debt = ''
        self.sonarqube = None
        self.creation_date = ''
        self.modification_date = ''

    def set_env(self, env):
        self.sonarqube = env

    def feed(self, json):
        self.json = json
        env.debug('------ISSUE------')
        env.debug(self.to_string())

        self.id = json['key']
        self.severity = json['severity']
        self.type = json['type']
        self.author = json['author']
        self.assignee = '' # json['assignee']
        self.status = json['status']
        try:
            self.line = json['line']
        except KeyError:
            self.line = None

        self.resolution = '' # json['resolution']
        self.rule = json['rule']
        self.project = json['project']
        self.language = ''
        self.changelog = None
        self.creation_date = json['creationDate']
        self.modification_date = json['updateDate']
        
        self.changelog = None
        try:
            self.comments = json['comments']
        except KeyError:
            self.comments = None
        self.component = json['component']
        try:
            self.hash = json['hash']
        except KeyError:
            self.hash = None
        try:
            self.message = json['message']
        except KeyError:
            self.message = None
        try:
            self.debt = json['debt']
        except KeyError:
            self.debt = None

    def read(self):
        parms = dict(issues=self.id, additionalFields='_all')
        if (self.sonarqube is None):
            resp = env.get('/api/issues/search', parms)
        else:
            resp = self.sonarqube.get('/api/issues/search', parms)
        self.feed(resp.issues[0])

    def get_changelog(self, force_api = False):
        if (force_api or self.changelog is None):
            self.changelog = IssueChangeLog(self.id, self.sonarqube)
            env.debug('---In get_changelog----')
            env.debug(self.changelog.to_string())
        return self.changelog

    def has_changelog(self):
        return self.get_changelog().size() > 0

    def get_comments(self):
        try:
            self.comments = IssueComments(self.json['comments'], self.env)
        except KeyError:
            self.comments = None
        return self.comments

    def has_comments(self):
        comments = self.get_comments()
        return False if comments is None else comments.size() > 0

    def has_changelog_or_comments(self):
        return self.has_changelog() or self.has_comments()
        
    def add_comment(self, comment_text, myenv = None):
        parms = dict(issue=self.id, text=comment_text)
        if (myenv is None):
            env.post('/api/issues/add_comment', parms)
        else:
            myenv.post('/api/issues/add_comment', parms)

    # def delete_comment(self, comment_id):

    # def edit_comment(self, comment_id, comment_str)

    def get_severity(self, force_api = False):
        if (force_api or self.severity == ''):
            self.read()
        return self.severity

    def set_severity(self, severity):
        """Sets severity"""

    def assign(self, assignee):
        """Sets assignee"""

    def get_authors(self):
        """Gets authors from SCM"""

    def set_tags(self, tags):
        """Sets tags"""

    def get_tags(self):
        """Gets tags"""

    def set_type(self, type):
        """Sets type"""
    
    def get_type(self):
        """Gets type"""
    
    def get_status(self):
        return self.status
    

    def to_string(self):
        """Dumps the object in a string"""
        return json.dumps(self.json, sort_keys=True, indent=3, separators=(',', ': '))

    def print_issue(self):
        """Prints the issue"""
        print(self.to_string())

    def has_been_marked_as_wont_fix(self):
        changelog = self.get_changelog()
        for log in changelog:
            for diff in log['diffs']:
                if diff["key"] == "resolution" and diff["newValue"] == "WONTFIX":
                    return True
        return False

    def has_been_marked_as_false_positive(self):
        changelog = self.get_changelog()
        for log in changelog:
            for diff in log['diffs']:
                if diff["key"] == "resolution" and diff["newValue"] == "FALSE-POSITIVE":
                    return True
        return False

    def has_been_marked_as_statuses(self, diffs, statuses):
        for diff in diffs:
            if diff["key"] == "resolution":
                for status in statuses:
                    if diff["newValue"] == status:
                        return True
        return False

    def print_change_log(self):
        events_by_date = self.get_changelog().sort()
        comments_by_date = self.get_comments().sort()
        for date in comments_by_date:
            events_by_date[date] = comments_by_date[date]
        for date in sorted(events_by_date):
            print(date, ':')
            # print_object(events_by_date[date])
    
    def get_key(self):
        return self.id

            
    def identical_to(self, another_issue):
        env.debug("=" * 20)
        env.debug("Comparing potential siblings:")
        env.debug(self.to_string())
        env.debug(another_issue.to_string())
        env.debug("=" * 20)
        identical = (self.rule == another_issue.rule and self.component == another_issue.component and
            self.message == another_issue.message and self.debt == another_issue.debt and self.hash == another_issue.hash)
        env.debug(identical)
        env.debug("=" * 20)
        return identical

    def was_fp_or_wf(self):
        changelog = self.get_changelog()
        env.debug('------- ISS ChangeLog--------')
        env.debug(changelog)
        env.debug(changelog.to_string())
        for log in changelog.get_json():
            if is_log_a_closed_fp(log) or is_log_a_closed_wf(log) or is_log_a_severity_change(log) or is_log_a_type_change(
                    log):
                return True
        return False

    def to_csv(self):
        # id,project,rule,type,severity,status,creation,modification,project,file,line,debt,message
        minutes = 0
        if self.debt is None:
            debt = 0
        else:
            m = re.search(r'(\d+)kd', self.debt)
            kdays = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)d', self.debt)
            days = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)h', self.debt)
            hours = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)min', self.debt)
            minutes = int(m.group(1)) if m else 0    
            debt = ((kdays * 1000 + days) * 24 + hours) * 60 + minutes
        cdate = re.sub(r"T.*", "", self.creation_date)
        ctime = re.sub(r".*T", "", self.creation_date)
        ctime = re.sub(r"\+.*", "", ctime) # Strip timezone
        mdate = re.sub(r"T.*", "", self.modification_date)
        mtime = re.sub(r".*T", "", self.modification_date)
        mtime = re.sub(r"\+.*", "", mtime) # Strip timezone
        msg = re.sub('"','""', self.message)
        line = '-' if self.line is None else self.line
        csv = ';'.join([str(x) for x in [self.id, self.rule, self.type, self.severity, self.status, cdate, ctime,
            mdate, mtime, self.project, projects.get_project_name(self.project), self.component, line, debt, '"'+msg+'"']])
        return csv

#------------------------------- Static methods --------------------------------------
def check_fp_transition(diffs):
    env.debug("----------------- DIFFS     -----------------")
    #print_object(diffs)
    if diffs[0]['key'] == "resolution" and (
        diffs[1]["oldValue"] == "FALSE-POSITIVE" or diffs[1]["oldValue"] == "WONTFIX") and diffs[0]["newValue"] == "FIXED":
        return True
    return False

def sort_comments(comments):
    sorted_comments = dict()
    for comment in comments:
        sorted_comments[comment['createdAt']] = ('comment', comment)
    return sorted_comments

def search(**kwargs):
    parms = dict()
    # for key, value in kwargs.items():
    for arg in kwargs:
        if arg is not 'env' and arg is not 'url' and arg is not 'token':
            parms[arg] = kwargs[arg]
    if kwargs is None or 'env' not in kwargs:
        resp = env.get( '/api/issues/search', parms)
    else:
        resp = kwargs['env'].get('/api/issues/search', parms)
    data = json.loads(resp.text)
    env.json_dump_debug(data)
    nbr_issues = data['paging']['total']
    page = data['paging']['pageIndex']
    nbr_pages = ((data['paging']['total']-1) // data['paging']['pageSize'])+1
    env.debug("Number of issues: ", nbr_issues)
    env.debug("Page: ", data['paging']['pageIndex'], '/', nbr_pages)
    all_issues = []
    for json_issue in data['issues']:
        issue = Issue(0)
        issue.feed(json_issue)
        issue.set_env(kwargs['env'])
        all_issues = all_issues + [issue]
        #print('----issues.ISSUE---------------------------------------------------------------------------------------------------------------------------------')
        #json.dump(json_issue, sys.stdout, sort_keys=True, indent=3, separators=(',', ': '))
        #print(issue.toString)
    return dict(page=page, pages=nbr_pages, total=nbr_issues, issues=all_issues)

def search_all_issues(**kwargs):
    parms = dict()
    for arg in kwargs:
        parms[arg] = kwargs[arg]
    parms['ps'] = 500
    page=1
    nbr_pages=1
    issues = []
    while page <= nbr_pages and page <= 20:
        parms['p'] = page
        returned_data = search(**parms)
        issues = issues + returned_data['issues']
        page = returned_data['page']
        nbr_pages = returned_data['pages']
        page = page+1
        parms['p'] = page
    env.debug ("Total number of issues: ", len(issues))
    return issues

def search_all_issues_unlimited(**kwargs):
    if kwargs is None or 'componentKeys' not in kwargs:
        project_list = projects.get_projects_list()
    else:
        project_list= { kwargs['componentKeys'] }

    if kwargs is None or 'severities' not in kwargs:
        severities = {'INFO','MINOR','MAJOR','CRITICAL','BLOCKER'}
    else:
        severities = {kwargs['severities']}

    parms = dict()
    for arg in kwargs:
        parms[arg] = kwargs[arg]
    issues = []
    for pk in project_list:
        for severity in severities:
            parms['componentKeys'] = pk
            parms['severities'] = severity
            issues = issues + search_all_issues(**parms)
    return issues

def apply_changelog(new_issue, closed_issue, do_it_really=True):
    if (closed_issue.has_changelog()):
        events_by_date = closed_issue.get_changelog().sort()
    if (closed_issue.has_comments()):
        comments_by_date = closed_issue.get_comments().sort()
        for date in comments_by_date:
            events_by_date[date] = comments_by_date[date]
    if do_it_really:
        print('   Not joking I am doing it')

    if len(events_by_date) > 0:
        key = new_issue.id
        for date in sorted(events_by_date):
            # print_object(events_by_date[date])
            is_applicable_event = True

            if events_by_date[date][0] == 'log' and is_log_a_severity_change(events_by_date[date][1]):
                params = dict(issue=key, severity=get_log_new_severity(events_by_date[date][1]))
                operation = 'Changing severity to: ' + params['severity']
                api = 'issues/set_severity'
            elif events_by_date[date][0] == 'log' and is_log_a_type_change(events_by_date[date][1]):
                params = dict(issue=key, type=get_log_new_type(events_by_date[date][1]))
                operation = 'Changing type to: ' + params['type']
                api = 'issues/set_type'
            elif events_by_date[date][0] == 'log' and is_log_a_reopen(events_by_date[date][1]):
                params = dict(issue=key, type='reopen')
                operation = 'Reopening issue'
                api = 'issues/do_transition'
            elif events_by_date[date][0] == 'log' and is_log_a_resolve_as_fp(events_by_date[date][1]):
                params = dict(issue=key, transition='falsepositive')
                operation = 'Setting as False Positive'
                api = 'issues/do_transition'
            elif events_by_date[date][0] == 'log' and is_log_a_resolve_as_wf(events_by_date[date][1]):
                params = dict(issue=key, transition='wontfix')
                operation = 'Setting as wontfix'
                api = 'issues/do_transition'
            elif events_by_date[date][0] == 'log' and is_log_an_assignee(events_by_date[date][1]):
                params = dict(issue=key, assignee=get_log_assignee(events_by_date[date][1]))
                operation = 'Assigning issue to: ' + params['assignee']
                api = 'issues/assign'
            elif events_by_date[date][0] == 'log' and is_log_a_tag_change(events_by_date[date][1]):
                params = dict(key=key, tags=get_log_new_tag(events_by_date[date][1]).replace(' ', ','))
                operation = 'Setting new tags to: ' + params['tags']
                api = 'issues/set_tags'
            elif events_by_date[date][0] == 'comment' and is_log_a_comment(events_by_date[date][1]):
                params = dict(issue=key, text=events_by_date[date][1]['markdown'])
                operation = 'Adding comment: ' + params['text']
                api = 'issues/add_comment'
            else:
                is_applicable_event = False
                api = ''


            if is_applicable_event:
                if do_it_really:
                    resp = new_issue.sonarqube.post('/api/' + api, parms=params)
                    if resp.status_code != 200:
                        print('HTTP Error ' + str(resp.status_code) + ' from SonarQube API query')
                else:
                    print('   DRY RUN for ' + operation)
        else:
            print("Closed sibling has no changelog")


def get_log_date(log):
    return log['creationDate']


def is_log_a_closed_resolved_as(log, old_value):
    cond1 = False
    cond2 = False

    for diff in log['diffs']:
        if diff['key'] == 'resolution' and 'newValue' in diff and diff['newValue'] == 'FIXED' and 'oldValue' in diff and \
                        diff['oldValue'] == old_value:
            cond1 = True
        if diff['key'] == 'status' and 'newValue' in diff and diff['newValue'] == 'CLOSED' and 'oldValue' in diff and \
                        diff['oldValue'] == 'RESOLVED':
            cond2 = True
    return cond1 and cond2


def is_log_a_closed_wf(log):
    return is_log_a_closed_resolved_as(log, 'WONTFIX')


def is_log_a_comment(log):
    return True


def is_log_an_assign(log):
    return False


def is_log_a_tag(log):
    return False

def is_log_a_closed_fp(log):
    return is_log_a_closed_resolved_as(log, 'FALSE-POSITIVE')

def is_log_a_resolve_as(log, resolve_reason):
    cond1 = False
    cond2 = False
    for diff in log['diffs']:
        if diff['key'] == 'resolution' and 'newValue' in diff and diff['newValue'] == resolve_reason:
            cond1 = True
        if diff['key'] == 'status' and 'newValue' in diff and diff['newValue'] == 'RESOLVED':
            cond2 = True
    return cond1 and cond2

def is_log_an_assignee(log):
    for diff in log['diffs']:
        if diff['key'] == 'assignee':
            return True

def is_log_a_reopen(log):
    cond1 = False
    cond2 = False
    for diff in log['diffs']:
        if diff['key'] == 'resolution':
            cond1 = True
        if diff['key'] == 'status' and 'newValue' in diff and diff['newValue'] == 'REOPENED':
            cond2 = True
    return cond1 and cond2

def is_log_a_resolve_as_fp(log):
    return is_log_a_resolve_as(log, 'FALSE-POSITIVE')

def is_log_a_resolve_as_wf(log):
    return is_log_a_resolve_as(log, 'WONTFIX')


def log_change_type(log):
    return log['diffs'][0]['key']


def is_log_a_severity_change(log):
    return log_change_type(log) == 'severity'


def is_log_a_type_change(log):
    return log_change_type(log) == 'type'


def is_log_an_assignee_change(log):
    return log_change_type(log) == 'assignee'


def is_log_a_tag_change(log):
    return log_change_type(log) == 'tags'


def get_log_new_value(log, key_type):
    for diff in log['diffs']:
        if diff['key'] == key_type:
            return diff['newValue']
    return 'undefined'


def get_log_assignee(log):
    return get_log_new_value(log, 'assignee')


def get_log_new_severity(log):
    return get_log_new_value(log, 'severity')


def get_log_new_type(log):
    return get_log_new_value(log, 'type')


def get_log_new_tag(log):
    return get_log_new_value(log, 'tags')


def identical_attributes(o1, o2, key_list):
    for key in key_list:
        if o1[key] != o2[key]:
            return False
    return True


def search_siblings(closed_issue, issue_list, only_new_issues=True):
    siblings = []
    for issue in issue_list:
        #if identical_attributes(closed_issue, iss, ['rule', 'component', 'message', 'debt']):
        #print("Looking at CLOSED " + closed_issue.to_string())
        #print("Looking at ISSUE " + issue.to_string())
        if issue.identical_to(closed_issue):
            if only_new_issues:
                if issue.get_changelog.size() == 0:
                    # Add issue only if it has no change log, meaning it's brand new
                    siblings.append(issue)
            else:
                siblings.append(issue)
    return siblings

def print_issue(issue):
    for attr in ['rule', 'component', 'message', 'debt', 'author', 'key', 'status']:
        print (issue[attr], ',')
    print()

def to_csv_header():
    return "# id;rule;type;severity;status;creation date;creation time;modification date;modification time;project key;project name;file;line;debt(min);message"