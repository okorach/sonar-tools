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
import json
import re
from sonarqube import measures, metrics, projects, env, version
import sonarqube.utilities as util

SEP = ","
RATINGS = 'letters'
PERCENTS = 'float'
DATEFMT = 'datetime'
CONVERT_OPTIONS = {'ratings': 'letters', 'percents': 'float', 'dates': 'datetime'}

def __diff(first, second):
    second = set(second)
    return [item for item in first if item not in second]


def __last_analysis(project_or_branch):
    last_analysis = project_or_branch.last_analysis_date()
    with_time = True
    if CONVERT_OPTIONS['dates'] == 'dateonly':
        with_time = False
    if last_analysis is None:
        last_analysis = "Never"
    else:
        last_analysis = util.date_to_string(last_analysis, with_time)
    return last_analysis


def __open_output(file):
    if file is None:
        fd = sys.stdout
        util.logger.info("Dumping report to stdout")
    else:
        fd = open(file, "w", encoding='utf-8')
        util.logger.info("Dumping report to file '%s'", file)
    return fd


def __close_output(file, fd):
    if file is not None:
        fd.close()
        util.logger.info("File '%s' generated", file)


def __get_csv_header(wanted_metrics, edition):
    if edition == 'community':
        header = f"# Project Key{SEP}Project Name{SEP}Last Analysis{SEP}"
    else:
        header = f"# Project Key{SEP}Project Name{SEP}Branch{SEP}Last Analysis{SEP}"
    for m in re.split(',', wanted_metrics):
        header += f"{m}{SEP}"
    return header[:-1]


def __get_json_project_measures(project, wanted_metrics, endpoint, with_branches=True):
    data = []
    if with_branches:
        for branch in project.get_branches():
            data.append(__get_json_branch_measures(branch, project, wanted_metrics, endpoint))
    else:
        p_meas = measures.component(project.key, wanted_metrics, endpoint=endpoint)
        prj = {'last_analysis': __last_analysis(project),
               'projectKey': project.key, 'projectName': project.name}
        for metric in wanted_metrics.split(','):
            if metric in p_meas:
                prj[metric] = measures.convert(metric, p_meas[metric], **CONVERT_OPTIONS)
        data.append(prj)
    return data


def __get_project_measures(project, wanted_metrics, endpoint, with_branches=True):
    if with_branches:
        branch_data = project.get_branches()
        lines = ''
        for branch in branch_data:
            lines += __get_branch_measures(branch, project, wanted_metrics, endpoint) + "\n"
        return lines[:-1]
    else:
        p_meas = measures.component(project.key, wanted_metrics, endpoint=endpoint)
        last_analysis = __last_analysis(project)
        line = f"{project.key}{SEP}{project.name}{SEP}{last_analysis}"
        for metric in wanted_metrics.split(','):
            val = "None"
            if metric in p_meas:
                val = str(measures.convert(metric, p_meas[metric].replace(SEP, '|'), **CONVERT_OPTIONS))
            line += SEP + val
    return line


def __get_json_branch_measures(branch, project, wanted_metrics, endpoint):
    p_meas = measures.component(project.key, wanted_metrics, branch=branch.name, endpoint=endpoint)
    data = {'last_analysis': __last_analysis(branch),
            'projectKey': project.key, 'projectName': project.name, 'branch': branch.name}
    for metric in wanted_metrics.split(','):
        if metric in p_meas:
            data[metric] = measures.convert(metric, p_meas[metric], **CONVERT_OPTIONS)
    return data


def __get_branch_measures(branch, project, wanted_metrics, endpoint):
    p_meas = measures.component(project.key, wanted_metrics, branch=branch.name, endpoint=endpoint)
    line = f"{project.key}{SEP}{project.name}{SEP}{branch.name}{SEP}{__last_analysis(branch)}"
    for metric in wanted_metrics.split(','):
        if metric in p_meas:
            line += SEP + str(measures.convert(metric, p_meas[metric].replace(SEP, '|'), **CONVERT_OPTIONS))
        else:
            line += SEP + "None"
    return line


