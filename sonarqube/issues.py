#!python3

import sys
import re
import datetime
import json
import requests
import sonarqube.env as env
import sonarqube.projects as projects
import sonarqube.sqobject as sq

OPTIONS_ISSUES_SEARCH = ['additionalFields', 'asc', 'assigned', 'assignees', 'authors', 'componentKeys',
                         'createdAfter', 'createdAt', 'createdBefore', 'createdInLast', 'facetMode', 'facets',
                         'issues', 'languages', 'onComponentOnly', 'p', 'ps', 'resolutions', 'resolved',
                         'rules', 's', 'severities', 'sinceLeakPeriod', 'statuses', 'tags', 'types']

class ApiError(Exception):
    pass


class UnknownIssueError(ApiError):
    pass

class TooManyIssuesError(Exception):
    def __init__(self, nbr_issues, message):
        super(TooManyIssuesError, self).__init__()
        self.nbr_issues = nbr_issues
        self.message = message

class IssueComments:
    def __init__(self, json_data):
        self.json = json_data

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

class IssueChangeLog(sq.SqObject):
    def __init__(self, issue_key, sqenv):
        self.env = sqenv
        self.env.debug('Getting changelog for issue key ' + issue_key)
        parms = dict(format='json', issue=issue_key)
        resp = self.get('/api/issues/changelog', parms)
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


class Issue(sq.SqObject):
    def __init__(self, issue_key, env):
        self.env = env
        self.id = issue_key
        self.json = None
        self.severity = None
        self.type = None
        self.author = None
        self.assignee = None
        self.status = None
        self.resolution = None
        self.rule = None
        self.project = None
        self.language = None
        self.changelog = None
        self.comments = None
        self.line = None
        self.component = None
        self.message = None
        self.debt = None
        self.sonarqube = None
        self.creation_date = None
        self.modification_date = None
        self.hash = None

    def feed(self, json):
        self.json = json
        #env.debug('------ISSUE------')
        #env.debug(self.to_string())

        self.id = json['key']
        self.type = json['type']
        if self.type != 'SECURITY_HOTSPOT':
            self.severity = json['severity']
        self.author = json['author']
        self.assignee = None # json['assignee']
        self.status = json['status']
        try:
            self.line = json['line']
        except KeyError:
            self.line = None

        self.resolution = None # json['resolution']
        self.rule = json['rule']
        self.project = json['project']
        self.language = None
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
        resp = self.get('/api/issues/search', parms)
        self.feed(resp.issues[0])

    def get_changelog(self, force_api = False):
        if (force_api or self.changelog is None):
            self.changelog = IssueChangeLog(self.id, self.env)
            env.debug('---In get_changelog----\n%s' % self.changelog.to_string())
        return self.changelog

    def has_changelog(self):
        return self.get_changelog().size() > 0

    def get_comments(self):
        try:
            self.comments = IssueComments(self.json['comments'])
        except KeyError:
            self.comments = None
        return self.comments

    def has_comments(self):
        comments = self.get_comments()
        return False if comments is None else comments.size() > 0

    def has_changelog_or_comments(self):
        return self.has_changelog() or self.has_comments()

    def add_comment(self, comment_text):
        parms = dict(issue=self.id, text=comment_text)
        self.post('/api/issues/add_comment', parms)

    # def delete_comment(self, comment_id):

    # def edit_comment(self, comment_id, comment_str)

    def get_severity(self, force_api = False):
        if force_api or self.severity is None:
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

    def set_type(self, issue_type):
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
        env.debug("Comparing 2 issues: %s and %s" % (self.to_string, another_issue.to_string()))
        env.debug("=" * 20)
        identical = (self.rule == another_issue.rule and self.hash == another_issue.hash and
                     self.component == another_issue.component and
                     self.message == another_issue.message and self.debt == another_issue.debt)
        env.debug(identical)
        env.debug("=" * 20)
        return identical

    def match(self, another_issue):
        env.debug("=" * 20)
        env.debug("Comparing 2 issues: %s and %s" % (self.to_string, another_issue.to_string()))
        if self.rule != another_issue.rule or self.hash != another_issue.hash:
            match_level = 0
        else:
            match_level = 1
            if self.component != another_issue.component:
                match_level -= 0.1
            if self.message != another_issue.message:
                match_level -= 0.1
            if self.debt != another_issue.debt:
                match_level -= 0.1
        env.debug("Match level %3.0f%%\n" % (match_level * 100))
        env.debug("=" * 20)
        return match_level

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
        csv = ';'.join([str(x) for x in [self.id, self.rule, self.type, self.severity, self.status,
                                         cdate, ctime, mdate, mtime, self.project,
                                         projects.get_project_name(self.project, self.env), self.component, line,
                                         debt, '"'+msg+'"']])
        return csv

