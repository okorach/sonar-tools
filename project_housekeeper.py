#!/usr/local/bin/python3
'''

    Deletes projects that has not been analyzed for a given amount of time

'''
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.env as env

parser = util.set_common_args('Deletes projects not analyzed since a given numbr of days')
parser.add_argument('-o', '--olderThan', required=True, help='Days since last analysis')
args = parser.parse_args()
kwargs = vars(args)
util.check_environment(kwargs)

olderThan = int(args.olderThan)
if olderThan < 90:
    util.logger.error("Can't delete projects more recent than 90 days")
    exit(1)

projects.delete_old_projects(days=olderThan, endpoint=env.Environment(url=args.url, token=args.token))
