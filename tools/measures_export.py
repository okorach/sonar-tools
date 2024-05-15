#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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
    Exports some measures of all projects
    - Either all measures (-m _all)
    - Or the main measures (-m _main)
    - Or a custom selection of measures (-m <measure1,measure2,measure3...>)
"""
import sys
from sonar import measures, metrics, platform, options, exceptions
from sonar.projects import projects
import sonar.utilities as util

RATINGS = "letters"
PERCENTS = "float"
DATEFMT = "datetime"
CONVERT_OPTIONS = {"ratings": "letters", "percents": "float", "dates": "datetime"}


def __last_analysis(project_or_branch):
    last_analysis = project_or_branch.last_analysis()
    with_time = True
    if CONVERT_OPTIONS["dates"] == "dateonly":
        with_time = False
    if last_analysis is None:
        last_analysis = "Never"
    else:
        last_analysis = util.date_to_string(last_analysis, with_time)
    return last_analysis


def __get_object_measures_history(obj: object, wanted_metrics: list[str], **kwargs) -> dict[str, str]:
    """Returns the measure history of an object (project, branch, application, portfolio)"""
    data = {}
    data["history"] = obj.get_measures_history(wanted_metrics)
    if kwargs[options.DATES_WITHOUT_TIME]:
        for item in data["history"]:
            item[0] = item[0].split("T")[0]
    data["url"] = obj.url()
    proj = obj
    if not isinstance(obj, projects.Project):
        proj = obj.concerned_object
        data["branch"] = obj.name
    data["projectKey"] = proj.key
    data["projectName"] = proj.name
    return data


def __get_json_measures_history(obj: object, wanted_metrics: list[str], **kwargs) -> dict[str, str]:
    """Returns the measure history of an object (project, branch, application, portfolio) as JSON"""
    d = __get_object_measures_history(obj, wanted_metrics, **kwargs)
    if not kwargs[options.WITH_URL]:
        d.pop("url", None)
    if not kwargs[options.WITH_BRANCHES]:
        d.pop("branch", None)
    return d


def __get_csv_measures_history(obj: object, wanted_metrics: list[str], **kwargs) -> str:
    """Returns a CSV list of measures history of an object, as CSV string"""
    data = __get_json_measures_history(obj, wanted_metrics, **kwargs)
    sep = kwargs[options.CSV_SEPARATOR]

    line = ""
    projkey = data["projectKey"]
    projname = data["projectName"]
    branch = data.get("branch", "")
    for m in data["history"]:
        if m[1] == "quality_gate_details":
            continue
        if CONVERT_OPTIONS["dates"] == "dateonly":
            m[0] = m[0].split("T")[0]
        line += projkey + sep + projname + sep
        if kwargs[options.WITH_BRANCHES]:
            line += branch + sep
        line += sep.join(m) + "\n"
    return line[:-1]


def __get_object_measures(obj, wanted_metrics):
    util.logger.info("Getting measures for %s", str(obj))
    measures_d = {k: v.value if v else None for k, v in obj.get_measures(wanted_metrics).items()}
    measures_d["lastAnalysis"] = __last_analysis(obj)
    measures_d["url"] = obj.url()
    measures_d.pop("quality_gate_details", None)
    proj = obj
    if not isinstance(obj, projects.Project):
        proj = obj.concerned_object
        measures_d["branch"] = obj.name
    measures_d["projectKey"] = proj.key
    measures_d["projectName"] = proj.name
    return measures_d


def __get_json_measures(obj, wanted_metrics, **kwargs):
    d = __get_object_measures(obj, wanted_metrics)
    if not kwargs[options.WITH_URL]:
        d.pop("url", None)
    if not kwargs[options.WITH_BRANCHES]:
        d.pop("branch", None)
    return d


def __get_csv_measures(obj, wanted_metrics, **kwargs):
    measures_d = __get_object_measures(obj, wanted_metrics)
    sep = kwargs[options.CSV_SEPARATOR]
    overall_metrics = "projectKey" + sep + "projectName"
    if kwargs[options.WITH_BRANCHES]:
        overall_metrics += sep + "branch"
    overall_metrics += sep + "lastAnalysis" + sep + util.list_to_csv(wanted_metrics)
    if kwargs[options.WITH_BRANCHES]:
        overall_metrics += sep + "url"
    line = ""
    for metric in util.csv_to_list(overall_metrics):
        val = ""
        if metric in measures_d and measures_d[metric] is not None:
            if isinstance(measures_d[metric], str) and sep in measures_d[metric]:
                val = util.quote(measures_d[metric], sep)
            else:
                val = str(measures.format(metric, measures_d[metric], **CONVERT_OPTIONS))
        line += val + sep
    return line[: -len(sep)]


def __get_wanted_metrics(args, endpoint):
    main_metrics = util.list_to_csv(metrics.MAIN_METRICS)
    wanted_metrics = args.metricKeys
    if wanted_metrics == "_all":
        all_metrics = metrics.search(endpoint).keys()
        # Hack: With SonarQube 7.9 and below new_development_cost measure can't be retrieved
        if endpoint.version() < (8, 0, 0):
            all_metrics.pop("new_development_cost")
        util.logger.info("Exporting %s metrics", len(all_metrics))
        wanted_metrics = main_metrics + "," + util.list_to_csv(set(all_metrics) - set(metrics.MAIN_METRICS))
    elif wanted_metrics == "_main" or wanted_metrics is None:
        wanted_metrics = main_metrics
    return util.csv_to_list(wanted_metrics)


def __get_fmt_and_file(args):
    kwargs = vars(args)
    fmt = kwargs["format"]
    fname = kwargs.get("file", None)
    if fname is not None:
        ext = fname.split(".")[-1].lower()
        if ext in ("csv", "json"):
            fmt = ext
    return (fmt, fname)


def __parse_args(desc):
    parser = util.set_common_args(desc)
    parser = util.set_key_arg(parser)
    parser = util.set_output_file_args(parser)
    parser.add_argument(
        "-m",
        "--metricKeys",
        required=False,
        help="Comma separated list of metrics or _all or _main",
    )
    parser.add_argument(
        "-b",
        "--" + options.WITH_BRANCHES,
        required=False,
        action="store_true",
        help="Also extract branches metrics",
    )
    parser.add_argument(
        "--withTags",
        required=False,
        action="store_true",
        help="Also extract project tags",
    )
    parser.set_defaults(withBranches=False, withTags=False)
    parser.add_argument(
        "-r",
        "--ratingsAsNumbers",
        action="store_true",
        default=False,
        required=False,
        help="Reports ratings as 12345 numbers instead of ABCDE letters",
    )
    parser.add_argument(
        "-p",
        "--percentsAsString",
        action="store_true",
        default=False,
        required=False,
        help="Reports percentages as string xy.z%% instead of float values 0.xyz",
    )
    parser.add_argument(
        "-d",
        f"--{options.DATES_WITHOUT_TIME}",
        action="store_true",
        default=False,
        required=False,
        help="Reports timestamps only with date, not time",
    )
    parser.add_argument(
        f"--{options.WITH_HISTORY}",
        action="store_true",
        default=False,
        required=False,
        help="Reports measures history not just last value",
    )
    parser.add_argument(
        "--" + options.WITH_URL,
        action="store_true",
        default=False,
        required=False,
        help="Add projects/branches URLs in report",
    )
    args = util.parse_and_check(parser)
    if args.ratingsAsNumbers:
        CONVERT_OPTIONS["ratings"] = "numbers"
    if args.percentsAsString:
        CONVERT_OPTIONS["percents"] = "percents"
    if args.datesWithoutTime:
        CONVERT_OPTIONS["dates"] = "dateonly"

    return args


def __write_measures_history_csv(file: str, args: object, obj_list: list[object], wanted_metrics: list[str]) -> None:
    """Writes measures history of object list in CSV format"""
    kwargs = vars(args)
    sep = kwargs[options.CSV_SEPARATOR]
    if not kwargs[options.WITH_BRANCHES]:
        header = f"# Project Key:1{sep}Project Name:2{sep}Last Analysis:3"
        i = 4
    else:
        header = "# Project Key:1{sep}Project Name:2{sep}Branch:3{sep}Last Analysis:4"
        i = 5
    for m in util.csv_to_list(wanted_metrics):
        header += f"{sep}{m}:{i}"
        i += 1
    if kwargs[options.WITH_URL]:
        header += f"{sep}URL:{i}"
    with util.open_file(file) as fd:
        print(header, file=fd)
        for obj in obj_list:
            print(__get_csv_measures_history(obj, wanted_metrics, **vars(args)), file=fd)


def __write_measures_history_json(file: str, args: object, obj_list: list[object], wanted_metrics: list[str]) -> None:
    """Bl"""
    is_first = True
    with util.open_file(file) as fd:
        print("[", end="", file=fd)
        for obj in obj_list:
            if not is_first:
                print(",", end="", file=fd)
            values = __get_json_measures_history(obj, wanted_metrics, **vars(args))
            json_str = util.json_dump(values)
            print(json_str, file=fd)
            is_first = False
        print("\n]\n", file=fd)


def __write_measures_json(file: str, args: object, obj_list: list[object], wanted_metrics: list[str]) -> None:
    """writes measures"""
    is_first = True
    with util.open_file(file) as fd:
        print("[", end="", file=fd)

        for obj in obj_list:
            if not is_first:
                print(",", end="", file=fd)
            json_str = util.json_dump(__get_json_measures(obj, wanted_metrics, **vars(args)))
            print(json_str, file=fd)
            is_first = False
        print("\n]\n", file=fd)


def __write_measures_csv(file: str, args: object, obj_list: list[object], wanted_metrics: list[str]) -> None:
    """writes measures in CSV"""
    kwargs = vars(args)
    sep = kwargs[options.CSV_SEPARATOR]
    with_br = kwargs[options.WITH_BRANCHES]
    base = f"# Project Key:1{sep}Project Name:2{sep}Date:3{sep}Metric:4{sep}Value:5"
    with util.open_file(file) as fd:
        if with_br:
            print(f"{base}{sep}Branch:6", file=fd)
        else:
            print(base, file=fd)
        for obj in obj_list:
            print(__get_csv_measures(obj, wanted_metrics, **vars(args)), file=fd)


def main():
    args = __parse_args("Extract measures of projects")
    endpoint = platform.Platform(
        some_url=args.url, some_token=args.token, org=args.organization, cert_file=args.clientCert, http_timeout=args.httpTimeout
    )

    with_branches = args.withBranches
    if endpoint.edition() == "community":
        with_branches = False

    wanted_metrics = __get_wanted_metrics(args, endpoint)
    (fmt, file) = __get_fmt_and_file(args)

    try:
        project_list = projects.get_list(endpoint=endpoint, key_list=args.projectKeys)
    except exceptions.ObjectNotFound as e:
        util.exit_fatal(e.message, options.ERR_NO_SUCH_KEY)
    obj_list = []
    if with_branches:
        for project in project_list.values():
            obj_list += project.branches().values()
    else:
        obj_list = project_list.values()
    nb_branches = len(obj_list)

    if endpoint.edition() == "community":
        args.withBranches = False
    if args.history:
        if fmt == "json":
            __write_measures_history_json(file, args, obj_list, wanted_metrics)
        else:
            __write_measures_history_csv(file, args, obj_list, wanted_metrics)
    else:
        if fmt == "json":
            __write_measures_json(file, args, obj_list, wanted_metrics)
        else:
            __write_measures_csv(file, args, obj_list, wanted_metrics)

        util.logger.info("%d PROJECTS %d branches", len(project_list), nb_branches)
        sys.exit(0)


if __name__ == "__main__":
    main()
