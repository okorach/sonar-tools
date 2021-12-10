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
    [--types <types>] Comma separated issue types (VULNERABILITY,BUG,CODE_SMELL)
    [--tags]
'''
import sys
from sonarqube import env, issues, version
import sonarqube.utilities as util


def parse_args():
    parser = util.set_common_args('SonarQube issues extractor')
    parser = util.set_component_args(parser)
    parser.add_argument('-s', '--statuses', required=False, help='comma separated issue status, \
        OPEN, WONTFIX, FALSE-POSITIVE, FIXED, CLOSED, REOPENED, REVIEWED')
    parser.add_argument('-a', '--createdAfter', required=False,
                        help='issues created on or after a given date (YYYY-MM-DD)')
    parser.add_argument('-b', '--createdBefore', required=False,
                        help='issues created on or before a given date (YYYY-MM-DD)')
    parser.add_argument('-r', '--resolutions', required=False,
                        help='Comma separated resolution states of the issues among'
                             'UNRESOLVED, FALSE-POSITIVE, WONTFIX')
    parser.add_argument('--severities', required=False,
                        help='Comma separated severities among BLOCKER, CRITICAL, MAJOR, MINOR, INFO')
    parser.add_argument('--types', required=False,
                        help='Comma separated issue types among CODE_SMELL, BUG, VULNERABILITY')
    parser.add_argument('--tags', help='Comma separated issue tags', required=False)

    return util.parse_and_check_token(parser)


def main():
    args = parse_args()
    sqenv = env.Environment(url=args.url, token=args.token)
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

    all_issues = issues.search_by_project(endpoint=sqenv, params=params, project_key=kwargs.get('componentKeys', None))
    print(issues.to_csv_header())
    for _, issue in all_issues.items():
        # util.logger.debug("ISSUE = %s", str(issue))
        print(issue.to_csv())
    util.logger.info("Returned issues: %d", len(all_issues))
    sys.exit(0)


if __name__ == '__main__':
    main()
