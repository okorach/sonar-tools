#!/usr/local/bin/python3
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
    This script exports issues as CSV

    Usage: issuesearch.py -t <SQ_TOKEN> -u <SQ_URL> [<filters>]

    Filters can be:
    [-k <projectKey>]
    [-s <statuses>] (FIXED, CLOSED, REOPENED, REVIEWED)
    [-r <resolutions>] (UNRESOLVED, FALSE-POSITIVE, WONTFIX)
    [-a <createdAfter>] issues created on or after a given date (YYYY-MM-DD)
    [-b <createdBefore>] issues created before or on a given date (YYYY-MM-DD)
    [--severities <severities>] Comma separated desired severities: BLOCKER, CRITICAL, MAJOR, MINOR, INFO
    [--types <types>] Comma separated issue types (VULNERABILITY,BUG,CODE_SMELL,HOTSPOT)
    [--tags]
'''
import sys
import json
from sonarqube import env, issues, hotspots, version, projects
import sonarqube.utilities as util

SEP = ','

def parse_args():
    parser = util.set_common_args('SonarQube issues extractor')
    parser = util.set_component_args(parser)
    parser.add_argument('-o', '--outputFile', required=False, help='File to generate the report, default is stdout'
                        'Format is automatically deducted from file extension, if extension given')
    parser.add_argument('-f', '--format', required=False, default='csv',
                        help='Format of output (json, csv), default is csv')
    parser.add_argument('-b', '--branches', required=False, default=None,
                        help='Comma separated list of branches to export. Use * to export findings from all branches. '
                             'If not specified, only findings of the main branch will be exported')
    parser.add_argument('-p', '--pullRequests', required=False, default=None,
                        help='Comma separated list of pull request. Use * to export findings from all PRs. '
                             'If not specified, only findings of the main branch will be exported')
    parser.add_argument('--statuses', required=False, help='comma separated issue status, '
                        'OPEN, WONTFIX, FALSE-POSITIVE, FIXED, CLOSED, REOPENED, REVIEWED')
    parser.add_argument('--createdAfter', required=False,
                        help='issues created on or after a given date (YYYY-MM-DD)')
    parser.add_argument('--createdBefore', required=False,
                        help='issues created on or before a given date (YYYY-MM-DD)')
    parser.add_argument('--resolutions', required=False,
                        help='Comma separated resolution states of the issues among'
                             'UNRESOLVED, FALSE-POSITIVE, WONTFIX')
    parser.add_argument('--severities', required=False,
                        help='Comma separated severities among BLOCKER, CRITICAL, MAJOR, MINOR, INFO')
    parser.add_argument('--types', required=False,
                        help='Comma separated issue types among CODE_SMELL, BUG, VULNERABILITY, HOTSPOT')
    parser.add_argument('--tags', help='Comma separated issue tags', required=False)
    parser.add_argument('--useFindings', required=False, default=False, action='store_true',
                        help='Use export_findings() whenever possible')
    parser.add_argument('--includeURLs', required=False, default=False, action='store_true',
                        help='Generate issues URL in the report, false by default')
    return util.parse_and_check_token(parser)

def __dump_issues(issues_list, file, file_format, with_urls=False):
    if file is None:
        f = sys.stdout
        util.logger.info("Dumping report to stdout")
    else:
        f = open(file, "w", encoding='utf-8')
        util.logger.info("Dumping report to file '%s'", file)
    if file_format == 'json':
        print("[", file=f)
    else:
        print(issues.to_csv_header(), file=f)
    is_first = True
    url = ''
    for _, issue in issues_list.items():
        if file_format == 'json':
            pfx = "" if is_first else ",\n"
            issue_json = issue.to_json()
            if not with_urls:
                issue_json.pop('url', None)
            print(pfx + json.dumps(issue_json, sort_keys=True, indent=3, separators=(',', ': ')), file=f, end='')
            is_first = False
        else:
            if with_urls:
                url = f'"{issue.url()}"{SEP}'
            print(f"{url}{issue.to_csv()}", file=f)

    if file_format == 'json':
        print("\n]", file=f)
    if file is not None:
        f.close()


def main():
    args = parse_args()
    sqenv = env.Environment(some_url=args.url, some_token=args.token)
    sqenv.set_env(args.url, args.token)
    kwargs = vars(args)
    util.check_environment(kwargs)
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)

    # Remove unset params from the dict
    params = vars(args)
    for p in params.copy():
        if params[p] is None:
            del params[p]

    # Add SQ environment
    params.update({'env': sqenv})
    all_issues = {}
    project_key = kwargs.get('componentKeys', None)
    branch_str = kwargs.get('branches', None)
    pr_str = kwargs.get('pullRequests', None)
    if project_key is not None:
        branches = []
        if branch_str == '*':
            project = projects.Project(project_key, sqenv)
            branches = project.get_branches()
        elif branch_str is not None:
            branches = [b.strip() for b in branch_str.split()]
        if pr_str == '*':
            project = projects.Project(project_key, sqenv)
            prs = project.get_pull_requests()
        elif pr_str is not None:
            prs = [p.strip() for p in pr_str.split()]
        if branches or prs:
            for b in branches:
                all_issues.update(issues.search_by_project(project_key, branch=b.name, endpoint=sqenv, search_findings=kwargs['useFindings']))
                if not kwargs['useFindings']:
                    all_issues.update(hotspots.search_by_project(project_key, sqenv, branch=b.name))
            for p in prs:
                all_issues.update(issues.search_by_project(project_key, pull_request=p.key, endpoint=sqenv, search_findings=kwargs['useFindings']))
                if not kwargs['useFindings']:
                    all_issues.update(hotspots.search_by_project(project_key, sqenv, pull_request=p.key))
        else:
            all_issues = issues.search_by_project(project_key, sqenv, search_findings=kwargs['useFindings'])
            if not kwargs['useFindings']:
                all_issues.update(hotspots.search_by_project(project_key, sqenv))
    else:
        all_issues = issues.search_by_project(project_key, sqenv, search_findings=kwargs['useFindings'])
        if not kwargs['useFindings']:
            all_issues.update(hotspots.search_by_project(project_key, sqenv))
    fmt = kwargs['format']
    if kwargs.get('outputFile', None) is not None:
        ext = kwargs['outputFile'].split('.')[-1].lower()
        if ext in ('csv', 'json'):
            fmt = ext
    __dump_issues(all_issues, kwargs.get('outputFile', None), fmt, with_urls=kwargs['includeURLs'])
    util.logger.info("Returned issues: %d", len(all_issues))
    sys.exit(0)


if __name__ == '__main__':
    main()
