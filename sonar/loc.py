#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2022 Olivier Korach
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
    Exports LoC per projects
'''
import sys
import csv

from sonar import projects, portfolios, env, version, options
import sonar.utilities as util


def __deduct_format(fmt, file):
    if fmt is not None:
        return fmt
    if file is not None:
        ext = file.split('.').pop(-1).lower()
        util.logger.debug("File extension = %s", ext)
        if ext == 'json':
            return ext
    return 'csv'


def __open_file(file):
    if file is None:
        fd = sys.stdout
        util.logger.info("Dumping LoC report to stdout")
    else:
        fd = open(file, "w", encoding='utf-8', newline='')
        util.logger.info("Dumping LoC report to file '%s'", file)
    return fd


def __dump_csv(object_list, fd, **kwargs):
    writer = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])

    nb_loc = 0
    nb_objects = 0
    arr = ['# Key', 'ncloc']
    if kwargs.get(options.WITH_NAME, False):
        arr.append('name')
    if kwargs.get(options.WITH_LAST_ANALYSIS, False):
        arr.append('lastAnalysis')
    if kwargs.get(options.WITH_URL, False):
        arr.append('URL')
    writer.writerow(arr)

    util.logger.info("%d objects with LoCs to export...", len(object_list))
    for p in object_list.values():
        if nb_objects == 0:
            if isinstance(p, portfolios.Portfolio):
                obj_type = 'portfolio'
            else:
                obj_type = 'project'

        data = p.dump_data(**kwargs)
        arr = [data['key'], data['ncloc']]
        if kwargs.get(options.WITH_NAME, False):
            arr.append(data['name'])
        if kwargs.get(options.WITH_LAST_ANALYSIS, False):
            arr.append(data['lastAnalysis'])
        if kwargs.get(options.WITH_URL, False):
            arr.append(data['url'])
        writer.writerow(arr)
        nb_objects += 1
        nb_loc += p.ncloc()
        if nb_objects % 50 == 0:
            util.logger.info("%d %ss and %d LoCs, still counting...", nb_objects, obj_type, nb_loc)

    util.logger.info("%d %ss and %d LoCs in total", len(object_list), obj_type, nb_loc)


def __dump_json(object_list, fd, **kwargs):
    nb_loc = 0
    nb_objects = 0
    data = []
    util.logger.info("%d objects with LoCs to export...", len(object_list))
    for p in object_list.values():
        if nb_objects == 0:
            if isinstance(p, portfolios.Portfolio):
                obj_type = 'portfolio'
            else:
                obj_type = 'project'
        data.append(p.dump_data(**kwargs))
        nb_objects += 1
        nb_loc += p.ncloc()
        if nb_objects % 50 == 0:
            util.logger.info("%d %ss and %d LoCs, still counting...", nb_objects, str(obj_type), nb_loc)

    print(util.json_dump(data), file=fd)
    util.logger.info("%d %ss and %d LoCs in total", len(object_list), str(obj_type), nb_loc)


def __dump_loc(object_list, file, **kwargs):
    fd = __open_file(file)
    if kwargs[options.FORMAT] == 'json':
        __dump_json(object_list, fd, **kwargs)
    else:
        __dump_csv(object_list, fd, **kwargs)
    if file is not None:
        fd.close()


def main():
    parser = util.set_common_args('Extract projects lines of code, as computed for the licence')
    parser = util.set_component_args(parser)
    parser.add_argument('-n', '--withName', required=False, default=False, action='store_true',
                        help='Also list the project name on top of the project key')
    parser.add_argument('-a', '--' + options.WITH_LAST_ANALYSIS, required=False, default=False, action='store_true',
                        help='Also list the last analysis date on top of nbr of LoC')
    parser.add_argument('--' + options.WITH_URL, required=False, default=False, action='store_true',
                        help='Also list the URL of the objects')
    parser.add_argument('--portfolios', required=False, default=False, action='store_true',
                        help='Export portfolios LoCs instead of projects')
    parser.add_argument('--topLevelOnly', required=False, default=False, action='store_true',
                        help='Extracts only toplevel portfolios LoCs, not sub-portfolios')
    parser.add_argument('-o', '--outputFile', required=False, help='File to generate the report, default is stdout'
                        'Format is automatically deducted from file extension, if extension given')
    parser.add_argument('-f', '--' + options.FORMAT, required=False, default='csv',
                        help='Format of output (json, csv), default is csv')
    parser.add_argument('--' + options.CSV_SEPARATOR, required=False, default=util.CSV_SEPARATOR,
                        help=f'CSV separator (for CSV output), default {util.CSV_SEPARATOR}')
    args = util.parse_and_check_token(parser)
    endpoint = env.Environment(some_url=args.url, some_token=args.token)
    util.check_environment(vars(args))
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)
    args.format = __deduct_format(args.format, args.outputFile)

    if args.portfolios:
        params = {}
        if args.topLevelOnly:
            params['qualifiers'] = 'VW'
        objects_list = portfolios.search(endpoint=endpoint, params=params)
    else:
        objects_list = projects.search(endpoint=endpoint)
    __dump_loc(objects_list, args.outputFile, **vars(args))
    sys.exit(0)


if __name__ == '__main__':
    main()
