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


def __dump_report__(problems, file, file_format):

    if file is None:
        f = sys.stdout
        util.logger.info("Dumping report to stdout")
    else:
        f = open(file, "w")
        util.logger.info("Dumping report to file '%s'", file)
    if file_format == 'json':
        print("[", file=f)
    is_first = True
    for p in problems:
        if file_format is not None and file_format == 'json':
            pfx = '' if is_first else ','
            p_dump = pfx + p.to_json()
            is_first = False
        else:
            p_dump = p.to_csv()
        print(p_dump, file=f)

    if file_format == 'json':
        print("]", file=f)
    if file is not None:
        f.close()


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

    if args.what is None:
        args.what = 'qp,qg,settings,projects'
    what_to_audit = args.what.split(',')

    problems = []
    if 'projects' in what_to_audit:
        problems += projects.audit(endpoint=sq)
    if 'qp' in what_to_audit:
        problems += qualityprofiles.audit(endpoint=sq)
    if 'qg' in what_to_audit:
        problems += qualitygates.audit(endpoint=sq)
    if 'settings' in what_to_audit:
        problems += sq.audit()

    args.format = __deduct_format__(args.format, args.reportFile)
    __dump_report__(problems, args.reportFile, args.format)

    if problems:
        util.logger.warning("%d issues found during audit", len(problems))
    else:
        util.logger.info("%d issues found during audit", len(problems))
    sys.exit(len(problems))


if __name__ == "__main__":
    main()
