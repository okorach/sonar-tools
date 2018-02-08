#!python3

import json
import requests
import sys

token = '2a9e1ccb0a18f9626d2f90f5cdac391e6280f7d1'
credentials = (token, '')
root_url = "http://localhost:9000"

class ApiError(Exception):
    pass


class UnknownIssueError(ApiError):
    pass


class IssueChangeLog:
    def __init__(self, id):
        self.id = id
        params = dict(format='json', issue=self.id)
        resp = requests.get(url=root_url + '/api/issues/changelog', auth=credentials, params=params)
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
        resp = requests.get(url=root_url + '/api/issues/search', auth=credentials, params=dict(issues=self.id))
        print(resp)

    def get_changelog(self):
        params = dict(format='json', issue=self.id)
        resp = requests.get(url=root_url + '/api/issues/changelog', auth=credentials, params=params)
        data = json.loads(resp.text)
        return data['changelog']

    def add_comment(self, comment_text):
        params = dict(issue=self.id, text=comment_text)
        resp = requests.get(url=root_url + '/api/issues/add_comment', auth=credentials, params=params)

    # def delete_comment(self, comment_id):

    # def edit_comment(self, comment_id, comment_str)

    def get_severity(self, force_api = False):
        if (force_api or self.severity == ''):
            self.read()
            params = dict(issues=self.id)
            resp = requests.get(url=root_url + '/api/issues/add_comment', auth=credentials, params=params)
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
    
    def toString(self):
        """Dumps the object in a string"""
        return json.dumps(self.json, sort_keys=True, indent=3, separators=(',', ': '))

def search(project_key, sq_url = root_url):
    params = dict(ps='1', componentKeys=project_key, additionalFields='_all')
    resp = requests.get(url=sq_url + '/api/issues/search', auth=credentials, params=params)
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

