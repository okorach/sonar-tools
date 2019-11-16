#!python3

import sys
import re
import datetime
import json
import requests
import sonarqube.env as env
import sonarqube.sqobject as sq
import sonarqube.utilities as util

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
        return len(self.json)

    def to_string(self):
        """Dumps the object in a string"""
        return json.dumps(self.json, sort_keys=True, indent=3, separators=(',', ': '))
class IssueChangeLog(sq.SqObject):
    def __init__(self, issue_key, sqenv):
        self.env = sqenv
        util.logger.debug('Getting changelog for issue key %s', issue_key)
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
        return len(self.json)

    def to_string(self):
        """Dumps the object in a string"""
        return json.dumps(self.json, sort_keys=True, indent=3, separators=(',', ': '))

    def get_json(self):
        return self.json

class Issue(sq.SqObject):
    def __init__(self, key, sqenv):
        self.env = sqenv
        self.id = key
        self.url = None
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

    def __str__(self):
        return "Key:{0} - Type:{1} - Severity:{2} - File/Line:{3}/{4} - Rule:{5}".format( \
            self.id, self.type, self.severity, self.component, self.line, self.rule)

    def to_string(self):
        """Dumps the object in a string"""
        return json.dumps(self.json, sort_keys=True, indent=3, separators=(',', ': '))

    def get_url(self):
        if self.url is None:
            self.url = '{0}/project/issues?id={1}&issues={2}'.format(self.env.get_url(), self.component, self.id)
        return self.url

    def feed(self, jsondata):
        self.json = jsondata
        self.id = jsondata['key']
        self.type = jsondata['type']
        if self.type != 'SECURITY_HOTSPOT':
            self.severity = jsondata['severity']
        self.author = jsondata['author']
        self.assignee = None # json['assignee']
        self.status = jsondata['status']
        try:
            self.line = jsondata['line']
        except KeyError:
            self.line = None

        self.resolution = None # json['resolution']
        self.rule = jsondata['rule']
        self.project = jsondata['project']
        self.language = None
        self.changelog = None
        self.creation_date = jsondata['creationDate']
        self.modification_date = jsondata['updateDate']

        self.changelog = None
        try:
            self.comments = jsondata['comments']
        except KeyError:
            self.comments = None
        self.component = jsondata['component']
        try:
            self.hash = jsondata['hash']
        except KeyError:
            self.hash = None
        try:
            self.message = jsondata['message']
        except KeyError:
            self.message = None
        try:
            self.debt = jsondata['debt']
        except KeyError:
            self.debt = None

    def read(self):
        parms = dict(issues=self.id, additionalFields='_all')
        resp = self.get('/api/issues/search', parms)
        self.feed(resp.issues[0])

    def get_changelog(self, force_api = False):
        if (force_api or self.changelog is None):
            self.changelog = IssueChangeLog(self.id, self.env)
            util.logger.debug('---In get_changelog----\n%s', self.changelog.to_string())
        return self.changelog

    def has_changelog(self):
        return self.get_changelog().size() > 0

    def get_comments(self):
        try:
            self.comments = IssueComments(self.json['comments'])
        except KeyError:
            self.comments = []
        return self.comments

    def get_all_events(self, is_sorted = True):
        events = self.get_changelog()
        comments = self.get_comments()
        for date in comments:
            events[date] = comments[date]
        if is_sorted:
            events = events.sort()
        return events

    def has_comments(self):
        comments = self.get_comments()
        return len(comments) > 0

    def has_changelog_or_comments(self):
        return self.has_changelog() or self.has_comments()

    def add_comment(self, comment):
        util.logger.debug("Adding comment %s to issue %s", comment, self.id)
        params = {'issue':self.id, 'text':comment}
        return self.do_post('issues/add_comment', **params)

    # def delete_comment(self, comment_id):

    # def edit_comment(self, comment_id, comment_str)

    def get_severity(self, force_api = False):
        if force_api or self.severity is None:
            self.read()
        return self.severity

    def set_severity(self, severity):
        """Sets severity"""
        util.logger.debug("Changing severity of issue %s from %s to %s", self.id, self.severity, severity)
        params = {'issue':self.id, 'severity':severity}
        return self.do_post('issues/set_severity', **params)

    def assign(self, assignee):
        """Sets assignee"""
        util.logger.debug("Assigning issue %s to %s", self.id, assignee)
        params = {'issue':self.id, 'assignee':assignee}
        return self.do_post('issues/assign', **params)

    def get_authors(self):
        """Gets authors from SCM"""

    def set_tags(self, tags):
        """Sets tags"""
        util.logger.debug("Setting tags %s to issue %s", tags, self.id)
        params = {'issue':self.id, 'tags':tags}
        return self.do_post('issues/set_tags', **params)

    def get_tags(self):
        """Gets tags"""

    def set_type(self, new_type):
        """Sets type"""
        util.logger.debug("Changing type of issue %s from %s to %s", self.id, self.type, new_type)
        params = {'issue':self.id, 'type':new_type}
        return self.do_post('issues/set_type', **params)

    def get_type(self):
        """Gets type"""

    def get_status(self):
        return self.status


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
            util.logger.info('%s:%s', date, str(events_by_date[date]))

    def get_key(self):
        return self.id

    def __same_rule(self, another_issue):
        return self.rule == another_issue.rule

    def __same_hash(self, another_issue):
        return self.hash == another_issue.hash

    def __same_message(self, another_issue):
        return self.message == another_issue.message

    def __same_debt(self, another_issue):
        return self.debt == another_issue.debt

    def same_general_attributes(self, another_issue):
        return self.__same_rule(another_issue) and self.__same_hash(another_issue) and \
               self.__same_message(another_issue)

    def is_vulnerability(self):
        return self.type == 'VULNERABILITY'

    def is_hotspot(self):
        return self.type == 'SECURITY_HOTSPOT'

    def is_bug(self):
        return self.type == 'BUG'

    def is_code_smell(self):
        return self.type == 'CODE_SMELL'

    def is_security_issue(self):
        return self.is_vulnerability() or self.is_hotspot()

    def __identical_security_issues(self, another_issue):
        return self.is_security_issue() and another_issue.is_security_issue()

    def identical_to(self, another_issue, ignore_component = False):
        if not self.same_general_attributes(another_issue) or \
            (self.component != another_issue.component and not ignore_component):
            util.logger.info("Issue %s and %s are different on general attributes", self.id, another_issue.id)
            return False
        # Hotspots carry no debt,so you can only check debt equality if issues
        # are not hotspots
        if not self.is_hotspot() and not another_issue.is_hotspot() and self.debt != another_issue.debt:
            util.logger.info("Issue %s and %s are different on debt", self.id, another_issue.id)
            return False
        util.logger.info("Issue %s and %s are identical", self.get_url(), another_issue.get_url())
        return True

    def identical_to_except_comp(self, another_issue):
        return self.identical_to(another_issue, True)

    def match(self, another_issue):
        util.logger.debug("Comparing 2 issues: %s and %s", str(self), str(another_issue))
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
        util.logger.debug("Match level %3.0f%%\n", (match_level * 100))
        return match_level

    def was_fp_or_wf(self):
        changelog = self.get_changelog()
        util.logger.debug(changelog)
        util.logger.debug(changelog.to_string())
        for log in changelog.get_json():
            if is_log_a_closed_fp(log) or is_log_a_closed_wf(log) or \
            is_event_a_severity_change(['log',log]) or is_event_a_type_change(['log',log]):
                return True
        return False

    def do_transition(self, transition):
        params = {'issue':self.id, 'transition':transition}
        return self.do_post('issues/do_transition', **params)

    def reopen(self):
        util.logger.debug("Reopening issue %s", self.id)
        return self.do_transition('reopen')

    def mark_as_false_positive(self):
        util.logger.debug("Marking issue %s as false positive", self.id)
        return self.do_transition('falsepositive')

    def mark_as_wont_fix(self):
        util.logger.debug("Marking issue %s as won't fix", self.id)
        return self.do_transition('wontfix')

    def mark_as_reviewed(self):
        if self.is_hotspot():
            util.logger.debug("Marking hotspot %s as reviewed", self.id)
            return self.do_transition('resolveasreviewed')
        elif self.is_vulnerability():
            util.logger.debug("Marking vulnerability %s as won't fix in replacement of 'reviewed'", self.id)
            ret = self.do_transition('wontfix')
            self.add_comment("Vulnerability marked as won't fix to replace hotspot 'reviewed' status")
            return ret
        else:
            util.logger.debug("Issue %s is neither a hotspot nor a vulnerability, cannot mark as reviewed", self.id)

    def do_post(self, api, **params):
        do_it_really = True
        if not do_it_really:
            util.logger.info('DRY RUN for %s', '/api/' + api + str(params))
            return 0
        resp = self.post('/api/' + api, params)
        if resp.status_code != 200:
            util.logger.error('HTTP Error %d from SonarQube API query: %s', resp.status_code, resp.content)
        return resp.status_code

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
        # Strip timezone
        ctime = re.sub(r"\+.*", "", ctime)
        mdate = re.sub(r"T.*", "", self.modification_date)
        mtime = re.sub(r".*T", "", self.modification_date)
        # Strip timezone
        mtime = re.sub(r"\+.*", "", mtime)
        msg = re.sub('"','""', self.message)
        line = '-' if self.line is None else self.line
        import sonarqube.projects as projects
        csv = ';'.join([str(x) for x in [self.id, self.rule, self.type, self.severity, self.status,
                                         cdate, ctime, mdate, mtime, self.project,
                                         projects.get_project_name(self.project, self.env), self.component, line,
                                         debt, '"'+msg+'"']])
        return csv