def __get_wanted_metrics(args, endpoint):
    main_metrics = ','.join(metrics.Metric.MAIN_METRICS)
    wanted_metrics = args.metricKeys
    if wanted_metrics == '_all':
        all_metrics = metrics.as_csv(metrics.search(endpoint=endpoint).values()).split(',')
        wanted_metrics = main_metrics + ',' + ','.join(__diff(all_metrics, metrics.Metric.MAIN_METRICS))
    elif wanted_metrics == '_main' or wanted_metrics is None:
        wanted_metrics = main_metrics
    return wanted_metrics


def __get_fmt_and_file(args):
    kwargs = vars(args)
    fmt = kwargs['format']
    file = kwargs.get('outputFile', None)
    if file is not None:
        ext = file.split('.')[-1].lower()
        if ext in ('csv', 'json'):
            fmt = ext
    return (fmt, file)


def __parse_cmd_line():
    parser = util.set_common_args('Extract measures of projects')
    parser = util.set_component_args(parser)
    parser.add_argument('-o', '--outputFile', required=False, help='File to generate the report, default is stdout'
                        'Format is automatically deducted from file extension, if extension given')
    parser.add_argument('-f', '--format', required=False, default='csv',
                        help='Format of output (json, csv), default is csv')
    parser.add_argument('-m', '--metricKeys', required=False, help='Comma separated list of metrics or _all or _main')
    parser.add_argument('-b', '--withBranches', required=False, action='store_true',
                        help='Also extract branches metrics')
    parser.add_argument('--withTags', required=False, action='store_true', help='Also extract project tags')
    parser.set_defaults(withBranches=False, withTags=False)
    parser.add_argument('-r', '--ratingsAsNumbers', action='store_true', default=False, required=False,
                        help='Reports ratings as 12345 numbers instead of ABCDE letters')
    parser.add_argument('-p', '--percentsAsString', action='store_true', default=False, required=False,
                        help='Reports percentages as string xy.z%% instead of float values 0.xyz')
    parser.add_argument('-d', '--datesWithoutTime', action='store_true', default=False, required=False,
                        help='Reports timestamps only with date, not time')
    args = util.parse_and_check_token(parser)
    util.check_environment(vars(args))
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)
    if args.ratingsAsNumbers:
        CONVERT_OPTIONS['ratings'] = 'numbers'
    if args.percentsAsString:
        CONVERT_OPTIONS['percents'] = 'percents'
    if args.datesWithoutTime:
        CONVERT_OPTIONS['dates'] = 'dateonly'

    return args


def main():
    args = __parse_cmd_line()
    endpoint = env.Environment(url=args.url, token=args.token)

    with_branches = args.withBranches
    if endpoint.edition() == 'community':
        with_branches = False

    wanted_metrics = __get_wanted_metrics(args, endpoint)
    (fmt, file) = __get_fmt_and_file(args)

    fd = __open_output(file)
    if fmt == 'json':
        print('[', end='', file=fd)
    else:
        print(__get_csv_header(wanted_metrics, endpoint.edition()), file=fd)

    filters = None
    if args.componentKeys is not None:
        filters = {'projects': args.componentKeys.replace(' ', '')}
    project_list = projects.search(endpoint=endpoint, params=filters)
    nb_branches, nb_loc = 0, 0
    is_first = True
    for _, project in project_list.items():
        util.logger.info('Exporting measures for %s', str(project))
        if fmt == 'json':
            if not is_first:
                print(',', end='', file=fd)
            values = __get_json_project_measures(project, wanted_metrics, endpoint, with_branches)
            json_str = json.dumps(values, indent=3, sort_keys=True, separators=(',', ': '))[1:-2]
            print(json_str, end='', file=fd)
            is_first = False
        else:
            print(__get_project_measures(project, wanted_metrics, endpoint, with_branches), file=fd)
        nb_loc += project.ncloc()
        if with_branches:
            nb_branches += len(project.get_branches())
        else:
            nb_branches += 1
    if fmt == 'json':
        print("\n]\n", file=fd)
    __close_output(file, fd)
    util.logger.info("%d PROJECTS %d branches %d LoCs", len(project_list), nb_branches, nb_loc)
    sys.exit(0)


if __name__ == '__main__':
    main()
