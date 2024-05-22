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
import csv
from http import HTTPStatus
from requests.exceptions import HTTPError
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


def __get_json_measures_history(obj: object, wanted_metrics: list[str]) -> dict[str, str]:
    """Returns the measure history of an object (project, branch, application, portfolio)"""
    data = {}
    try:
        data["history"] = obj.get_measures_history(wanted_metrics)
    except HTTPError as e:
        util.logger.error("HTTP Error %s, measures history export of %s skipped", str(e), str(obj))
    return data


def __get_csv_measures_history(obj: object, wanted_metrics: list[str], **kwargs) -> str:
    """Returns a CSV list of measures history of an object, as CSV string"""
    data = __get_json_measures_history(obj, wanted_metrics, **kwargs)
    if len(data) == 0:
        return ""
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


def __empty_measures(obj: object, metrics_list: list[str], sep: str = ",") -> str:
    """Returns an empty CSV of measures"""
    line = ""
    for metric in metrics_list:
        val = ""
        if metric == "projectKey":
            if isinstance(obj, projects.Project):
                val = obj.key
            else:
                val = obj.concerned_object.key
        elif metric == "branch":
            val = obj.key
        elif metric == "url":
            val = obj.url()
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
    else:
        # Verify that requested metrics do exist
        m_list = util.csv_to_list(wanted_metrics)
        all_metrics = metrics.search(endpoint).keys()
        for m in m_list:
            if m not in all_metrics:
                util.exit_fatal(f"Requested metric key '{m}' does not exist", options.ERR_NO_SUCH_KEY)
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
    parser.add_argument(
        "--asTable",
        action="store_true",
        default=False,
        required=False,
        help="Report measures history as table, instead of <date>,<metric>,<measure>",
    )
    args = util.parse_and_check(parser)
    if args.ratingsAsNumbers:
        CONVERT_OPTIONS["ratings"] = "numbers"
    if args.percentsAsString:
        CONVERT_OPTIONS["percents"] = "percents"
    if args.datesWithoutTime:
        CONVERT_OPTIONS["dates"] = "dateonly"

    return args


def __get_ts(ts: str, **kwargs) -> str:
    """Return datetime or date only depending on cmd line options"""
    if kwargs[options.DATES_WITHOUT_TIME]:
        ts = ts.split("T")[0]
    return ts


def __write_measures_history_csv_as_table(file: str, wanted_metrics: list[str], data: dict[str, str], **kwargs) -> None:
    """Writes measures history of object list in CSV format"""

    header_list = ["projectKey", "date"]
    if kwargs[options.WITH_NAME]:
        header_list.append("projectName")
    if kwargs[options.WITH_BRANCHES]:
        header_list.append("branch")
    header_list.append("lastAnalysis")
    header_list += wanted_metrics
    if kwargs[options.WITH_URL]:
        header_list.append("url")

    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        csvwriter.writerow(header_list)
        for project_data in data:
            key = project_data["projectKey"]
            if kwargs[options.WITH_NAME]:
                name = project_data["projectName"]
            if kwargs[options.WITH_BRANCHES]:
                branch = project_data["branch"]
            if kwargs[options.WITH_BRANCHES]:
                url = project_data["url"]
            row = []
            hist_data = {}
            if "history" not in project_data:
                continue
            for h in project_data["history"]:
                ts = __get_ts(h[0], **kwargs)
                if ts not in hist_data:
                    hist_data[ts] = {"projectKey": key}
                    if kwargs[options.WITH_NAME]:
                        hist_data[ts]["projectName"] = name
                    if kwargs[options.WITH_BRANCHES]:
                        hist_data[ts]["branch"] = branch
                    if kwargs[options.WITH_BRANCHES]:
                        hist_data[ts]["url"] = url
                hist_data[ts].update({h[1]: h[2]})

            for ts, data in hist_data.items():
                row = [data["projectKey"], ts]
                for m in wanted_metrics:
                    row.append(data.get(m, ""))
                csvwriter.writerow(row)


def __write_measures_history_csv_as_list(file: str, wanted_metrics: list[str], data: dict[str, str], **kwargs) -> None:
    """Writes measures history of object list in CSV format"""

    header_list = ["timestamp", "projectKey"]
    if kwargs[options.WITH_BRANCHES]:
        header_list.append("branch")
    header_list += ["metric", "value"]
    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        csvwriter.writerow(header_list)
        for project_data in data:
            key = project_data["projectKey"]
            if "history" not in project_data:
                continue
            for metric_data in project_data["history"]:
                csvwriter.writerow([__get_ts(metric_data[0], **kwargs), key, metric_data[1], metric_data[2]])


def __write_measures_history_csv(file: str, wanted_metrics: list[str], data: dict[str, str], **kwargs) -> None:
    """Writes measures history of object list in CSV format"""
    if kwargs["asTable"]:
        __write_measures_history_csv_as_table(file, wanted_metrics, data, **kwargs)
    else:
        __write_measures_history_csv_as_list(file, wanted_metrics, data, **kwargs)


def __write_measures_csv(file: str, wanted_metrics: list[str], data: dict[str, str], **kwargs) -> None:
    """writes measures in CSV"""
    header_list = ["projectKey"]
    if kwargs[options.WITH_NAME]:
        header_list.append("projectName")
    if kwargs[options.WITH_BRANCHES]:
        header_list.append("branch")
    header_list.append("lastAnalysis")
    header_list += wanted_metrics
    if kwargs[options.WITH_URL]:
        header_list.append("url")
    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        csvwriter.writerow(header_list)
        for project_data in data:
            row = []
            for m in header_list:
                row.append(project_data.get(m, ""))
            csvwriter.writerow(row)


def __general_object_data(obj: object, **kwargs) -> dict[str, str]:
    """Return general project/branch data"""
    data = {}
    proj = obj
    if kwargs[options.WITH_BRANCHES] and not isinstance(obj, projects.Project):
        proj = obj.concerned_object
        data["branch"] = obj.key
    data["projectKey"] = proj.key
    if kwargs[options.WITH_URL]:
        data["url"] = obj.url()
    if kwargs[options.WITH_NAME]:
        data["projectName"] = proj.name
    return data


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

    kwargs = vars(args)
    kwargs[options.WITH_NAME] = True
    kwargs.pop("file", None)
    measure_list = []
    for obj in obj_list:
        data = __general_object_data(obj=obj, **kwargs)
        try:
            if args.history:
                data.update(__get_json_measures_history(obj, wanted_metrics))
            else:
                data.update(__get_object_measures(obj, wanted_metrics))
        except HTTPError as e:
            if e.response.status_code == HTTPStatus.FORBIDDEN:
                util.logger.error("Insufficient permission to retrieve measures of %s, export skipped for this object", str(obj))
            else:
                util.logger.error("HTTP Error %s while retrieving measures of %s, export skipped for this object", str(e), str(obj))
            continue
        util.logger.debug("COLLECTED = %s", util.json_dump(data))
        measure_list += [data]

    if fmt == "json":
        with util.open_file(file) as fd:
            print(util.json_dump(measure_list), file=fd)
    elif kwargs["history"]:
        __write_measures_history_csv(file, wanted_metrics, measure_list, **kwargs)
    else:
        __write_measures_csv(file=file, wanted_metrics=wanted_metrics, data=measure_list, **kwargs)

    if file:
        util.logger.info("File '%s' created", file)
    util.logger.info("%d PROJECTS %d branches", len(project_list), nb_branches)
    sys.exit(0)


if __name__ == "__main__":
    main()
