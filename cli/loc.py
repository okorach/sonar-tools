#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2022-2025 Olivier Korach
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
import datetime
from requests import RequestException

from cli import options
import sonar.logging as log
from sonar import platform, portfolios, applications, projects, errcodes, exceptions, version
import sonar.utilities as util

TOOL_NAME = "sonar-loc"


def __get_csv_header_list(**kwargs) -> list[str]:
    """Returns CSV header"""
    arr = [f"# {kwargs[options.COMPONENT_TYPE][0:-1]} key"]
    if kwargs[options.WITH_BRANCHES]:
        arr.append("branch")
    arr.append("ncloc")
    if kwargs[options.WITH_NAME]:
        arr.append(f"{kwargs[options.COMPONENT_TYPE][0:-1]} name")
    if kwargs[options.WITH_LAST_ANALYSIS]:
        arr.append("last analysis")
    if kwargs[options.WITH_URL]:
        arr.append("URL")
    return arr


def __get_csv_row(o: object, **kwargs) -> tuple[list[str], str]:
    """Returns CSV row of object"""
    try:
        loc = o.loc()
    except (ConnectionError, RequestException) as e:
        util.handle_error(e, f"LoC export of {str(o)}, skipped", catch_all=True)
        loc = ""
    arr = [o.key, loc]
    obj_type = type(o).__name__.lower()
    if obj_type in ("branch", "applicationbranch"):
        arr = [o.concerned_object.key, o.name, loc]
    if kwargs[options.WITH_NAME]:
        proj_name = o.name
        if obj_type in ("branch", "applicationbranch"):
            proj_name = o.concerned_object.name
        arr.append(proj_name)
    if kwargs[options.WITH_LAST_ANALYSIS]:
        last_ana = ""
        if loc != "":
            last_ana = o.last_analysis()
        arr.append(last_ana)
    if kwargs[options.WITH_URL]:
        arr.append(o.url())
    return arr, loc


def __dump_csv(object_list: list[object], file: str, **kwargs) -> None:
    """Dumps LoC of passed list of objects (projects, branches or portfolios) as CSV"""

    if len(object_list) <= 0:
        log.warning("No objects with LoCs to dump, dump skipped")
        return
    obj_type = type(object_list[0]).__name__.lower()
    nb_loc, nb_objects = 0, 0
    with util.open_file(file) as fd:
        writer = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        writer.writerow(__get_csv_header_list(**kwargs))

        for o in object_list:
            arr, loc = __get_csv_row(o, **kwargs)
            writer.writerow(arr)
            nb_objects += 1
            if loc != "":
                log.debug("arr = %s", str(arr))
                nb_loc += loc
            if nb_objects % 50 != 0:
                continue
            if obj_type == "project":
                log.info("%d %ss and %d LoCs, still counting...", nb_objects, obj_type, nb_loc)
            else:
                log.info("%d %ss objects dumped, still working...", nb_objects, obj_type)
    if obj_type == "project":
        log.info("%d %ss and %d LoCs in total", len(object_list), obj_type, nb_loc)
    else:
        log.info("%d %ss objects dumped in total...", len(object_list), obj_type)


def __get_object_json_data(o: object, **kwargs) -> dict[str, str]:
    """Returns the object data as JSON"""
    obj_type = type(o).__name__.lower()
    parent_type = kwargs[options.COMPONENT_TYPE][0:-1]
    d = {parent_type: o.key, "ncloc": ""}
    if obj_type in ("branch", "applicationbranch"):
        d = {parent_type: o.concerned_object.key, "branch": o.name, "ncloc": ""}
    try:
        d["ncloc"] = o.loc()
    except (ConnectionError, RequestException) as e:
        util.handle_error(e, f"LoC export of {str(o)}, skipped", catch_all=True)
    if kwargs[options.WITH_NAME]:
        d[f"{parent_type}Name"] = o.name
        if obj_type in ("branch", "applicationbranch"):
            d[f"{parent_type}Name"] = o.concerned_object.name
    if kwargs[options.WITH_LAST_ANALYSIS]:
        d["lastAnalysis"] = ""
        if o.last_analysis() is not None:
            d["lastAnalysis"] = datetime.datetime.isoformat(o.last_analysis())
    if kwargs[options.WITH_URL]:
        d["url"] = o.url()
    return d