#------------------------------- Static methods --------------------------------------
def check_fp_transition(diffs):
    env.debug("----------------- DIFFS     -----------------")
    #print_object(diffs)
    if diffs[0]['key'] == "resolution" and diffs[0]["newValue"] == "FIXED" and (
       diffs[1]["oldValue"] == "FALSE-POSITIVE" or diffs[1]["oldValue"] == "WONTFIX"):
        return True
    return False

def sort_comments(comments):
    sorted_comments = dict()
    for comment in comments:
        sorted_comments[comment['createdAt']] = ('comment', comment)
    return sorted_comments

def search(sqenv = None, **kwargs):
    parms = dict()
    # for key, value in kwargs.items():
    parms = get_issues_search_parms(kwargs)
    if sqenv is None:
        resp = env.get('/api/issues/search', parms)
    else:
        resp = sqenv.get('/api/issues/search', parms)
    data = json.loads(resp.text)
    #env.json_dump_debug(data)
    nbr_issues = data['paging']['total']
    env.debug("Number of issues: ", nbr_issues)
    page = data['paging']['pageIndex']
    nbr_pages = ((data['paging']['total']-1) // data['paging']['pageSize'])+1
    env.debug("Page: ", data['paging']['pageIndex'], '/', nbr_pages)
    all_issues = []
    for json_issue in data['issues']:
        issue = Issue(json_issue['key'], kwargs['env'])
        issue.feed(json_issue)
        all_issues = all_issues + [issue]
        #print('----issues.ISSUE%s' % ('-'*30))
        #json.dump(json_issue, sys.stdout, sort_keys=True, indent=3, separators=(',', ': '))
        #print(issue.toString)
    return dict(page=page, pages=nbr_pages, total=nbr_issues, issues=all_issues)

def search_all_issues(sqenv = None, **kwargs):
    kwargs['ps'] = 500
    page = 1
    nbr_pages = 1
    issues = []
    while page <= nbr_pages and page <= 20:
        kwargs['p'] = page
        returned_data = search(sqenv = sqenv, **kwargs)
        issues = issues + returned_data['issues']
        #if returned_data['total'] > 10000 and page == 20: NOSONAR
        #    raise TooManyIssuesError(returned_data['total'], 'Request found %d issues which is more than the maximum allowed 10000' % returned_data['total']) NOSONAR
        page = returned_data['page']
        nbr_pages = returned_data['pages']
        page = page + 1
        kwargs['p'] = page
    env.debug ("Total number of issues: ", len(issues))
    return issues

def get_one_issue_date(sqenv=None, asc_sort='true', **kwargs):
    ''' Returns the date of one issue found '''
    kwtemp = kwargs.copy()
    kwtemp['s'] = 'CREATION_DATE'
    kwtemp['asc'] = asc_sort
    kwtemp['ps'] = 1
    try:
        returned_data = search(sqenv=sqenv, **kwtemp)
    except TooManyIssuesError:
        pass

    if returned_data['total'] == 0:
        return None
    else:
        return returned_data['issues'][0].creation_date

def get_oldest_issue(sqenv=None, **kwargs):
    ''' Returns the oldest date of all issues found '''
    return get_one_issue_date(sqenv=sqenv, asc_sort='true', **kwargs)

def get_newest_issue(sqenv=None, **kwargs):
    ''' Returns the newest date of all issues found '''
    return get_one_issue_date(sqenv=sqenv, asc_sort='false', **kwargs)

def get_number_of_issues(sqenv=None, **kwargs):
    ''' Returns number of issues of a search '''
    kwtemp = kwargs.copy()
    kwtemp['ps'] = 1
    returned_data = search(sqenv=sqenv, **kwtemp)
    env.debug("Project %s has %d issues" % (kwargs['componentKeys'], returned_data['total']))
    return returned_data['total']

def search_project_daily_issues(key, day, sqenv=None, **kwargs):
    kw = kwargs.copy()
    kw['componentKeys'] = key
    if kwargs is None or 'severities' not in kwargs:
        severities = {'INFO','MINOR','MAJOR','CRITICAL','BLOCKER'}
    else:
        severities = re.split(',', kwargs['severities'])
    if kwargs is None or 'types' not in kwargs:
        types = {'CODE_SMELL','VULNERABILITY','BUG','SECURITY_HOTSPOT'}
    else:
        types = re.split(',', kwargs['types'])
    kw['createdAfter'] = day
    kw['createdBefore'] = day
    issues = []
    for severity in severities:
        kw['severities'] = severity
        for issue_type in types:
            kw['types'] = issue_type
            issues = issues + search_all_issues(sqenv=sqenv, **kw)
    env.log("INFO: %d daily issues for project key %s on %s" % (len(issues), key, day))
    return issues

def search_project_issues(key, sqenv=None, **kwargs):
    kwargs['componentKeys'] = key
    oldest = get_oldest_issue(sqenv=sqenv, **kwargs)
    if oldest is None:
        return []
    startdate = datetime.datetime.strptime(oldest, '%Y-%m-%dT%H:%M:%S%z')
    enddate = datetime.datetime.strptime(get_newest_issue(sqenv=sqenv, **kwargs), '%Y-%m-%dT%H:%M:%S%z')

    nbr_issues = get_number_of_issues(sqenv=sqenv, **kwargs)
    days_slice = abs((enddate - startdate).days)+1
    if nbr_issues > 10000:
        days_slice = (10000 * days_slice) // (nbr_issues * 4)
    env.debug("For project %s, slicing by %d days, between %s and %s" % (key, days_slice, startdate, enddate))

    issues = []
    window_start = startdate
    while window_start <= enddate:
        current_slice = days_slice
        sliced_enough = False
        while not sliced_enough:
            window_size = datetime.timedelta(days=current_slice)
            kwargs['createdAfter']  = "%04d-%02d-%02d" % (window_start.year, window_start.month, window_start.day)
            window_stop = window_start + window_size
            kwargs['createdBefore'] = "%04d-%02d-%02d" % (window_stop.year, window_stop.month, window_stop.day)
            found_issues = search_all_issues(sqenv=sqenv, **kwargs)
            if len(found_issues) < 10000:
                issues = issues + found_issues
                env.debug("Got %d issue, OK, go to next window" % len(found_issues))
                sliced_enough = True
                window_start = window_stop + datetime.timedelta(days=1)
            elif current_slice == 0:
                found_issues = search_project_daily_issues(key, kwargs['createdAfter'], sqenv, **kwargs)
                issues = issues + found_issues
                sliced_enough = True
                env.log("ERROR: Project key %s has many issues on %s, showing only the first %d" %
                        (key, window_start, len(found_issues)))
                window_start = window_stop + datetime.timedelta(days=1)
            else:
                sliced_enough = False
                current_slice = current_slice // 2
                env.debug("Reslicing with a thinner slice of %d days" % current_slice)

    env.debug("For project %s, %d issues found" % (key, len(issues)))
    return issues

def search_all_issues_unlimited_old(sqenv=None, **kwargs):
    if kwargs is None or 'componentKeys' not in kwargs:
        project_list = projects.get_projects_list(sqenv=kwargs['env'])
    else:
        project_list= { kwargs['componentKeys'] }
    if kwargs is None or 'severities' not in kwargs:
        severities = {'INFO','MINOR','MAJOR','CRITICAL','BLOCKER'}
    else:
        severities = {kwargs['severities']}

    if kwargs is None or 'types' not in kwargs:
        types = {'CODE_SMELL','VULNERABILITY','BUG','SECURITY_HOTSPOT'}
    else:
        types = {kwargs['types']}

    creation_periods = []
    if kwargs is None or 'creation_date' not in kwargs:
        oldest = get_oldest_issue(sqenv=sqenv, **kwargs)
        startdate = datetime.datetime.strptime(oldest, '%Y-%m-%dT%H:%M:%S%z')
        today = datetime.datetime.now(startdate.tzinfo)
        date_increment = datetime.timedelta(days=10)

        while startdate <= today:
            s_date = "%04d-%02d-%02d" % (startdate.year, startdate.month, startdate.day)
            enddate = startdate + date_increment
            e_date = "%04d-%02d-%02d" % (enddate.year, enddate.month, enddate.day)
            creation_periods.append([s_date, e_date])
            startdate = enddate + datetime.timedelta(days=1)
    else:
        s, e = re.split( ':', kwargs['creation_period'])
        creation_periods = { [s, e] }
    issues = []
#    for pk in project_list:
#        kwargs['componentKeys'] = pk
    for creation_period in creation_periods:
        kwargs['createdAfter'], kwargs['createdBefore'] = creation_period
        for severity in severities:
            kwargs['severities'] = severity
            for issue_type in types:
                kwargs['types'] = issue_type
                issues = issues + search_all_issues(sqenv=sqenv, **kwargs)
    return issues

def search_all_issues_unlimited(sqenv=None, **kwargs):

    if kwargs is None or 'componentKeys' not in kwargs:
        project_list = projects.get_projects_list(sqenv=sqenv)
    else:
        project_list= re.split(',', kwargs['componentKeys'])
    issues = []
    for project in project_list:
        issues = issues + search_project_issues(key=project, sqenv=sqenv, **kwargs)
    return issues

def apply_changelog(target_issue, source_issue, do_it_really=True):
    if source_issue.has_changelog():
        events_by_date = source_issue.get_changelog().sort()
    if source_issue.has_comments():
        comments_by_date = source_issue.get_comments().sort()
        for date in comments_by_date:
            events_by_date[date] = comments_by_date[date]

    if not events_by_date:
        print("Sibling has no changelog, no action taken")
        return

    if do_it_really:
        print('   Not joking I am doing it')
    key = target_issue.id
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
            continue

        if not do_it_really:
            print('   DRY RUN for %s' % operation)
            continue
        resp = target_issue.post('/api/' + api, params)
        if resp.status_code != 200:
            print('HTTP Error %d from SonarQube API query' % resp.status_code)

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

def search_siblings(an_issue, issue_list, only_new_issues=True):
    siblings = []
    for issue in issue_list:
        #if identical_attributes(closed_issue, iss, ['rule', 'component', 'message', 'debt']):
        #print("Looking at CLOSED " + closed_issue.to_string())
        #print("Looking at ISSUE " + issue.to_string())
        if issue.identical_to(an_issue):
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

def get_issues_search_parms(parms):
    outparms= dict()
    for key in parms:
        if parms[key] is not None and key in OPTIONS_ISSUES_SEARCH:
            outparms[key] = parms[key]
    return outparms
