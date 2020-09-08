#
# sonar-tools
# Copyright (C) 2019-2020 Olivier Korach
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

def get_log_date(log):
    return log['creationDate']


def is_log_a_closed_resolved_as(log, old_value):
    cond1 = False
    cond2 = False

    for diff in log['diffs']:
        if diff['key'] == 'resolution' and 'newValue' in diff and diff['newValue'] == 'FIXED' and \
            'oldValue' in diff and diff['oldValue'] == old_value:
            cond1 = True
        if diff['key'] == 'status' and 'newValue' in diff and diff['newValue'] == 'CLOSED' and \
            'oldValue' in diff and diff['oldValue'] == 'RESOLVED':
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
    return event['event'] == 'comment'


def is_event_an_assignment(event):
    return event['event'] == 'assign'


def is_event_a_resolve_as_fp(event):
    return event['event'] == 'transition' and event['value'] == 'falsepositive'


def is_event_a_resolve_as_wf(event):
    return event['event'] == 'transition' and event['value'] == 'wontfix'


def is_event_a_resolve_as_reviewed(event):
    return False


def is_event_a_severity_change(event):
    return event['event'] == 'severity'


def is_event_a_reopen(event):
    return event['event'] == 'transition' and event['value'] == 'reopen'


def is_event_a_type_change(event):
    return event['event'] == 'type'


def is_event_an_assignee_change(event):
    return event['event'] == 'assign'


def is_event_a_tag_change(event):
    return event['event'] == 'tags'


def get_log_assignee(event):
    return event['value']


def get_log_new_severity(event):
    return event['value']


def get_log_new_type(event):
    return event['value']


def get_log_new_tag(event):
    return event['value']
