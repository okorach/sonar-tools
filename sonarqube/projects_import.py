#!/usr/local/bin/python3
'''

    Imports a list of projects to a SonarQube platform

'''
import sys
import sonarqube.projects as projects
import sonarqube.utilities as util
import sonarqube.env as env


def main():
    parser = util.set_common_args('Imports a list of projects in a SonarQube platform')
    parser.add_argument('-f', '--projectsFile', required=True, help='File with the list of projects')

    args = parser.parse_args()
    myenv = env.Environment(url=args.url, token=args.token)
    util.check_environment(vars(args))

    f = open(args.projectsFile, "r")
    project_list = []
    for line in f:
        (key, status, _) = line.split(',', 2)
        if status is None or status != 'FAIL':
            project_list.append(key)
    f.close()

    nb_projects = len(project_list)
    util.logger.info("%d projects to import", nb_projects)
    i = 0
    statuses = {}
    for key in project_list:
        status = projects.create_project(key=key, sqenv=myenv)
        if status != 200:
            s = "CREATE {0}".format(status)
            if s in statuses:
                statuses[s] += 1
            else:
                statuses[s] = 1
        else:
            status = projects.Project(key, endpoint=myenv).importproject()
            s = "IMPORT {0}".format(status)
            if s in statuses:
                statuses[s] += 1
            else:
                statuses[s] = 1
        i += 1
        util.logger.info("%d/%d exports (%d%%) - Latest: %s - %s", i, nb_projects,
                         int(i * 100 / nb_projects), key, status)
        summary = ''
        for s in statuses:
            summary += "{0}:{1}, ".format(s, statuses[s])
        util.logger.info("%s", summary)
    sys.exit(0)


if __name__ == "__main__":
    main()
