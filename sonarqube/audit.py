#!/usr/local/bin/python3
'''

    Audits a SonarQube platform

'''
import sys
import sonarqube.projects as projects
import sonarqube.qualityprofiles as qualityprofiles
import sonarqube.qualitygates as qualitygates
import sonarqube.utilities as util
import sonarqube.env as env


def main():
    parser = util.set_common_args('Deletes projects not analyzed since a given numbr of days')
    parser.add_argument('-w', '--what', required=False, help='What to audit settings,projects,qg,qp')
    args = parser.parse_args()
    sq = env.Environment(url=args.url, token=args.token)
    kwargs = vars(args)
    util.check_environment(kwargs)

    problems = []
    if args.what is None or 'projects' in args.what.split(','):
        problems += projects.audit(endpoint=sq)
    if args.what is None or 'qp' in args.what.split(','):
        problems += qualityprofiles.audit(endpoint=sq)
    if args.what is None or 'qg' in args.what.split(','):
        problems += qualitygates.audit(endpoint=sq)
    if args.what is None or 'settings' in args.what.split(','):
        problems += sq.audit()

    for p in problems:
        print("{}".format(str(p)))
    if problems:
        util.logger.warning("%d issues found during audit", len(problems))
    else:
        util.logger.info("%d issues found during audit", len(problems))
    sys.exit(len(problems))


if __name__ == "__main__":
    main()
