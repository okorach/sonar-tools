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

    Abstraction of the SonarQube "issue" concept

'''
import re
import datetime
import json
from sonarqube import env, projects, users
import sonarqube.sqobject as sq
import sonarqube.utilities as util
import sonarqube.issue_changelog as changelog


SYNC_IGNORE_COMPONENTS = 'ignore_components'
SYNC_ADD_LINK = 'add_link'
SYNC_ADD_COMMENTS = 'add_comments'
SYNC_COMMENTS = 'sync_comments'
SYNC_ASSIGN = 'sync_assignments'
SYNC_SERVICE_ACCOUNTS = 'sync_service_accounts'

class ApiError(Exception):
    pass


class UnknownIssueError(ApiError):
    pass


class TooManyIssuesError(Exception):
    def __init__(self, nbr_issues, message):
        super().__init__()
        self.nbr_issues = nbr_issues
        self.message = message


class IssueComments:
    def __init__(self, json_data):
        self.json = json_data

    def sort(self):
        sorted_comment = {}
        for comment in self.json:
            sorted_comment[comment['createdAt']] = ('comment', comment)
        return sorted_comment

    def size(self):
        return len(self.json)

    def __str__(self):
        """Dumps the object in a string"""
        return json.dumps(self.json, sort_keys=True, indent=3, separators=(',', ': '))


class Issue(sq.SqObject):
    SEARCH_API = 'issues/search'
    MAX_PAGE_SIZE = 500
    MAX_SEARCH = 10000
    OPTIONS_SEARCH = ['additionalFields', 'asc', 'assigned', 'assignees', 'authors', 'componentKeys',
                      'createdAfter', 'createdAt', 'createdBefore', 'createdInLast', 'directories',
                      'facetMode', 'facets', 'files', 'branch', 'fileUuids',
                      'issues', 'languages', 'onComponentOnly', 'p', 'ps', 'resolutions', 'resolved',
                      'rules', 's', 'severities', 'sinceLeakPeriod', 'statuses', 'tags', 'types']

    def __init__(self, key, endpoint, data=None, from_findings=False):
        super().__init__(key, endpoint)
        self._url = None
        self._json = None
        self._severity = None
        self.type = None
        self.author = None
        self.assignee = None
        self.status = None
        self.resolution = None
        self.rule = None
        self.projectKey = None
        self.language = None
        self._changelog = None
        self._comments = []
        self.line = None
        self.component = None
        self.message = None
        self._debt = None
        self.creation_date = None
        self.modification_date = None
        self.hash = None
        self.branch = None
        if data is not None:
            if from_findings:
                self.__load_finding(data)
            else:
                self.__load(data)

    def __str__(self):
        return f"Issue key '{self.key}'"

    def __format__(self, format_spec=''):
        return f"Key: {self.key} - Type: {self.type} - Severity: {self._severity}" \
               f" - File/Line: {self.component}/{self.line} - Rule: {self.rule}"

    def to_string(self):
        """Dumps the object in a string"""
        return json.dumps(self._json, sort_keys=True, indent=3, separators=(',', ': '))

    def url(self):
        if self._url is None:
            branch = ''
            if self.branch is not None:
                branch = f'&branch={self.branch}'
            self._url = f'{self.endpoint.url}/project/issues?id={self.projectKey}{branch}&issues={self.key}'
        return self._url

    def __load(self, jsondata):
        self.__load_common(jsondata)
        self.author = jsondata['author']
        self.assignee = jsondata.get('assignee', None)
        self.projectKey = jsondata['project']
        self.creation_date = util.string_to_date(jsondata['creationDate'])
        self.modification_date = util.string_to_date(jsondata['updateDate'])
        self.component = jsondata['component']
        self.hash = jsondata.get('hash', None)
        self.branch = jsondata.get('branch', None)

    def __load_finding(self, jsondata):
        self.__load_common(jsondata)
        self.projectKey = jsondata['projectKey']
        self.creation_date = util.string_to_date(jsondata['createdAt'])
        self.modification_date = util.string_to_date(jsondata['updatedAt'])

    def __load_common(self, jsondata):
        self._json = jsondata
        self.type = jsondata['type']
        self._severity = jsondata.get('severity', None)
        self.line = jsondata.get('line', jsondata.get('lineNumber', None))
        self.resolution = jsondata.get('resolution', None)
        self.rule = jsondata.get('rule', jsondata.get('ruleReference', None))
        self.message = jsondata.get('message', None)
        self.status = jsondata['status']

    def debt(self):
        if self._debt is not None:
            return self._debt
        if 'debt' in self._json:
            debt = self._json['debt']
            m = re.search(r'(\d+)kd', debt)
            kdays = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)d', debt)
            days = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)h', debt)
            hours = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)min', debt)
            minutes = int(m.group(1)) if m else 0
            self._debt = ((kdays * 1000 + days) * 24 + hours) * 60 + minutes
        elif 'effort' in self._json:
            if self._json['effort'] == 'null':
                self._debt = 0
            else:
                self._debt = int(self._json['effort'])
        return self._debt

    def read(self):
        resp = self.get(Issue.SEARCH_API, params={'issues': self.key, 'additionalFields': '_all'})
        self.__load(resp.issues[0])

    def changelog(self, force_api=False):
        if (force_api or self._changelog is None):
            resp = self.get('issues/changelog', {'issue': self.key, 'format': 'json'})
            data = json.loads(resp.text)
            util.json_dump_debug(data['changelog'], "Issue Changelog = ")
            self._changelog = []
            for l in data['changelog']:
                d = changelog.diff_to_changelog(l['diffs'])
                util.logger.debug('Changelog %s', str(d))
                if d['event'] in ('merge', 'fork', 'unknown'):
                    # Skip automatic changelog events generated by SonarSource itself
                    continue
                self._changelog.append({'date': l['creationDate'], 'event': d['event'], 'value': d['value'],
                    'user': l['user'], 'userName': l['userName']})
        return self._changelog

    def has_changelog(self):
        util.logger.debug('Issue %s had %d changelog', self.key, len(self.changelog()))
        return len(self.changelog()) > 0

    def __has_sync_breaking_changelog(self, user_list):
        if user_list is None:
            return self.has_changelog()
        for c in self.modifiers():
            if c not in user_list:
                return True
        return False

    def comments(self):
        if 'comments' not in self._json:
            self._comments = []
        elif self._comments is None:
            self._comments = []
            util.json_dump_debug(self._json['comments'], "Issue Comments = ")
            for c in self._json['comments']:
                self._comments.append({'date': c['createdAt'], 'event': 'comment', 'value': c['markdown'],
                    'user': c['login'], 'userName': c['login']})
        return self._comments

    def has_comments(self):
        comments = self.comments()
        return len(comments) > 0

    def has_changelog_or_comments(self):
        return self.has_changelog() or self.has_comments()

    def add_comment(self, comment, really=True):
        util.logger.debug("Adding comment %s to issue %s", comment, self.key)
        if really:
            return self.post('issues/add_comment', {'issue': self.key, 'text': comment})
        else:
            return None

    def severity(self, force_api=False):
        if force_api or self._severity is None:
            self.read()
        return self._severity

    def set_severity(self, severity):
        """Sets severity"""
        util.logger.debug("Changing severity of issue %s from %s to %s", self.key, self._severity, severity)
        return self.post('issues/set_severity', {'issue': self.key, 'severity': severity})

    def assign(self, assignee):
        """Sets assignee"""
        util.logger.debug("Assigning issue %s to %s", self.key, assignee)
        return self.post('issues/assign', {'issue': self.key, 'assignee': assignee})

    def set_tags(self, tags):
        """Sets tags"""
        util.logger.debug("Setting tags %s to issue %s", tags, self.key)
        return self.post('issues/set_tags', {'issue': self.key, 'tags': tags})

    def set_type(self, new_type):
        """Sets type"""
        util.logger.debug("Changing type of issue %s from %s to %s", self.key, self.type, new_type)
        return self.post('issues/set_type', {'issue': self.key, 'type': new_type})

    def modifiers(self):
        '''Returns list of users that modified the issue'''
        return util.unique_dict_field(self.changelog(), 'user')

    def commenters(self):
        '''Returns list of users that commented the issue'''
        return util.unique_dict_field(self.comments(), 'user')

    def modifiers_excluding_service_users(self, service_users):
        mods = []
        for u in self.modifiers():
            if u not in service_users:
                mods.append(u)
        return mods

    def search_siblings(self, issue_list, allowed_users=None, ignore_component=False, **kwargs):
        exact_matches = []
        approx_matches = []
        match_but_modified = []
        for key, issue in issue_list.items():
            if key == self.key:
                continue
            if issue.strictly_identical_to(self, ignore_component, **kwargs):
                util.logger.debug("Issues %s and %s are strictly identical", self.key, key)
                if self.__has_sync_breaking_changelog(allowed_users):
                    match_but_modified.append(issue)
                else:
                    exact_matches.append(issue)
            elif issue.almost_identical_to(self, ignore_component, **kwargs):
                util.logger.debug("Issues %s and %s are almost identical", self.key, key)
                if self.__has_sync_breaking_changelog(allowed_users):
                    match_but_modified.append(issue)
                else:
                    approx_matches.append(issue)
            else:
                util.logger.debug("Issues %s and %s are not siblings", self.key, key)
        return (exact_matches, approx_matches, match_but_modified)

    def is_wont_fix(self):
        return self.__has_been_marked_as_statuses(["WONTFIX"])

    def is_false_positive(self):
        return self.__has_been_marked_as_statuses(["FALSE-POSITIVE"])

    def __has_been_marked_as_statuses(self, statuses):
        for log in self.changelog():
            for diff in log['diffs']:
                if diff["key"] != "resolution":
                    continue
                for status in statuses:
                    if diff["newValue"] == status:
                        return True
        return False

    def strictly_identical_to(self, another_issue, ignore_component=False):
        return (
            self.rule == another_issue.rule and
            self.hash == another_issue.hash and
            self.message == another_issue.message and
            self.debt() == another_issue.debt() and
            (self.component == another_issue.component or ignore_component)
        )

    def almost_identical_to(self, another_issue, ignore_component=False, **kwargs):
        if self.rule != another_issue.rule or self.hash != another_issue.hash:
            return False
        score = 0
        if self.message == another_issue.message or kwargs.get('ignore_message', False):
            score += 2
        if self.debt() == another_issue.debt() or kwargs.get('ignore_debt', False):
            score += 1
        if self.line == another_issue.line or kwargs.get('ignore_line', False):
            score += 1
        if self.component == another_issue.component or ignore_component:
            score += 1
        if self.author == another_issue.author or kwargs.get('ignore_author', False):
            score += 1
        if self.type == another_issue.type or kwargs.get('ignore_type', False):
            score += 1
        if self._severity == another_issue.severity or kwargs.get('ignore_severity', False):
            score += 1
        # Need at least 6 / 8 to match
        return score >= 6

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

    def __do_transition(self, transition):
        return self.post('issues/do_transition', {'issue': self.key, 'transition': transition})

    def reopen(self):
        util.logger.debug("Reopening %s", str(self))
        return self.__do_transition('reopen')

    def mark_as_false_positive(self):
        util.logger.debug("Marking %s as false positive", str(self))
        return self.__do_transition('falsepositive')

    def mark_as_wont_fix(self):
        util.logger.debug("Marking %s as won't fix", str(self))
        return self.__do_transition('wontfix')

    def mark_as_reviewed(self):
        if self.is_hotspot():
            util.logger.debug("Marking hotspot %s as reviewed", self.key)
            return self.__do_transition('resolveasreviewed')
        elif self.is_vulnerability():
            util.logger.debug("Marking vulnerability %s as won't fix in replacement of 'reviewed'", self.key)
            ret = self.__do_transition('wontfix')
            self.add_comment("Vulnerability marked as won't fix to replace hotspot 'reviewed' status")
            return ret

        util.logger.debug("Issue %s is neither a hotspot nor a vulnerability, cannot mark as reviewed", self.key)
        return False

    def to_csv(self):
        # id,project,rule,type,severity,status,creation,modification,project,file,line,debt,message
        cdate = self.creation_date.strftime(util.SQ_DATE_FORMAT)
        ctime = self.creation_date.strftime(util.SQ_TIME_FORMAT)
        mdate = self.modification_date.strftime(util.SQ_DATE_FORMAT)
        mtime = self.modification_date.strftime(util.SQ_TIME_FORMAT)
        # Strip timezone
        mtime = mtime.split('+')[0]
        msg = self.message.replace('"', '""').replace("\n", " ")
        line = '-' if self.line is None else self.line
        return ';'.join([str(x) for x in [self.key, self.rule, self.type, self._severity, self.status,
                                          cdate, ctime, mdate, mtime, self.projectKey,
                                          projects.get(self.projectKey, self.endpoint).name, self.component, line,
                                          self.debt(), '"' + msg + '"']])

    def to_json(self):
        # id,project,rule,type,severity,status,creation,modification,project,file,line,debt,message
        data = vars(self)

        for old_name, new_name in (('line', 'lineNumber'), ('rule', 'ruleReference')):
            data[new_name] = data.pop(old_name, None)
        data['effort'] = self.debt()
        data['url'] = self.url()
        data['createdAt'] = self.creation_date.strftime(util.SQ_DATETIME_FORMAT)
        data['updatedAt'] = self.modification_date.strftime(util.SQ_DATETIME_FORMAT)
        if self.component is not None:
            data['path'] = self.component.split(":")[-1]
        elif 'path' in self._json:
            data['path'] = self._json['path']
        else:
            util.logger.warning("Can't find file path for %s", str(self))
            data['path'] = 'Unknown'
        for field in ('endpoint', 'id', '_json', 'changelog', '_url', 'assignee', 'hash', 'sonarqube',
                      'creation_date', 'modification_date', '_debt', 'component', 'language', 'branch', 'resolution'):
            data.pop(field, None)
        return json.dumps(data, sort_keys=True, indent=3, separators=(',', ': '))

    def __apply_event(self, event, settings):
        util.logger.debug("Applying event %s", str(event))
        origin = f"originally by *{event['userName']}* on original branch"
        if changelog.is_event_a_severity_change(event):
            self.set_severity(changelog.get_log_new_severity(event))
            self.add_comment(f"Change of severity {origin}", settings[SYNC_ADD_COMMENTS])
        elif changelog.is_event_a_type_change(event):
            self.set_type(changelog.get_log_new_type(event))
            self.add_comment(f"Change of issue type {origin}", settings[SYNC_ADD_COMMENTS])
        elif changelog.is_event_a_reopen(event):
            self.reopen()
            self.add_comment(f"Issue re-open {origin}", settings[SYNC_ADD_COMMENTS])
        elif changelog.is_event_a_resolve_as_fp(event):
            self.mark_as_false_positive()
            self.add_comment(f"False positive {origin}", settings[SYNC_ADD_COMMENTS])
        elif changelog.is_event_a_resolve_as_wf(event):
            self.mark_as_wont_fix()
            self.add_comment(f"Won't fix {origin}", settings[SYNC_ADD_COMMENTS])
        elif changelog.is_event_a_resolve_as_reviewed(event):
            self.mark_as_reviewed()
            self.add_comment(f"Hotspot review {origin}")
        elif changelog.is_event_an_assignment(event):
            if settings[SYNC_ASSIGN]:
                u = users.get_login_from_name(event['value'], endpoint=self.endpoint)
                if u is None:
                    u = settings[SYNC_SERVICE_ACCOUNTS][0]
                self.assign(u)
                self.add_comment(f"Issue assigned {origin}", settings[SYNC_ADD_COMMENTS])
        elif changelog.is_event_a_tag_change(event):
            self.set_tags(event['value'].replace(' ', ','))
            self.add_comment(f"Tag change {origin}", settings[SYNC_ADD_COMMENTS])
        elif changelog.is_event_a_comment(event):
            self.add_comment(event['value'])
            self.add_comment("Above comment {origin}", settings[SYNC_ADD_COMMENTS])
        else:
            util.logger.error("Event %s can't be applied", str(event))
            return False
        return True

    def apply_changelog(self, source_issue, settings):
        events = source_issue.get_all_events(True)
        if events is None or not events:
            util.logger.debug("Sibling %s has no changelog, no action taken", source_issue.key)
            return False

        change_nbr = 0
        start_change = len(self._changelog) + 1
        util.logger.info("Applying changelog of issue %s to issue %s, from change %d",
                         source_issue.key, self.key, start_change)
        link_added = False
        for d in sorted(events.keys()):
            change_nbr += 1
            if change_nbr < start_change:
                util.logger.debug("Skipping change %s", str(events[d]))
                continue
            if not link_added:
                if settings[SYNC_ADD_LINK]:
                    self.add_comment(f"Automatically synchronized from [this original issue]({source_issue.url()})")
                link_added = True
            self.__apply_event(events[d], settings)
        return True

# ------------------------------- Static methods --------------------------------------

def __search_all_by_directories(params, endpoint=None):
    new_params = params.copy()
    facets = _get_facets(new_params['componentKeys'], facets='directories', params=new_params, endpoint=endpoint)
    issue_list = {}
    for d in facets['directories']:
        util.logger.info('Search by directory %s', d['val'])
        new_params['directories'] = d['val']
        issue_list.update(_search_all(new_params, endpoint, raise_error=False))
    return issue_list


def __search_all_by_types(params, endpoint=None):
    issue_list = {}
    new_params = params.copy()
    for issue_type in ('BUG', 'VULNERABILITY', 'CODE_SMELL'):
        try:
            util.logger.info('Search by type %s', issue_type)
            new_params['types'] = issue_type
            issue_list.update(_search_all(new_params, endpoint))
        except TooManyIssuesError:
            util.logger.info('Too many issues, recursing')
            issue_list.update(__search_all_by_directories(params=new_params, endpoint=endpoint))
    return issue_list


def __search_all_by_severities(params, endpoint=None):
    issue_list = {}
    new_params = params.copy()
    for sev in ('BLOCKER', 'CRITICAL', 'MAJOR', 'MINOR', 'INFO'):
        util.logger.info('Search by severity %s', sev)
        new_params['severities'] = sev
        try:
            issue_list.update(_search_all(params=new_params, endpoint=endpoint))
        except TooManyIssuesError:
            util.logger.info('Too many issues, recursing')
            issue_list.update(__search_all_by_types(params=new_params, endpoint=endpoint))
    util.logger.info('Total: %d for %s', len(issue_list), str(params))
    return issue_list


def __search_all_by_date(params, date_start=None, date_stop=None, endpoint=None):
    new_params = params.copy()
    if date_start is None:
        date_start = get_oldest_issue(endpoint=endpoint,
                                      params=new_params).replace(hour=0, minute=0, second=0, microsecond=0)
    if date_stop is None:
        date_stop = get_newest_issue(endpoint=endpoint,
                                     params=new_params).replace(hour=0, minute=0, second=0, microsecond=0)
    util.logger.info("Search by date between [%s - %s]",
        util.date_to_string(date_start, False), util.date_to_string(date_stop, False))
    issue_list = {}
    new_params.update({'createdAfter': date_start, 'createdBefore': date_stop})
    try:
        issue_list = _search_all(params=new_params, endpoint=endpoint)
    except TooManyIssuesError as e:
        util.logger.info("Too many issues (%d), splitting time window", e.nbr_issues)
        diff = (date_stop - date_start).days
        if diff == 0:
            util.logger.info('Too many issues, recursing')
            issue_list = __search_all_by_severities(new_params, endpoint=endpoint)
        elif diff == 1:
            issue_list.update(
                __search_all_by_date(new_params, date_start=date_start, date_stop=date_start, endpoint=endpoint))
            issue_list.update(
                __search_all_by_date(new_params, date_start=date_stop, date_stop=date_stop, endpoint=endpoint))
        else:
            date_middle = date_start + datetime.timedelta(days=diff//2)
            issue_list.update(
                __search_all_by_date(new_params, date_start=date_start, date_stop=date_middle, endpoint=endpoint))
            date_middle = date_middle + datetime.timedelta(days=1)
            issue_list.update(
                __search_all_by_date(new_params, date_start=date_middle, date_stop=date_stop, endpoint=endpoint))
    if date_start is not None and date_stop is not None:
        util.logger.debug("Project %s has %d issues between %s and %s", new_params['componentKeys'], len(issue_list),
                          util.date_to_string(date_start, False), util.date_to_string(date_stop, False))
    return issue_list


def _search_all_by_project(project_key, params, endpoint=None):
    if project_key is None:
        key_list = projects.search(endpoint).keys()
    else:
        key_list = project_key.split(',')
    issue_list = {}
    for k in key_list:
        params['componentKeys'] = k
        try:
            issue_list.update(_search_all(params, endpoint))
        except TooManyIssuesError:
            util.logger.info('Too many issues, recursing')
            issue_list.update(__search_all_by_date(params=params, endpoint=endpoint))
    return issue_list


def _search_all(params, endpoint=None, raise_error=True):
    new_params = params.copy()
    new_params['ps'] = Issue.MAX_PAGE_SIZE
    issue_list = {}
    p, nbr_pages = 1, 20
    util.logger.debug("Search all with %s", str(params))
    while p <= nbr_pages:
        new_params['p'] = p
        resp = env.get(Issue.SEARCH_API, params=new_params, ctxt=endpoint)
        data = json.loads(resp.text)
        for i in data['issues']:
            issue_list[i['key']] = Issue(key=i['key'], endpoint=endpoint, data=i)
        nbr_issues = data['paging']['total']
        #util.logger.info("nbr_issues = %d max = %d raise error = %s", nbr_issues, Issue.MAX_SEARCH, str(raise_error))
        if nbr_issues > Issue.MAX_SEARCH and raise_error:
            raise TooManyIssuesError(nbr_issues, f'{nbr_issues} issues returned by api/issues/search, '
                                     f'this is more than the max {Issue.MAX_SEARCH} possible')
        p += 1
    util.logger.info('Collected %d issues', len(issue_list))
    return issue_list


def search_by_project(project_key, endpoint=None, branch=None, params=None, search_findings=False):
    if params is None:
        params = {}
    if branch is not None:
        params['branch'] = branch
    if project_key is None:
        key_list = projects.search(endpoint).keys()
    else:
        key_list = project_key.split(',')
    issue_list = {}
    for k in key_list:
        util.logger.info("Issue search by project %s branch %s", k, str(branch))
        if endpoint.version() >= (9, 1, 0) and endpoint.edition() in ('enterprise', 'datacenter') and search_findings:
            util.logger.info('Using new export findings to speed up issue export')
            issue_list.update(projects.Project(k, endpoint).get_findings(branch))
            continue
        util.logger.info('Traditional issue search by project')
        issue_list.update(_search_all_by_project(k, params, endpoint=endpoint))
    return issue_list


def search(endpoint=None, page=None, params=None):
    if params is None:
        new_params = {}
    else:
        new_params = params.copy()
    new_params = __get_issues_search_params(new_params)
    util.logger.debug("Search params = %s", str(new_params))
    new_params['ps'] = Issue.MAX_PAGE_SIZE
    p = 1
    issue_list = {}
    while True:
        if page is None:
            new_params['p'] = p
        else:
            new_params['p'] = page
        resp = env.get(Issue.SEARCH_API, params=new_params, ctxt=endpoint)
        data = json.loads(resp.text)
        nbr_issues = data['paging']['total']
        nbr_pages = (nbr_issues + Issue.MAX_PAGE_SIZE-1) // Issue.MAX_PAGE_SIZE
        util.logger.debug("Number of issues: %d - Page: %d/%d", nbr_issues, new_params['p'], nbr_pages)
        if page is None and nbr_issues > Issue.MAX_SEARCH:
            raise TooManyIssuesError(nbr_issues,
                f'{nbr_issues} issues returned by api/{Issue.SEARCH_API}, '
                f'this is more than the max {Issue.MAX_SEARCH} possible')

        for i in data['issues']:
            issue_list[i['key']] = Issue(key=i['key'], endpoint=endpoint, data=i)
        if page is not None or p >= nbr_pages:
            break
        p += 1
    return issue_list


def search_all_issues(params=None, endpoint=None):
    util.logger.info('searching issues for %s', str(params))
    if params is None:
        params = {}
    params['ps'] = 500
    page = 1
    nbr_pages = 1
    issues = []
    while page <= nbr_pages and page <= 20:
        params['p'] = page
        returned_data = search(endpoint=endpoint, params=params)
        issues = issues + returned_data['issues']
        page = returned_data['page']
        nbr_pages = returned_data['pages']
        page = page + 1
    util.logger.debug("Total number of issues: %d", len(issues))
    return issues


def _get_facets(project_key, facets='directories', endpoint=None, params=None):
    if params is None:
        parms = {}
    else:
        parms = params.copy()
    parms['componentKeys'] = project_key
    parms['facets'] = facets
    parms['ps'] = 500
    parms = __get_issues_search_params(parms)
    resp = env.get(Issue.SEARCH_API, params=parms, ctxt=endpoint)
    data = json.loads(resp.text)
    util.json_dump_debug(data['facets'], 'FACETS = ')
    l = {}
    facets_list = facets.split(',')
    for f in data['facets']:
        if f['property'] in facets_list:
            l[f['property']] = f['values']
    return l


def __get_one_issue_date(endpoint=None, asc_sort='false', params=None):
    ''' Returns the date of one issue found '''
    if params is None:
        parms = {}
    else:
        parms = params.copy()
    parms['s'] = 'CREATION_DATE'
    parms['asc'] = asc_sort
    parms['ps'] = 1
    issue_list = search(endpoint=endpoint, page=1, params=parms)
    if not issue_list:
        return None
    for _, i in issue_list.items():
        date = i.creation_date
        util.logger.debug('Date: %s Issue %s', str(date), str(i))
        break
    return date


def get_oldest_issue(endpoint=None, params=None):
    ''' Returns the oldest date of all issues found '''
    return __get_one_issue_date(endpoint=endpoint, asc_sort='true', params=params)


def get_newest_issue(endpoint=None, params=None):
    ''' Returns the newest date of all issues found '''
    return __get_one_issue_date(endpoint=endpoint, asc_sort='false', params=params)


def _search_project_daily_issues(key, day, sqenv=None, **kwargs):
    util.logger.debug("Searching daily issues for project %s on day %s", key, day)
    kw = kwargs.copy()
    kw['componentKeys'] = key
    if kwargs is None or 'severities' not in kwargs:
        severities = {'INFO', 'MINOR', 'MAJOR', 'CRITICAL', 'BLOCKER'}
    else:
        severities = re.split(',', kwargs['severities'])
    util.logger.debug("Severities = %s", str(severities))
    if kwargs is None or 'types' not in kwargs:
        types = {'CODE_SMELL', 'VULNERABILITY', 'BUG', 'SECURITY_HOTSPOT'}
    else:
        types = re.split(',', kwargs['types'])
    util.logger.debug("Types = %s", str(types))
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


def count(endpoint=None, **kwargs):
    ''' Returns number of issues of a search '''
    returned_data = search(endpoint=endpoint, params=kwargs.copy().update({'ps': 1}))
    util.logger.debug("Issue search %s would return %d issues", str(kwargs), returned_data['total'])
    return returned_data['total']


def search_project_issues(key, sqenv=None, **kwargs):
    kwargs['componentKeys'] = key
    oldest = get_oldest_issue(endpoint=sqenv, **kwargs)
    if oldest is None:
        return []
    startdate = oldest
    enddate = get_newest_issue(endpoint=sqenv, **kwargs)

    nbr_issues = count(sqenv=sqenv, **kwargs)
    days_slice = abs((enddate - startdate).days)+1
    if nbr_issues > Issue.MAX_SEARCH:
        days_slice = (Issue.MAX_SEARCH * days_slice) // (nbr_issues * 4)
    util.logger.debug("For project %s, slicing by %d days, between %s and %s", key, days_slice, startdate, enddate)

    issues = []
    window_start = startdate
    while window_start <= enddate:
        current_slice = days_slice
        sliced_enough = False
        while not sliced_enough:
            window_size = datetime.timedelta(days=current_slice)
            kwargs['createdAfter'] = util.format_date(window_start)
            window_stop = window_start + window_size
            kwargs['createdBefore'] = util.format_date(window_stop)
            found_issues = search_all_issues(endpoint=sqenv, **kwargs)
            if len(found_issues) < Issue.MAX_SEARCH:
                issues = issues + found_issues
                util.logger.debug("Got %d issue, OK, go to next window", len(found_issues))
                sliced_enough = True
                window_start = window_stop + datetime.timedelta(days=1)
            elif current_slice == 0:
                found_issues = _search_project_daily_issues(key, kwargs['createdAfter'], sqenv, **kwargs)
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


def identical_attributes(o1, o2, key_list):
    for key in key_list:
        if o1[key] != o2[key]:
            return False
    return True


def to_csv_header():
    return "# id;rule;type;severity;status;creation date;creation time;modification date;" + \
           "modification time;project key;project name;file;line;debt(min);message"


def __get_issues_search_params(params):
    outparams = {'additionalFields': 'comments'}
    for key in params:
        if params[key] is not None and key in Issue.OPTIONS_SEARCH:
            outparams[key] = params[key]
    return outparams
