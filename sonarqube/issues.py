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
import sonarqube.env as env
import sonarqube.sqobject as sq
import sonarqube.components as components
import sonarqube.utilities as util
import sonarqube.projects as projects
import sonarqube.issue_changelog as changelog


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
                      'facetMode', 'facets', 'files', 'branch',
                      'issues', 'languages', 'onComponentOnly', 'p', 'ps', 'resolutions', 'resolved',
                      'rules', 's', 'severities', 'sinceLeakPeriod', 'statuses', 'tags', 'types']

    def __init__(self, key, endpoint, data=None):
        super().__init__(key=key, env=endpoint)
        self.url = None
        self.json = None
        self.severity = None
        self.type = None
        self.author = None
        self.assignee = None
        self.status = None
        self.resolution = None
        self.rule = None
        self.projectKey = None
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
        self.branch = None
        if data is not None:
            self.__load__(data)

    def __str__(self):
        return "Key: {0} - Type: {1} - Severity: {2} - File/Line: {3}/{4} - Rule: {5}".format(
            self.key, self.type, self.severity, self.component, self.line, self.rule)

    def to_string(self):
        """Dumps the object in a string"""
        return json.dumps(self.json, sort_keys=True, indent=3, separators=(',', ': '))

    def get_url(self):
        if self.url is None:
            branch = ''
            if self.branch is not None:
                branch = 'branch={}&'.format(self.branch)
            self.url = '{}/project/issues?{}id={}&issues={}'.format(
                self.env.get_url(), branch, self.projectKey, self.key)
        return self.url

    def __load__(self, jsondata):
        self.json = jsondata
        self.id = jsondata['key']
        self.type = jsondata['type']
        if self.type != 'SECURITY_HOTSPOT':
            self.severity = jsondata['severity']

        self.author = jsondata['author']
        self.assignee = jsondata.get('assignee', None)
        self.status = jsondata['status']
        self.line = jsondata.get('line', None)

        self.resolution = jsondata.get('resolution', None)
        self.rule = jsondata['rule']
        self.projectKey = jsondata['project']
        self.language = None
        self.changelog = None
        self.creation_date = util.string_to_date(jsondata['creationDate'])
        self.modification_date = util.string_to_date(jsondata['updateDate'])

        self.component = jsondata['component']
        self.hash = jsondata.get('hash', None)
        self.message = jsondata.get('message', None)
        self.debt = jsondata.get('debt', None)
        self.branch = jsondata.get('branch', None)

    def read(self):
        resp = self.get(Issue.SEARCH_API, params={'issues': self.key, 'additionalFields': '_all'})
        self.__load__(resp.issues[0])

    def get_changelog(self, force_api = False):
        if (force_api or self.changelog is None):
            resp = self.get('issues/changelog', {'issue': self.key, 'format': 'json'})
            data = json.loads(resp.text)
            # util.json_dump_debug(data['changelog'], "Issue Changelog = ")
            self.changelog = []
            for l in data['changelog']:
                d = changelog.diff_to_changelog(l['diffs'])
                if d['event'] in ('merge', 'fork', 'unknown'):
                    # Skip automatic changelog events generated by SonarSource itself
                    continue
                self.changelog.append({'date': l['creationDate'], 'event': d['event'], 'value': d['value'],
                    'user': l['user'], 'userName': l['userName']})
        return self.changelog

    def has_changelog(self):
        util.logger.debug('Issue %s had %d changelog', self.key, len(self.get_changelog()))
        return len(self.get_changelog()) > 0

    def get_comments(self):
        if 'comments' not in self.json:
            self.comments = []
        elif self.comments is None:
            self.comments = []
            util.json_dump_debug(self.json['comments'], "Issue Comments = ")
            for c in self.json['comments']:
                self.comments.append({'date': c['createdAt'], 'event': 'comment', 'value': c['markdown'],
                    'user': c['login'], 'userName': c['login']})
        return self.comments

    def get_all_events(self, is_sorted=True):
        events = self.get_changelog()
        util.logger.debug('Get all events: Issue %s has %d changelog', self.key, len(events))
        comments = self.get_comments()
        util.logger.debug('Get all events: Issue %s has %d comments', self.key, len(comments))
        for c in comments:
            events.append(c)
        if not is_sorted:
            return events
        bydate = {}
        for e in events:
            bydate[e['date']] = e
        return bydate

    def has_comments(self):
        comments = self.get_comments()
        return len(comments) > 0

    def has_changelog_or_comments(self):
        return self.has_changelog() or self.has_comments()

    def add_comment(self, comment):
        util.logger.debug("Adding comment %s to issue %s", comment, self.key)
        return self.post('issues/add_comment', {'issue': self.key, 'text': comment})

    # def delete_comment(self, comment_id):

    # def edit_comment(self, comment_id, comment_str)

    def get_severity(self, force_api=False):
        if force_api or self.severity is None:
            self.read()
        return self.severity

    def set_severity(self, severity):
        """Sets severity"""
        util.logger.debug("Changing severity of issue %s from %s to %s", self.key, self.severity, severity)
        return self.post('issues/set_severity', {'issue': self.key, 'severity': severity})

    def assign(self, assignee):
        """Sets assignee"""
        util.logger.debug("Assigning issue %s to %s", self.key, assignee)
        return self.post('issues/assign', {'issue': self.key, 'assignee': assignee})

    def get_authors(self):
        """Gets authors from SCM"""

    def set_tags(self, tags):
        """Sets tags"""
        util.logger.debug("Setting tags %s to issue %s", tags, self.key)
        return self.post('issues/set_tags', {'issue': self.key, 'tags': tags})

    def get_tags(self):
        """Gets tags"""

    def set_type(self, new_type):
        """Sets type"""
        util.logger.debug("Changing type of issue %s from %s to %s", self.key, self.type, new_type)
        return self.post('issues/set_type', {'issue': self.key, 'type': new_type})

    def get_type(self):
        """Gets type"""

    def get_status(self):
        return self.status

    def search_siblings(self, issue_list, **kwargs):
        exact_matches = []
        approx_matches = []
        match_but_modified = []
        for key, issue in issue_list.items():
            if key == self.id:
                continue
            if issue.strictly_identical_to(self, **kwargs):
                if self.has_changelog():
                    match_but_modified.append(issue)
                else:
                    exact_matches.append(issue)
            elif issue.almost_identical_to(self, **kwargs):
                if issue.has_changelog():
                    match_but_modified.append(issue)
                else:
                    approx_matches.append(issue)
        return (exact_matches, approx_matches, match_but_modified)

    def is_wont_fix(self):
        return self.__has_been_marked_as_statuses__(["WONTFIX"])

    def is_false_positive(self):
        return self.__has_been_marked_as_statuses__(["FALSE-POSITIVE"])

    def __has_been_marked_as_statuses__(self, statuses):
        for log in self.get_changelog():
            for diff in log['diffs']:
                if diff["key"] != "resolution":
                    continue
                for status in statuses:
                    if diff["newValue"] == status:
                        return True
        return False

    def get_key(self):
        return self.key

    def same_general_attributes(self, another_issue):
        return (
            self.rule == another_issue.rule and
            self.hash == another_issue.hash and
            self.message == another_issue.message and
            self.debt == another_issue.debt
        )

    def strictly_identical_to(self, another_issue, **kwargs):
        return (
            self.rule == another_issue.rule and
            self.hash == another_issue.hash and
            self.message == another_issue.message and
            self.debt == another_issue.debt and
            (self.component == another_issue.component or kwargs.get('ignore_component', False))
        )

    def almost_identical_to(self, another_issue, **kwargs):
        if self.rule != another_issue.rule or self.hash != another_issue.hash:
            return False
        score = 0
        if self.message == another_issue.message or kwargs.get('ignore_message', False):
            score += 2
        if self.debt == another_issue.debt or kwargs.get('ignore_debt', False):
            score += 1
        if self.line == another_issue.line or kwargs.get('ignore_line', False):
            score += 1
        if self.component == another_issue.component or kwargs.get('ignore_component', False):
            score += 1
        if self.author == another_issue.author or kwargs.get('ignore_author', False):
            score += 1
        if self.type == another_issue.type or kwargs.get('ignore_type', False):
            score += 1
        if self.severity == another_issue.severity or kwargs.get('ignore_severity', False):
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

    def do_transition(self, transition):
        return self.post('issues/do_transition', {'issue': self.key, 'transition': transition})

    def reopen(self):
        util.logger.debug("Reopening issue %s", self.id)
        return self.do_transition('reopen')

    def mark_as_false_positive(self):
        util.logger.debug("Marking issue %s as false positive", self.key)
        return self.do_transition('falsepositive')

    def mark_as_wont_fix(self):
        util.logger.debug("Marking issue %s as won't fix", self.key)
        return self.do_transition('wontfix')

    def mark_as_reviewed(self):
        if self.is_hotspot():
            util.logger.debug("Marking hotspot %s as reviewed", self.key)
            return self.do_transition('resolveasreviewed')
        elif self.is_vulnerability():
            util.logger.debug("Marking vulnerability %s as won't fix in replacement of 'reviewed'", self.key)
            ret = self.do_transition('wontfix')
            self.add_comment("Vulnerability marked as won't fix to replace hotspot 'reviewed' status")
            return ret

        util.logger.debug("Issue %s is neither a hotspot nor a vulnerability, cannot mark as reviewed", self.key)
        return False

    def to_csv(self):
        # id,project,rule,type,severity,status,creation,modification,project,file,line,debt,message
        debt = 0
        if self.debt is not None:
            m = re.search(r'(\d+)kd', self.debt)
            kdays = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)d', self.debt)
            days = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)h', self.debt)
            hours = int(m.group(1)) if m else 0
            m = re.search(r'(\d+)min', self.debt)
            minutes = int(m.group(1)) if m else 0
            debt = ((kdays * 1000 + days) * 24 + hours) * 60 + minutes
        cdate = self.creation_date.strftime(util.SQ_DATE_FORMAT)
        ctime = self.creation_date.strftime(util.SQ_TIME_FORMAT)
        mdate = self.modification_date.strftime(util.SQ_DATE_FORMAT)
        mtime = self.modification_date.strftime(util.SQ_TIME_FORMAT)
        # Strip timezone
        mtime = re.sub(r"\+.*", "", mtime)
        msg = re.sub('"', '""', self.message)
        line = '-' if self.line is None else self.line
        return ';'.join([str(x) for x in [self.key, self.rule, self.type, self.severity, self.status,
                                          cdate, ctime, mdate, mtime, self.projectKey,
                                          projects.get(self.projectKey, self.env).name, self.component, line,
                                          debt, '"' + msg + '"']])

    def apply_changelog(self, source_issue):
        if self.has_changelog():
            util.logger.error("Can't apply changelog to an issue that already has a changelog")
            return False

        events = source_issue.get_all_events(True)

        if events is None or not events:
            util.logger.debug("Sibling %s has no changelog, no action taken", source_issue.key)
            return False

        util.logger.info("Applying changelog of issue %s to issue %s", source_issue.key, self.key)
        self.add_comment("Automatically synchronized from [this original issue]({0})".format(
            source_issue.get_url()))
        for d in sorted(events.keys()):
            event = events[d]
            util.logger.debug("Verifying event %s", str(event))
            if changelog.is_event_a_severity_change(event):
                self.set_severity(changelog.get_log_new_severity(event))
                self.add_comment("Change of severity originally by *{}* on original branch".format(event['userName']))
            elif changelog.is_event_a_type_change(event):
                self.set_type(changelog.get_log_new_type(event))
                self.add_comment("Change of issue type originally by *{}* on original branch".format(event['userName']))
            elif changelog.is_event_a_reopen(event):
                self.reopen()
                self.add_comment("Issue re-open originally by *{}* on original branch".format(event['userName']))
            elif changelog.is_event_a_resolve_as_fp(event):
                self.mark_as_false_positive()
                self.add_comment("False positive originally by *{}* on original branch".format(event['userName']))
            elif changelog.is_event_a_resolve_as_wf(event):
                self.mark_as_wont_fix()
                self.add_comment("Won't fix originally by *{}* on original branch".format(event['userName']))
            elif changelog.is_event_a_resolve_as_reviewed(event):
                self.mark_as_reviewed()
                self.add_comment("Hotspot review originally by *{}* on original branch".format(event['userName']))
            elif changelog.is_event_an_assignment(event):
                self.assign(event['value'])
                self.add_comment("Issue assigned originally by *{}* on original branch".format(event['userName']))
            elif changelog.is_event_a_tag_change(event):
                self.set_tags(event['value'].replace(' ', ','))
                self.add_comment("Tag change originally by *{}* on original branch".format(event['userName']))
            elif changelog.is_event_a_comment(event):
                self.add_comment(event['value'])
                self.add_comment("Above comment originally from *{}* on original branch".format(event['userName']))
            else:
                util.logger.error("Event %s can't be applied", str(event))
        return True

