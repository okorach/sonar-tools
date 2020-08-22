#!/usr/local/bin/python3
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
import sonarqube.env as env
import sonarqube.issues as issues
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
                        help='''Comma separated resolution states of the issues,
                                  UNRESOLVED, FALSE-POSITIVE, WONTFIX''')
    parser.add_argument('--severities', required=False,
                        help='Comma separated severities, BLOCKER, CRITICAL, MAJOR, MINOR, INFO')
    parser.add_argument('--types', help='Comma separated issue types', required=False)
    parser.add_argument('--tags', help='Comma separated issue tags', required=False)

    return parser.parse_args()


def main():
    args = parse_args()
    sqenv = env.Environment(url=args.url, token=args.token)
    sqenv.set_env(args.url, args.token)
    kwargs = vars(args)
    util.check_environment(kwargs)

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
