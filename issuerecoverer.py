#!/usr/local/bin/python

# !/Library/Frameworks/Python.framework/Versions/3.6/bin/python3.6

import json, requests

root_url = 'http://localhost:9000/'
credentials = ('2a9e1ccb0a18f9626d2f90f5cdac391e6280f7d1', '')
project_key = 'issuelifecycle'


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
                    diffs[1]["oldValue"] == "FALSE-POSITIVE" or diffs[1]["oldValue"] == "WONTFIX") and diffs[0][
        "newValue"] == "FIXED":
        return True
    return False


def print_object(o):
    print(json.dumps(o, indent=3, sort_keys=True))


def get_changelog(issue_key):
    params = dict(format='json', issue=issue_key)
    resp = requests.get(url=root_url + 'api/issues/changelog', auth=credentials, params=params)
    data = json.loads(resp.text)
    return data['changelog']


def get_comments(issue_key):
    # print('Searching comments for issue key ', issue_key)
    params = dict(format='json', issues=issue_key, additionalFields='comments')
    resp = requests.get(url=root_url + 'api/issues/search', auth=credentials, params=params)
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

def print_change_log(issue_key):
    events_by_date = sort_changelog(get_changelog(issue_key))
    comments_by_date = sort_comments(get_comments(issue_key))
    for date in comments_by_date:
        events_by_date[date] = comments_by_date[date]

    for date in sorted(events_by_date):
        print(date, ':')
        print_object(events_by_date[date])


def apply_changelog(new_issue, closed_issue, do_it_really=True):
    events_by_date = sort_changelog(get_changelog(closed_issue))
    comments_by_date = sort_comments(get_comments(closed_issue))
    for date in comments_by_date:
        events_by_date[date] = comments_by_date[date]

    for date in sorted(events_by_date):
        print_object(events_by_date[date])
        if events_by_date[date][0] == 'log' and is_log_a_severity_change(events_by_date[date][1]):
            params = dict(issue=new_issue, severity=get_log_new_severity(events_by_date[date][1]))
            print('Changing severity to ', params['severity'])
            if do_it_really:
                resp = requests.post(url=root_url + 'api/issues/set_severity', auth=credentials, params=params)
        elif events_by_date[date][0] == 'log' and is_log_a_type_change(events_by_date[date][1]):
            params = dict(issue=new_issue, type=get_log_new_type(events_by_date[date][1]))
            print('Changing type to ', params['type'])
            if do_it_really:
                resp = requests.post(url=root_url + 'api/issues/set_type', auth=credentials, params=params)
        elif events_by_date[date][0] == 'log' and is_log_a_reopen(events_by_date[date][1]):
            params = dict(issue=new_issue, type='reopen')
            print('Reopening issue ')
            if do_it_really:
                resp = requests.post(url=root_url + 'api/issues/set_type', auth=credentials, params=params)
        elif events_by_date[date][0] == 'log' and is_log_a_resolve_as_fp(events_by_date[date][1]):
            params = dict(issue=new_issue, transition='falsepositive')
            print('Setting as False Positive')
            if do_it_really:
                resp = requests.post(url=root_url + 'api/issues/do_transition', auth=credentials, params=params)
        elif events_by_date[date][0] == 'log' and is_log_a_resolve_as_wf(events_by_date[date][1]):
            params = dict(issue=new_issue, transition='wontfix')
            print('Setting as wontfix')
            if do_it_really:
                resp = requests.post(url=root_url + 'api/issues/do_transition', auth=credentials, params=params)
        elif events_by_date[date][0] == 'comment' and is_log_a_comment(events_by_date[date][1]):
            params = dict(issue=new_issue, text=events_by_date[date][1]['markdown'])
            print('Adding comment', events_by_date[date][1]['markdown'])
            if do_it_really:
                resp = requests.post(url=root_url + 'api/issues/add_comment', auth=credentials, params=params)


def was_fp_or_wf(key):
    changelog = get_changelog(key)
    for log in changelog:
        if is_log_a_closed_fp(log) or is_log_a_closed_wf(log) or is_log_a_severity_change(log) or is_log_a_type_change(
                log):
            return True
    return False


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


def is_log_a_severity_change(log):
    return log['diffs'][0]['key'] == 'severity'


def is_log_a_type_change(log):
    return log['diffs'][0]['key'] == 'type'


def get_log_new_type(log):
    for diff in log['diffs']:
        if diff['key'] == 'type':
            return diff['newValue']
    return 'undefined'


def get_log_new_severity(log):
    for diff in log['diffs']:
        if diff['key'] == 'severity':
            return diff['newValue']
    return 'undefined'


def identical_attributes(o1, o2, key_list):
    for key in key_list:
        if o1[key] != o2[key]:
            return False
    return True


def search_siblings(closed_issue, issue_list, only_new_issues=True):
    siblings = []
    for iss in issue_list:
        if identical_attributes(closed_issue, iss, ['rule', 'component', 'message', 'debt']):
            if only_new_issues:
                if len(get_changelog(iss['key'])) == 0:
                    # Add issue only if it has no change log, meaning it's brand new
                    siblings.append(iss)
            else:
                siblings.append(iss)
    return siblings


def print_whole_issue(issue):
    print(json.dumps(issue, indent=4, sort_keys=True))


def print_issue(issue):
    for attr in ['rule', 'component', 'message', 'debt', 'author', 'key', 'status']:
        print (issue[attr], ',')
    print()


def parse_args():
    parser = argparse.ArgumentParser(
            description='Search for unexpectedly closed issues and recover their history in a corresponding new issue.')
    parser.add_argument('-p', '--projectKey', help='Project key of the project to search', required=True)
    parser.add_argument('-u', '--url', help='Root URL of the SonarQube server, default is http://localhost:9000',
                        required=False)

    args = parser.parse_args()

    project_key = args.projectKey

    if args.url != "":
        root_url = args.url


# ------------------------------------------------------------------------------

try:
    import argparse
except ImportError:
    if sys.version_info < (2, 7, 0):
        print("Error:")
        print("You are running an old version of python. Two options to fix the problem")
        print("  Option 1: Upgrade to python version >= 2.7")
        print("  Option 2: Install argparse library for the current python version")
        print("            See: https://pypi.python.org/pypi/argparse")

parse_args()

params = dict(ps='500', componentKeys=project_key, additionalFields='_all')
resp = requests.get(url=root_url + 'api/issues/search', auth=credentials, params=params)
data = json.loads(resp.text)

print("Number of issues:", data['paging']['total'])

all_issues = data['issues']
non_closed_issues = []
mistakenly_closed_issues = []

for issue in all_issues:
    print('----ISSUE-------------------------------------------------------------')
    print_object(issue)
    print('----CHANGELOG-------------')
    print_object(get_changelog(issue['key']))
    print('----------------------------------------------------------------------')
    if issue['status'] == 'CLOSED':
        if was_fp_or_wf(issue['key']):
            mistakenly_closed_issues.append(issue)
    else:
        non_closed_issues.append(issue)

print('----------------------------------------------------------------------')
print('        ', len(mistakenly_closed_issues), 'mistakenly closed issues')
print('----------------------------------------------------------------------')

for issue in mistakenly_closed_issues:
    print_issue(issue)
    print_change_log(issue['key'])
    siblings = search_siblings(issue, non_closed_issues)
    if len(siblings) > 0:
        print('   Found', len(siblings), 'SIBLING(S)')
        for sibling in siblings:
            print('  ')
            print_issue(sibling)
        if len(siblings) == 1:
            print('Applying changelog')
            apply_changelog(siblings[0]['key'], issue['key'], True)

    print('----------------------------------------------------------------------')
