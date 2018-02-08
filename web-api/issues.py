#!python3


class ApiError(Exception):
    pass


class UnknownIssueError(ApiError):
    pass


class IssueChangeLog:
    def __init__(self, issue_key):
        params = dict(format='json', issue=self.issue_key)
        resp = requests.get(url=root_url + 'api/issues/changelog', auth=credentials, params=params)
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

    def read(self, issue_key):
        params = dict(issue=self.issue_key)
        resp = requests.get(url=root_url + 'api/issues/search', auth=credentials, dict(issues=self.issue_key))
        print(resp)

    def get_changelog(self):
        params = dict(format='json', issue=self.issue_key)
        resp = requests.get(url=root_url + 'api/issues/changelog', auth=credentials, params=params)
        data = json.loads(resp.text)
        return data['changelog']

    def get_tag(self, tag_name):
        if tag_name in FileTags.TAGS.keys():
            return self.exif_dict[FileTags.TAGS[tag_name][0]][FileTags.TAGS[tag_name][1]]
        else:
            raise UnknownTagError

    def set_tag(self, tag_name, tag_value):
        if tag_name in FileTags.TAGS.keys():
            self.exif_dict[FileTags.TAGS[tag_name][0]][FileTags.TAGS[tag_name][1]] = tag_value
        else:
            raise UnknownTagError

    def add_comment(self, comment_text):
        params = dict(issue=self.key, text=comment_text)
        resp = requests.get(url=root_url + 'api/issues/add_comment', auth=credentials, params=params)

    # def delete_comment(self, comment_id):

    # def edit_comment(self, comment_id, comment_str)

    def get_severity(self, force_api = False):
        if (force_api or self.severity == ''):
            self.search()
            params = dict(issues=self.key)
            resp = requests.get(url=root_url + 'api/issues/add_comment', auth=credentials, params=params)
        return self.severity

    def set_severity(self, severity):
        """Sets severity"""

    def assign(self, assignee):
        """Assigns issue"""

    def get_authors(self):
        """Get SCM author, if available"""

    def set_tag(self, tag):
        """Sets tags"""

    def get_tags(self):
        """Gets tags"""

    def set_type(self, type):
        """Sets type"""

    def get_type(self):
        """Gets type"""


def loadIssues:
    params = dict(ps='500', componentKeys=project_key, additionalFields='_all')
    resp = requests.get(url=root_url + 'api/issues/search', auth=credentials, params=params)
    data = json.loads(resp.text)
    print("Number of issues:", data['paging']['total'])

    all_issues = data['issues']
    non_closed_issues = []
    mistakenly_closed_issues = []

    for issue in all_issues: