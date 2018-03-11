#!python3

import json
import requests
import sys
import sonarqube.env

class ApiError(Exception):
    pass


class UnknownIssueError(ApiError):
    pass


class IssueChangeLog:
    def __init__(self, issue_key):
        params = dict(format='json', issue=issue_key)
        resp = requests.get(url=sonarqube.env.get_url() + '/api/issues/changelog', auth=sonarqube.env.get_credentials(), params=params)
        data = json.loads(resp.text)
        self.json = data['changelog']

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
        self.changelog = ''
        self.comments = ''
        self.line = ''
        self.component = ''

    def __init__(self, json):
        self.feed(json)

    def feed(self, json):
        self.id = json['key']
        self.json = json
        self.severity = json['severity']
        self.type = json['type']
        self.author = json['author']
        self.assignee = '' # json['assignee']
        self.status = json['status']
        self.resolution = json['resolution']
        self.rule = json['rule']
        self.project = json['project']
        self.language = ''
        self.changelog = '' # To read with API
        self.comments = json['comments']
        self.component = json['component']
        self.line = json['line']

    def read(self):
        resp = requests.get(url=sonarqube.env.get_url() + '/api/issues/search', auth=sonarqube.env.get_credentials(), params=dict(issues=self.id))
        self.feed(resp.issues[0])

    def get_changelog(self):
        self.changelog = IssueChangeLog(self.id)
        
    def add_comment(self, comment_text):
        params = dict(issue=self.id, text=comment_text)
        resp = requests.post(url=sonarqube.env.get_url() + '/api/issues/add_comment', auth=sonarqube.env.get_credentials(), params=params)

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
    
    def tostring(self):
        """Dumps the object in a string"""
        return json.dumps(self.json, sort_keys=True, indent=3, separators=(',', ': '))


def has_been_marked_as_statuses(diffs, statuses):
    for diff in diffs:
        if diff["key"] == "resolution":
            for status in statuses:
                if diff["newValue"] == status:
                    return True
    return False


def has_been_marked_as_false_positive(issue_key):
    changelog = get_changelog(issue_key)
    for log in changelog:
        for diff in log['diffs']:
            if diff["key"] == "resolution" and diff["newValue"] == "FALSE-POSITIVE":
                return True
    return False


def has_been_marked_as_wont_fix(issue_key):
    changelog = get_changelog(issue_key)
    for log in changelog:
        for diff in log['diffs']:
            if diff["key"] == "resolution" and diff["newValue"] == "WONTFIX":
                return True
    return False


def check_fp_transition(diffs):
    print("----------------- DIFFS     -----------------")
    print_object(diffs)
    if diffs[0]['key'] == "resolution" and (
        diffs[1]["oldValue"] == "FALSE-POSITIVE" or diffs[1]["oldValue"] == "WONTFIX") and diffs[0]["newValue"] == "FIXED":
        return True
    return False


def print_object(o):
    print(json.dumps(o, indent=3, sort_keys=True))





def get_comments(issue_key):
    # print('Searching comments for issue key ', issue_key)
    params = dict(format='json', issues=issue_key, additionalFields='comments')
    resp = requests.get(url=sonarqube.env.get_url() + 'api/issues/search', auth=sonarqube.env.get_credentials(), params=params)
    data = json.loads(resp.text)
    return data['issues'][0]['comments']


def sort_changelog(changelog):
    sorted_log = dict()
    for log in changelog:
        sorted_log[log['creationDate']] = ('log', log)
    return sorted_log


def sort_comments(comments):
    sorted_comments = dict()
    for comment in comments:
        sorted_comments[comment['createdAt']] = ('comment', comment)
    return sorted_comments

def search(project_key, sq_url = sonarqube.env.get_url()):
    params = dict(ps='1', componentKeys=project_key, additionalFields='_all')
    resp = requests.get(url=sq_url + '/api/issues/search', auth=sonarqube.env.get_credentials(), params=params)
    data = json.loads(resp.text)
    json.dump(data, sys.stdout, sort_keys=True, indent=3, separators=(',', ': '))
    print("Number of issues:", data['paging']['total'])
    all_issues = []
    for json_issue in data['issues']:
        all_issues = all_issues + [Issue(json_issue)]
 
    #all_json_issues = data['issues']
    #json.dump(all_json_issues, sys.stdout, sort_keys=True, indent=3, separators=(',', ': '))
    #for issue in all_issues:
    #    print(issue.toString)
    return all_issues

