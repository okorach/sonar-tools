#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2022-2023 Olivier Korach
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
"""
    Exports LoC per projects
"""
import sys
import csv

from sonar import platform, portfolios, version, options
from sonar.projects import projects
import sonar.utilities as util


def __deduct_format(fmt, file):
    if fmt is not None:
        return fmt
    if file is not None:
        ext = file.split(".").pop(-1).lower()
        util.logger.debug("File extension = %s", ext)
        if ext == "json":
            return ext
    return "csv"


def __dump_csv(object_list, fd, **kwargs):
    writer = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])

    nb_loc, nb_objects = 0, 0
    arr = ["# Key", "ncloc"]
    if kwargs.get(options.WITH_NAME, False):
        arr.append("name")
    if kwargs.get(options.WITH_LAST_ANALYSIS, False):
        arr.append("lastAnalysis")
    if kwargs.get(options.WITH_URL, False):
        arr.append("URL")
    writer.writerow(arr)

    util.logger.info("%d objects with LoCs to export...", len(object_list))
    obj_type = None
    for o in object_list.values():
        if obj_type is None:
            obj_type = type(o).__name__.lower()
        loc = o.loc()
        arr = [o.key, o.loc()]
        if kwargs.get(options.WITH_NAME, False):
            arr.append(o.name)
        if kwargs.get(options.WITH_LAST_ANALYSIS, False):
            arr.append(o.last_analysis())
        if kwargs.get(options.WITH_URL, False):
            arr.append(o.url())
        writer.writerow(arr)
        nb_objects += 1
        nb_loc += loc

        if nb_objects % 50 == 0:
            util.logger.info("%d %ss and %d LoCs, still counting...", nb_objects, obj_type, nb_loc)

    util.logger.info("%d %ss and %d LoCs in total", len(object_list), obj_type, nb_loc)


def __dump_json(object_list, fd, **kwargs):
    nb_loc, nb_objects = 0, 0
    data = []
    util.logger.info("%d objects with LoCs to export...", len(object_list))
    obj_type = None
    for o in object_list.values():
        if obj_type is None:
            obj_type = type(o).__name__.lower()
        d = {"key": o.key, "ncloc": o.loc()}
        if kwargs.get(options.WITH_NAME, False):
            d["name"] = o.name
        if kwargs.get(options.WITH_LAST_ANALYSIS, False):
            d["lastAnalysis"] = util.date_to_string(o.last_analysis())
        if kwargs.get(options.WITH_URL, False):
            d["url"] = o.url()
        data.append(d)
        nb_objects += 1
        if nb_objects % 50 == 0:
            util.logger.info("%d %ss and %d LoCs, still counting...", nb_objects, str(obj_type), nb_loc)

    print(util.json_dump(data), file=fd)
    util.logger.info("%d %ss and %d LoCs in total", len(object_list), str(obj_type), nb_loc)


def __dump_loc(object_list, file, **kwargs):
    with util.open_file(file) as fd:
        if kwargs[options.FORMAT] == "json":
            __dump_json(object_list, fd, **kwargs)
        else:
            __dump_csv(object_list, fd, **kwargs)


def __parse_args(desc):
    parser = util.set_common_args(desc)
    parser = util.set_key_arg(parser)
    parser = util.set_output_file_args(parser)
    parser.add_argument(
        "-n",
        "--withName",
        required=False,
        default=False,
        action="store_true",
        help="Also list the project name on top of the project key",
    )
    parser.add_argument(
        "-a",
        "--" + options.WITH_LAST_ANALYSIS,
        required=False,
        default=False,
        action="store_true",
        help="Also list the last analysis date on top of nbr of LoC",
    )
    parser.add_argument(
        "--" + options.WITH_URL,
        required=False,
        default=False,
        action="store_true",
        help="Also list the URL of the objects",
    )
    parser.add_argument(
        "--portfolios",
        required=False,
        default=False,
        action="store_true",
        help="Export portfolios LoCs instead of projects",
    )
    parser.add_argument(
        "--topLevelOnly",
        required=False,
        default=False,
        action="store_true",
        help="Extracts only toplevel portfolios LoCs, not sub-portfolios",
    )
    args = util.parse_and_check_token(parser)
    util.check_environment(vars(args))
    util.check_token(args.token)
    util.logger.info("sonar-tools version %s", version.PACKAGE_VERSION)
    return args


def main():
    args = __parse_args("Extract projects or portfolios lines of code, as computed for the licence")
    endpoint = platform.Platform(some_url=args.url, some_token=args.token, cert_file=args.clientCert)
    kwargs = vars(args)
    ofile = kwargs.pop("file", None)
    args.format = __deduct_format(args.format, ofile)

    if args.portfolios:
        params = {}
        if args.topLevelOnly:
            params["qualifiers"] = "VW"
        objects_list = portfolios.search(endpoint, params=params)
    else:
        objects_list = projects.search(endpoint)
    __dump_loc(objects_list, ofile, **vars(args))
    sys.exit(0)


if __name__ == "__main__":
    main()