def __dump_json(object_list: list[object], file: str, **kwargs) -> None:
    """Dumps LoC of passed list of objects (projects, branches or portfolios) as JSON"""
    nb_loc, nb_objects = 0, 0
    data = []
    if len(object_list) <= 0:
        log.warning("No objects with LoCs to dump, dump skipped")
        return
    obj_type = type(object_list[0]).__name__.lower()
    # Collect all objects data
    for o in object_list:
        data.append(__get_object_json_data(o, **kwargs))
        nb_objects += 1
        if nb_objects % 50 != 0:
            continue
        if obj_type == "project":
            log.info("%d %ss and %d LoCs, still counting...", nb_objects, str(obj_type), nb_loc)
        else:
            log.info("%d %ss dumped, still counting...", nb_objects, str(obj_type))

    with util.open_file(file) as fd:
        print(util.json_dump(data), file=fd)
    if obj_type == "project":
        log.info("%d %ss and %d LoCs in total", len(object_list), str(obj_type), nb_loc)
    else:
        log.info("%d %ss dumped in total", len(object_list), str(obj_type))


def __dump_loc(object_list: list[object], file: str, **kwargs) -> None:
    """Dumps the LoC of collection of objects either in CSV or JSON format"""
    log.info("%d objects with LoCs to export, in format %s...", len(object_list), kwargs[options.FORMAT])
    if kwargs[options.FORMAT] == "json":
        __dump_json(object_list, file, **kwargs)
    else:
        __dump_csv(object_list, file, **kwargs)


def __parse_args(desc: str) -> object:
    """Defines and parses CLI arguments"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("json", "csv"))
    parser.add_argument(
        f"-{options.WITH_NAME_SHORT}",
        f"--{options.WITH_NAME}",
        required=False,
        default=False,
        action="store_true",
        help="Also list the project name on top of the project key",
    )
    parser.add_argument(
        f"-{options.WITH_LAST_ANALYSIS_SHORT}",
        f"--{options.WITH_LAST_ANALYSIS}",
        required=False,
        default=False,
        action="store_true",
        help="Also list the last analysis date on top of nbr of LoC",
    )
    options.add_url_arg(parser)
    options.add_branch_arg(parser)
    options.add_component_type_arg(parser)
    parser.add_argument(
        "--topLevelOnly",
        required=False,
        default=False,
        action="store_true",
        help="Extracts only toplevel portfolios LoCs, not sub-portfolios",
    )
    args = options.parse_and_check(parser=parser, logger_name=TOOL_NAME)
    return args


def __check_options(edition: str, kwargs: dict[str, str]) -> dict[str, str]:
    """Verifies a certain number of options for compatibility with edition"""
    kwargs[options.FORMAT] = util.deduct_format(kwargs[options.FORMAT], kwargs[options.REPORT_FILE])
    if kwargs[options.WITH_BRANCHES] and edition == "community":
        util.exit_fatal(f"No branches in {edition} edition, aborting...", errcodes.UNSUPPORTED_OPERATION)
    if kwargs[options.COMPONENT_TYPE] == "portfolios" and edition in ("community", "developer"):
        util.exit_fatal(f"No portfolios in {edition} edition, aborting...", errcodes.UNSUPPORTED_OPERATION)
    if kwargs[options.COMPONENT_TYPE] == "portfolios" and kwargs[options.WITH_BRANCHES]:
        log.warning("Portfolio LoC export selected, branch option is ignored")
        kwargs[options.WITH_BRANCHES] = False
    return kwargs


def main() -> None:
    """sonar-loc entry point"""
    start_time = util.start_clock()
    try:
        kwargs = util.convert_args(
            __parse_args("Extract projects, applications or portfolios lines of code - for projects LoC it is as computed for the license")
        )
        endpoint = platform.Platform(**kwargs)
        endpoint.verify_connection()
        endpoint.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")
    except (options.ArgumentsError, exceptions.ConnectionError) as e:
        util.exit_fatal(e.message, e.errcode)
    portfolios.Portfolio.CACHE.clear()
    applications.Application.CACHE.clear()
    projects.Project.CACHE.clear()

    kwargs = __check_options(endpoint.edition(), kwargs)

    try:
        if kwargs[options.COMPONENT_TYPE] == "portfolios":
            params = {}
            if kwargs["topLevelOnly"]:
                params["qualifiers"] = "VW"
            objects_list = list(portfolios.search(endpoint, params=params).values())
        elif kwargs[options.COMPONENT_TYPE] == "apps":
            objects_list = list(applications.search(endpoint).values())
        else:
            objects_list = list(projects.search(endpoint).values())

        if kwargs[options.WITH_BRANCHES]:
            branch_list = []
            for proj in objects_list:
                branch_list += proj.branches().values()
            objects_list = branch_list
        __dump_loc(objects_list, **kwargs)
    except exceptions.UnsupportedOperation as e:
        util.exit_fatal(err_msg=e.message, exit_code=errcodes.UNSUPPORTED_OPERATION)
    except (PermissionError, FileNotFoundError) as e:
        util.exit_fatal(f"OS error while writing LoCs: {e}", exit_code=errcodes.OS_ERROR)
    util.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