# ------------------------------- Static methods --------------------------------------
def check_fp_transition(diffs):
    util.logger.debug("----------------- DIFFS     -----------------")
    return diffs[0]['key'] == "resolution" and diffs[0]["newValue"] == "FIXED" and \
           (diffs[1]["oldValue"] == "FALSE-POSITIVE" or diffs[1]["oldValue"] == "WONTFIX")


def sort_comments(comments):
    sorted_comments = {}
    for comment in comments:
        sorted_comments[comment['createdAt']] = ('comment', comment)
    return sorted_comments


def search_by_file(root_key, file_uuid, params=None, endpoint=None):
    if params is None:
        parms = {}
    else:
        parms = params.copy()
    parms.pop('directories', None)
    parms['componentKeys'] = root_key
    util.logger.debug("Searching issues in file %s", file_uuid)
    parms['fileUuids'] = file_uuid
    issue_list = search(endpoint=endpoint, params=parms)
    util.logger.debug("File %s has %d issues", file_uuid, len(issue_list))
    return issue_list


def search_by_component(root_key, component=None, endpoint=None, params=None):
    if params is None:
        parms = {}
    else:
        parms = params.copy()
    dir_list = {}
    if component is None:
        dir_list = components.get_subcomponents(root_key, strategy='leaves', with_issues=True, endpoint=endpoint)
    else:
        dir_list[component.key] = component
    util.logger.debug("Found %d subcomponents", len(dir_list))
    issue_list = {}

    for key, comp in dir_list.items():
        util.logger.debug("Searching issues in sub-component %s", key)
        parms['componentKeys'] = key
        comp_issues = {}
        try:
            if comp.qualifier == 'DIR':
                comp_issues = search(endpoint=endpoint, params=parms)
            elif comp.qualifier == 'FIL':
                comp_issues = search_by_file(root_key=root_key, file_uuid=comp.id, endpoint=endpoint, params=parms)
            else:
                util.logger.error("Unexpected component qualifier %s in project %s", comp.qualifier, root_key)
        except TooManyIssuesError:
            if comp.qualifier == 'DIR':
                comp_issues = search_by_component(root_key=root_key, params=parms, endpoint=endpoint)
            else:
                util.logger.error("Project %s has more than 10K issues in a single file %s", root_key, comp.path)
        issue_list.update(comp_issues)
        util.logger.debug("Component %s has %d issues", key, len(comp_issues))

    return issue_list


