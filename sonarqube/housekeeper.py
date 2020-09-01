#!/usr/local/bin/python3
'''

    Removes obsolete data from SonarQube platform
    Currently only projects not analyzed since a given number of days

'''
import sys
import sonarqube.env as env
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.version as version
import sonarqube.audit_problem as pb


def main():
    util.set_logger('sonar-housekeeper')
    parser = util.set_common_args('Deletes projects not analyzed since a given numbr of days')
    parser.add_argument('-o', '--olderThan', required=True, type=int,
                        help='Number of days since last analysis to delete file')
    args = parser.parse_args()
    sq = env.Environment(url=args.url, token=args.token)
    kwargs = vars(args)
    util.check_environment(kwargs)
    util.logger.info('sonar-tools version %s', version.SONAR_TOOLS_VERSION)

    if args.olderThan < 90:
        util.logger.error("Can't delete projects more recent than 90 days")
        sys.exit(1)

    settings = {
        'audit.projects.maxLastAnalysisAge': args.olderThan,
        'audit.projects.neverAnalyzed': False,
        'audit.projects.duplicates': False,
        'audit.projects.visibility': False,
        'audit.projects.permissions': False,
        'audit.projects.lastAnalysisDate': True
    }
    problems = projects.audit(endpoint=sq, audit_settings=settings)

    if not problems:
        util.logger.info("%d projects older than %d days found during audit", len(problems), args.olderThan)
        sys.exit(0)

    pb.dump_report(problems, file=None, file_format='csv')
    util.logger.warning("%d projects older than %d days found during audit", len(problems), args.olderThan)
    text = input('Please confirm deletion y/n [n] ')
    if text != 'y':
        sys.exit(1)
    total_loc = 0
    nb_proj = 0
    for p in problems:
        if p.concerned_object is not None and isinstance(p.concerned_object, projects.Project):
            loc = int(p.concerned_object.get_measure('ncloc'))

            util.logger.info("Deleting project '%s', %d LoC", p.concerned_object.key, loc)
            p.concerned_object.delete()
            total_loc += loc
            nb_proj += 1
    util.logger.info("%d projects and %d LoCs deleted", nb_proj, total_loc)
    sys.exit(len(problems))


if __name__ == "__main__":
    main()
