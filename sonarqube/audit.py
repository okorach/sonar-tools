#!/usr/local/bin/python3
'''

    Audits a SonarQube platform

'''
import sys
import sonarqube.projects as projects
import sonarqube.qualityprofiles as qualityprofiles
import sonarqube.qualitygates as qualitygates
import sonarqube.utilities as util
import sonarqube.version as version
import sonarqube.env as env
import sonarqube.audit_problem as pb
import sonarqube.audit_config as conf


def __deduct_format__(fmt, file):
    if fmt is not None:
        return fmt
    if file is not None:
        ext = file.split('.').pop(-1).lower()
        if ext == 'csv' or ext == 'json':
            return ext
    return 'csv'


def main():
    util.set_logger('sonar-audit')
    parser = util.set_common_args('Deletes projects not analyzed since a given numbr of days')
    parser.add_argument('-w', '--what', required=False,
                        help='What to audit (qp,qg,settings,projects) comma separated, everything by default')
    parser.add_argument('--format', choices=['csv', 'json'], required=False,
                        help='''Output format for audit report
If not specified, it is the output file extension if json or csv, then csv by default''')
    parser.add_argument('-f', '--file', required=False, help='Output file for the report, stdout by default')
    args = parser.parse_args()
    sq = env.Environment(url=args.url, token=args.token)
    kwargs = vars(args)
    util.check_environment(kwargs)
    util.logger.info('sonar-tools version %s', version.SONAR_TOOLS_VERSION)
    settings = conf.load('sonar-audit.properties')

    if args.what is None:
        args.what = 'qp,qg,settings,projects'
    what_to_audit = args.what.split(',')

    problems = []
    if 'projects' in what_to_audit:
        problems += projects.audit(endpoint=sq, audit_settings=settings)
    if 'qp' in what_to_audit:
        problems += qualityprofiles.audit(endpoint=sq)
    if 'qg' in what_to_audit:
        problems += qualitygates.audit(endpoint=sq)
    if 'settings' in what_to_audit:
        problems += sq.audit(audit_settings=settings)

    args.format = __deduct_format__(args.format, args.file)
    pb.dump_report(problems, args.file, args.format)

    if problems:
        util.logger.warning("%d issues found during audit", len(problems))
    else:
        util.logger.info("%d issues found during audit", len(problems))
    sys.exit(len(problems))


if __name__ == "__main__":
    main()