#------------------------------- Static methods --------------------------------------
def check_fp_transition(diffs):
    util.logger.debug("----------------- DIFFS     -----------------")
    return diffs[0]['key'] == "resolution" and diffs[0]["newValue"] == "FIXED" and \
           (diffs[1]["oldValue"] == "FALSE-POSITIVE" or diffs[1]["oldValue"] == "WONTFIX")

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
    nbr_issues = data['paging']['total']
    util.logger.debug("Number of issues: %d", nbr_issues)
    page = data['paging']['pageIndex']
    nbr_pages = ((data['paging']['total']-1) // data['paging']['pageSize'])+1
    util.logger.debug("Page: %d/%d", data['paging']['pageIndex'], nbr_pages)
    all_issues = []
    for json_issue in data['issues']:
        issue = Issue(key = json_issue['key'], sqenv = sqenv)
        issue.feed(json_issue)
        all_issues = all_issues + [issue]
    return dict(page=page, pages=nbr_pages, total=nbr_issues, issues=all_issues)

def search_all_issues(sqenv = None, **kwargs):
    util.logger.info('searching issues for %s', str(kwargs))
    kwargs['ps'] = 500
    page = 1
    nbr_pages = 1
    issues = []
    while page <= nbr_pages and page <= 20:
        kwargs['p'] = page
        returned_data = search(sqenv = sqenv, **kwargs)
        issues = issues + returned_data['issues']
        #if returned_data['total'] > 10000 and page == 20: NOSONAR
        #    raise TooManyIssuesError(returned_data['total'], \
        #          'Request found %d issues which is more than the maximum allowed 10000' % \
        #          returned_data['total']) NOSONAR
        page = returned_data['page']
        nbr_pages = returned_data['pages']
        page = page + 1
        kwargs['p'] = page
    util.logger.debug ("Total number of issues: %d", len(issues))
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
    util.logger.debug("Project %s has %d issues", kwargs['componentKeys'], returned_data['total'])
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
    util.logger.info("%d daily issues for project key %s on %s", len(issues), key, day)
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
    util.logger.debug("For project %s, slicing by %d days, between %s and %s", key, days_slice, startdate, enddate)

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
                util.logger.debug("Got %d issue, OK, go to next window", len(found_issues))
                sliced_enough = True
                window_start = window_stop + datetime.timedelta(days=1)
            elif current_slice == 0:
                found_issues = search_project_daily_issues(key, kwargs['createdAfter'], sqenv, **kwargs)
                issues = issues + found_issues
                sliced_enough = True
                util.logger.error("Project key %s has many issues on %s, showing only the first %d",
                                  key, window_start, len(found_issues))
                window_start = window_stop + datetime.timedelta(days=1)
            else:
                sliced_enough = False
                current_slice = current_slice // 2
                util.logger.debug("Reslicing with a thinner slice of %d days", current_slice)

    util.logger.debug("For project %s, %d issues found", key, len(issues))
    return issues

def search_all_issues_unlimited(sqenv=None, **kwargs):
    import sonarqube.projects as projects
    if kwargs is None or 'componentKeys' not in kwargs:
        project_list = projects.get_projects_list(sqenv=sqenv)
    else:
        project_list= re.split(',', kwargs['componentKeys'])
    issues = []
    for project in project_list:
        issues = issues + projects.Project(key=project, sqenv=sqenv).get_all_issues()
    return issues

def apply_changelog(target_issue, source_issue):
    events = source_issue.get_all_events(True)

    if not events:
        util.logger.debug("Sibling has no changelog, no action taken")
        return

    util.logger.info("Applying changelog of issue %s to issue %s", source_issue.id, target_issue.id)
    for date in sorted(events):
        event = events[date]
        if is_event_a_severity_change(event):
            target_issue.set_severity(get_log_new_severity(event[1]))
        elif is_event_a_type_change(event):
            target_issue.set_type(get_log_new_type(event[1]))
        elif events[date][0] == 'log' and is_log_a_reopen(event[1]):
            target_issue.reopen()
        elif is_event_a_resolve_as_fp(event):
            target_issue.mark_as_false_positive()
        elif is_event_a_resolve_as_wf(event):
            target_issue.mark_as_wont_fix()
        elif is_event_a_resolve_as_reviewed(event):
            target_issue.mark_as_reviewed()
        elif is_event_an_assignment(event):
            target_issue.assign(get_log_assignee(event[1]))
        elif is_event_a_tag_change(event):
            target_issue.set_tags(get_log_new_tag(event[1]).replace(' ', ','))
        elif is_event_a_comment(event):
            target_issue.add_comment(event[1]['markdown'])
        else:
            util.logger.error("Event %s can't be applied", str(event))


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

def is_log_an_assignment(log):
    for diff in log['diffs']:
        if diff['key'] == 'assignee':
            return True
    return False

def is_log_a_reopen(log):
    cond1 = False
    cond2 = False
    for diff in log['diffs']:
        if diff['key'] == 'resolution':
            cond1 = True
        if diff['key'] == 'status' and 'newValue' in diff and diff['newValue'] == 'REOPENED':
            cond2 = True
    return cond1 and cond2

def is_log_a_reviewed(log):
    cond1 = False
    cond2 = False
    for diff in log['diffs']:
        if diff['key'] == 'resolution' and 'newValue' in diff and diff['newValue'] == 'FIXED':
            cond1 = True
        if diff['key'] == 'status' and 'newValue' in diff and diff['newValue'] == 'REVIEWED':
            cond2 = True
    return cond1 and cond2

def is_event_a_comment(event):
    return event[0] == 'comment'

def is_event_an_assignment(event):
    return event[0] == 'log' and is_log_an_assignment(event[1])

def is_event_a_resolve_as_fp(event):
    return event[0] == 'log' and is_log_a_resolve_as(event[1], 'FALSE-POSITIVE')

def is_event_a_resolve_as_wf(event):
    return event[0] == 'log' and is_log_a_resolve_as(event[1], 'WONTFIX')

def is_event_a_resolve_as_reviewed(event):
    return event[0] == 'log' and is_log_a_reviewed(event[1])

def log_change_type(log):
    return log['diffs'][0]['key']

def is_event_a_severity_change(event):
    return event[0] == 'log' and log_change_type(event[1]) == 'severity'

def is_event_a_type_change(event):
    return event[0] == 'log' and log_change_type(event[1]) == 'type'

def is_event_an_assignee_change(event):
    return event[0] == 'log' and log_change_type(event[1]) == 'assignee'

def is_event_a_tag_change(event):
    return event[0] == 'log' and log_change_type(event[1]) == 'tags'


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

def search_siblings(an_issue, issue_list, only_new_issues=True, check_component = False):
    siblings = []
    for issue in issue_list:
        if not issue.identical_to(an_issue, not check_component):
            continue
        if not only_new_issues or (only_new_issues and not issue.has_changelog()):
            # Add issue only if it has no change log, meaning it's brand new
            util.logger.debug("Adding issue %s to list", issue.get_url())
            siblings.append(issue)
    return siblings

def to_csv_header():
    return "# id;rule;type;severity;status;creation date;creation time;modification date;" + \
    "modification time;project key;project name;file;line;debt(min);message"

def get_issues_search_parms(parms):
    outparms = {}
    for key in parms:
        if parms[key] is not None and key in OPTIONS_ISSUES_SEARCH:
            outparms[key] = parms[key]
    return outparms