def search_by_rule(root_key, rule, endpoint=None, params=None):
    if params is None:
        parms = {}
    else:
        parms = params.copy()
    parms['rules'] = rule
    util.logger.debug("Searching issues for rule %s", rule)
    issue_list = {}
    try:
        issue_list = search(endpoint=endpoint, params=parms)
    except TooManyIssuesError:
        file_facet = 'files'
        if endpoint.version() >= (8, 5, 0):
            file_facet = 'files'
        else:
            file_facet = 'fileUuids'
        facets = get_facets(facets=file_facet, project_key=parms['componentKeys'], endpoint=endpoint, params=parms)
        if len(facets) < 100:
            for f in facets:
                issue_list.update(search_by_file(root_key=root_key, file_uuid=f['val'],
                                                 endpoint=endpoint, params=parms))
    util.logger.debug("Rule %s has %d issues", rule, len(issue_list))
    return issue_list


def search_by_facet(project_key, facets='rules,files,severities,types', endpoint=None, params=None):
    if endpoint.version() < (8, 5, 0):
        facets = facets.replace('files', 'fileUuids')
    issue_list = {}
    selected_facet = None
    largest_facet = 0
    facets = get_facets(facets=facets, project_key=project_key, endpoint=endpoint, params=params)
    for key, facet in facets.items():
        if len(facet) > largest_facet and len(facet) < 100:
            selected_facet = key
            largest_facet = len(facet)
    if selected_facet is None:
        return None
    try:
        for f in facets[selected_facet]:
            if selected_facet == 'rules':
                issue_list.update(search_by_rule(root_key=project_key, rule=f['val'], endpoint=endpoint, params=params))
            elif selected_facet in ('fileUuids', 'files'):
                issue_list.update(search_by_file(root_key=project_key, file_uuid=f['val'],
                                                 endpoint=endpoint, params=params))
            else:
                # TODO search by severities/types
                return None
    except TooManyIssuesError:
        return None
    return issue_list


