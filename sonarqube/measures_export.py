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
    Exports some measures of all projects
    - Either all measures (-m _all)
    - Or the main measures (-m _main)
    - Or a custom selection of measures (-m <measure1,measure2,measure3...>)
'''
import sys
import re
from sonarqube import measures, metrics, projects, env, version
import sonarqube.utilities as util

csv_sep = ","

def __diff(first, second):
    second = set(second)
    return [item for item in first if item not in second]

def __get_project_measures(project, wanted_metrics, endpoint, with_branches=True):
    if with_branches:
        branch_data = project.get_branches()
        lines = ''
        for branch in branch_data:
            lines += __get_branch_measures(branch, project, wanted_metrics, endpoint) + "\n"
        return lines[:-1]
    else:
        p_meas = measures.component(project.key, wanted_metrics, endpoint=endpoint)
        last_analysis = project.last_analysis_date()
        if last_analysis is None:
            last_analysis = "Never"
        else:
            last_analysis = util.date_to_string(last_analysis)
        line = "{1}{0}{2}{0}{3}".format(csv_sep, project.key, project.name, last_analysis)
        for metric in wanted_metrics.split(','):
            if metric in p_meas:
                line += csv_sep + p_meas[metric].replace(csv_sep, '|')
            else:
                line += csv_sep + "None"
    return line

def __get_branch_measures(branch, project, wanted_metrics, endpoint):
    p_meas = measures.component(project.key, wanted_metrics, branch=branch.name, endpoint=endpoint)
    last_analysis = branch.last_analysis_date()
    if last_analysis is None:
        last_analysis = "Never"
    else:
        last_analysis = util.date_to_string(last_analysis)
    line = "{1}{0}{2}{0}{3}{0}{4}".format(csv_sep, project.key, project.name, branch.name, last_analysis)
    for metric in wanted_metrics.split(','):
        if metric in p_meas:
            line += csv_sep + p_meas[metric].replace(csv_sep, '|')
        else:
            line += csv_sep + "None"
    return line


def main():
    parser = util.set_common_args('Extract measures of projects')
    parser = util.set_component_args(parser)
    parser.add_argument('-m', '--metricKeys', required=False, help='Comma separated list of metrics or _all or _main')
    parser.add_argument('-b', '--withBranches', required=False, action='store_true',
                        help='Also extract branches metrics')
    parser.add_argument('--withTags', required=False, action='store_true', help='Also extract project tags')
    parser.set_defaults(withBranches=False, withTags=False)
    parser.add_argument('-r', '--ratingsAsLetters', action='store_true', required=False,
                        help='Reports ratings as ABCDE letters instead of 12345 numbers')

    args = util.parse_and_check_token(parser)
    endpoint = env.Environment(url=args.url, token=args.token)

    with_branches = args.withBranches
    if endpoint.edition() == 'community':
        with_branches = False

    util.check_environment(vars(args))
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)

    # Mandatory script input parameters

    main_metrics = metrics.Metric.MAIN_METRICS
    main_metrics_list = main_metrics.split(',')

    wanted_metrics = args.metricKeys
    if wanted_metrics == '_all':
        all_metrics = metrics.as_csv(metrics.search(endpoint=endpoint).values()).split(',')
        wanted_metrics = main_metrics + ',' + ','.join(__diff(all_metrics, main_metrics_list))
    elif wanted_metrics == '_main' or wanted_metrics is None:
        wanted_metrics = main_metrics

    if endpoint.edition() == 'community':
        print("# Project Key%sProject Name%sLast Analysis" % (csv_sep, csv_sep), end=csv_sep)
    else:
        print("# Project Key%sProject Name%sBranch%sLast Analysis" % (csv_sep, csv_sep, csv_sep), end=csv_sep)

    metrics_list = re.split(',', wanted_metrics)
    for m in metrics_list:
        print("{0}".format(m), end=csv_sep)
    print('')

    filters = None
    if args.componentKeys is not None:
        filters = {'projects': args.componentKeys.replace(' ', '')}
    project_list = projects.search(endpoint=endpoint, params=filters)
    nb_branches = 0
    nb_loc = 0
    for _, project in project_list.items():
        print(__get_project_measures(project, wanted_metrics, endpoint, with_branches))
        nb_loc += project.ncloc()
        if with_branches:
            nb_branches += len(project.get_branches())
        else:
            nb_branches += 1
    util.logger.info("%d PROJECTS %d branches %d LoCs", len(project_list), nb_branches, nb_loc)
    sys.exit(0)


if __name__ == '__main__':
    main()