def search_by_date(date_start=None, date_stop=None, endpoint=None, params=None):
    if params is None:
        parms = {}
    else:
        parms = params.copy()
    if date_start is None:
        date_start = get_oldest_issue(endpoint=endpoint,
                                      params=parms).replace(hour=0, minute=0, second=0, microsecond=0)
    if date_stop is None:
        date_stop = get_newest_issue(endpoint=endpoint,
                                     params=parms).replace(hour=0, minute=0, second=0, microsecond=0)

    issue_list = {}
    parms.update({'createdAfter':date_start, 'createdBefore': date_stop})
    try:
        issue_list = search(endpoint=endpoint, params=params)
    except TooManyIssuesError:
        diff = (date_stop - date_start).days
        if diff == 0:
            l = search_by_facet(endpoint=endpoint, project_key=parms['componentKeys'], params=None)
            if l is None:
                l = search_by_component(root_key=parms['componentKeys'], endpoint=endpoint, params=parms)
            issue_list.update(l)
        elif diff == 1:
            issue_list.update(
                search_by_date(endpoint=endpoint, date_start=date_start, date_stop=date_start, params=parms))
            issue_list.update(
                search_by_date(endpoint=endpoint, date_start=date_stop, date_stop=date_stop, params=parms))
        else:
            date_middle = date_start + datetime.timedelta(days=diff//2)
            issue_list.update(
                search_by_date(endpoint=endpoint, date_start=date_start, date_stop=date_middle, params=parms))
            date_middle = date_middle + datetime.timedelta(days=1)
            issue_list.update(
                search_by_date(endpoint=endpoint, date_start=date_middle, date_stop=date_stop, params=parms))
    if date_start is not None and date_stop is not None:
        util.logger.debug("Project %s has %d issues between %s and %s", parms.get('componentKeys', 'None'),
                          len(issue_list), util.date_to_string(date_start), util.date_to_string(date_stop))
    return issue_list


def search_by_project(project_key, endpoint=None, params=None):
    if params is None:
        parms = {}
    else:
        parms = params.copy()
    branch = parms.get('branch', None)
    if branch is None:
        branch = 'MAIN'
    if project_key is None:
        key_list = projects.search(endpoint).keys()
    else:
        util.logger.info("Searching issues for project %s branch %s", project_key, branch)
        key_list = [project_key]
    issue_list = {}
    for k in key_list:
        parms['componentKeys'] = k
        try:
            project_issue_list = search(endpoint=endpoint, params=parms)
        except TooManyIssuesError:
            project_issue_list = search_by_date(endpoint=endpoint, params=parms)
        util.logger.info("Project %s branch %s has %d issues", k, branch, len(project_issue_list))
        issue_list.update(project_issue_list)
    return issue_list


def search(endpoint=None, page=None, params=None):
    if params is None:
        parms = {}
    else:
        parms = params.copy()
    parms = __get_issues_search_params__(parms)
    util.logger.debug("Search params = %s", str(parms))
    parms['ps'] = Issue.MAX_PAGE_SIZE
    p = 1
    issue_list = {}
    while True:
        if page is None:
            parms['p'] = p
        else:
            parms['p'] = page
        resp = env.get(Issue.SEARCH_API, params=parms, ctxt=endpoint)
        data = json.loads(resp.text)
        nbr_issues = data['total']
        nbr_pages = (nbr_issues + Issue.MAX_PAGE_SIZE-1) // Issue.MAX_PAGE_SIZE
        util.logger.debug("Number of issues: %d - Page: %d/%d", nbr_issues, parms['p'], nbr_pages)
        if page is None and nbr_issues > Issue.MAX_SEARCH:
            raise TooManyIssuesError(nbr_issues,
                                     '{} issues returned by api/{}, this is more than the max {} possible'.format(
                                         nbr_issues, Issue.SEARCH_API, Issue.MAX_SEARCH))

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
        #if returned_data['total'] > Issue.MAX_SEARCH and page == 20: NOSONAR
        #    raise TooManyIssuesError(returned_data['total'], \
        #          'Request found %d issues which is more than the maximum allowed %d' % \
        #          (returned_data['total'], Issue.MAX_SEARCH) NOSONAR
        page = returned_data['page']
        nbr_pages = returned_data['pages']
        page = page + 1
    util.logger.debug ("Total number of issues: %d", len(issues))
    return issues


def get_facets(project_key, facets='directories', endpoint=None, params=None):
    if params is None:
        parms = {}
    else:
        parms = params.copy()
    parms['componentKeys'] = project_key
    parms['facets'] = facets
    parms['ps'] = 500
    parms = __get_issues_search_params__(parms)
    resp = env.get(Issue.SEARCH_API, params=parms, ctxt=endpoint)
    data = json.loads(resp.text)
    util.json_dump_debug(data['facets'], 'FACETS = ')
    l = {}
    facets_list = facets.split(',')
    for f in data['facets']:
        if f['property'] in facets_list:
            l[f['property']] = f['values']
    return l


def __get_one_issue_date__(endpoint=None, asc_sort='false', params=None):
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
    return __get_one_issue_date__(endpoint=endpoint, asc_sort='true', params=params)


def get_newest_issue(endpoint=None, params=None):
    ''' Returns the newest date of all issues found '''
    return __get_one_issue_date__(endpoint=endpoint, asc_sort='false', params=params)


def get_number_of_issues(endpoint=None, **kwargs):
    ''' Returns number of issues of a search '''
    kwtemp = kwargs.copy()
    kwtemp['ps'] = 1
    returned_data = search(endpoint=endpoint, params=kwtemp)
    util.logger.debug("Project %s has %d issues", kwargs['componentKeys'], returned_data['total'])
    return returned_data['total']


def search_project_daily_issues(key, day, sqenv=None, **kwargs):
    util.logger.debug("Searching daily issues for project %s on day %s", key, day)
    kw = kwargs.copy()
    kw['componentKeys'] = key
    if kwargs is None or 'severities' not in kwargs:
        severities = {'INFO','MINOR','MAJOR','CRITICAL','BLOCKER'}
    else:
        severities = re.split(',', kwargs['severities'])
    util.logger.debug("Severities = %s", str(severities))
    if kwargs is None or 'types' not in kwargs:
        types = {'CODE_SMELL','VULNERABILITY','BUG','SECURITY_HOTSPOT'}
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


def count(endpoint=None, params=None):
    resp = env.get(Issue.SEARCH_API, params=params, ctxt=endpoint)
    data = resp.json_load(resp.text)
    return data['total']


def search_project_issues(key, sqenv=None, **kwargs):
    kwargs['componentKeys'] = key
    oldest = get_oldest_issue(endpoint=sqenv, **kwargs)
    if oldest is None:
        return []
    startdate = oldest
    enddate = get_newest_issue(endpoint=sqenv, **kwargs)

    nbr_issues = get_number_of_issues(sqenv=sqenv, **kwargs)
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
            kwargs['createdAfter']  = util.format_date(window_start)
            window_stop = window_start + window_size
            kwargs['createdBefore'] = util.format_date(window_stop)
            found_issues = search_all_issues(endpoint=sqenv, **kwargs)
            if len(found_issues) < Issue.MAX_SEARCH:
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


def identical_attributes(o1, o2, key_list):
    for key in key_list:
        if o1[key] != o2[key]:
            return False
    return True


def to_csv_header():
    return "# id;rule;type;severity;status;creation date;creation time;modification date;" + \
    "modification time;project key;project name;file;line;debt(min);message"


def __get_issues_search_params__(params):
    outparams = {'additionalFields':'comments'}
    for key in params:
        if params[key] is not None and key in Issue.OPTIONS_SEARCH:
            outparams[key] = params[key]
    return outparams
