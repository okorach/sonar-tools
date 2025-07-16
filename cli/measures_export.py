#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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

from requests import RequestException
from sonar.util import types
from cli import options
import sonar.logging as log
from sonar import metrics, platform, exceptions, errcodes, version, measures
import sonar.utilities as util
import sonar.util.constants as c
from sonar.util import component_helper

TOOL_NAME = "sonar-measures"


def __get_measures_history(obj: object, wanted_metrics: types.KeyList, convert_options: dict[str, str]) -> dict[str, str]:
    """Returns the measure history of an object (project, branch, application, portfolio)"""
    try:
        data = obj.get_measures_history(wanted_metrics)
    except RequestException as e:
        log.error("Error while getting measures history for %s: %s", str(obj), e)
        return {}
    if data:
        ratings = convert_options.get("ratings", "letters")
        percents = convert_options.get("percents", "float")
        for m in data:
            m[2] = measures.format(obj.endpoint, m[1], m[2], ratings, percents)
    return obj.component_data() | {"history": data}


def __get_measures(obj: object, wanted_metrics: types.KeyList, convert_options: dict[str, str]) -> dict[str, str]:
    """Returns the list of requested measures of an object"""
    log.info("Getting measures for %s", str(obj))
    measures_d = obj.component_data() | obj.get_measures(wanted_metrics)
    measures_d.pop("quality_gate_details", None)
    ratings = convert_options.get("ratings", "letters")
    percents = convert_options.get("percents", "float")
    measures_d = {k: v.format(ratings, percents) if v else None for k, v in measures_d.items()}
    last_analysis = obj.last_analysis()
    measures_d["lastAnalysis"] = util.date_to_string(last_analysis, convert_options["dates"] != "dateonly") if last_analysis else "Never"
    if not convert_options.get(options.WITH_TAGS, False):
        return measures_d

    sep = "|" if convert_options[options.CSV_SEPARATOR] == "," else ","
    if obj.__class__.__name__ == "Branch":
        measures_d["tags"] = sep.join(obj.concerned_object.get_tags())
    else:
        measures_d["tags"] = sep.join(obj.get_tags())
    return measures_d


def __get_wanted_metrics(endpoint: platform.Platform, wanted_metrics: types.KeySet) -> types.KeyList:
    """Returns an ordered list of metrics based on CLI inputs"""
    main_metrics = list(metrics.MAIN_METRICS)
    if endpoint.version() >= c.ACCEPT_INTRO_VERSION:
        main_metrics += metrics.MAIN_METRICS_10
    if endpoint.edition() in (c.EE, c.DCE):
        if endpoint.version() >= (10, 0, 0):
            main_metrics += metrics.MAIN_METRICS_ENTERPRISE_10
        if endpoint.version() >= (2025, 3, 0):
            main_metrics += metrics.MAIN_METRICS_ENTERPRISE_2025_3
    if "_all" in wanted_metrics or "*" in wanted_metrics:
        all_metrics = list(metrics.search(endpoint).keys())
        all_metrics.remove("quality_gate_details")
        # Hack: With SonarQube 7.9 and below new_development_cost measure can't be retrieved
        if not endpoint.is_sonarcloud() and endpoint.version() < (8, 0, 0):
            all_metrics.remove("new_development_cost")
        wanted_metrics = main_metrics + sorted(set(all_metrics) - set(main_metrics))
    elif "_main" in wanted_metrics:
        wanted_metrics = main_metrics
    else:
        # Verify that requested metrics do exist
        non_existing_metrics = util.difference(list(wanted_metrics), metrics.search(endpoint).keys())
        if len(non_existing_metrics) > 0:
            miss = ",".join(non_existing_metrics)
            util.exit_fatal(f"Requested metric keys '{miss}' don't exist", errcodes.NO_SUCH_KEY)
    log.info("Exporting %s metrics", len(wanted_metrics))
    return list(dict.fromkeys(wanted_metrics))


def __parse_args(desc: str) -> object:
    """Set and parses CLI arguments"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("json", "csv"))
    parser.add_argument(
        f"-{options.METRIC_KEYS_SHORT}",
        f"--{options.METRIC_KEYS}",
        required=False,
        default="_main",
        help="Comma separated list of metrics or _all or _main",
    )
    options.add_branch_arg(parser)
    parser.add_argument(
        f"--{options.WITH_TAGS}",
        required=False,
        action="store_true",
        help="Also extract project or apps tags",
    )
    parser = options.add_component_type_arg(parser)
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
        f"--{options.WITH_HISTORY}",
        action="store_true",
        default=False,
        required=False,
        help="Reports measures history not just last value",
    )
    parser.add_argument(
        "--asTable",
        action="store_true",
        default=False,
        required=False,
        help="Report measures history as table, instead of <date>,<metric>,<measure>",
    )
    options.add_dateformat_arg(parser)
    options.add_url_arg(parser)
    args = options.parse_and_check(parser=parser, logger_name=TOOL_NAME)

    return args


def __get_ts(ts: str, **kwargs) -> str:
    """Return datetime or date only depending on cmd line options"""
    if kwargs[options.DATES_WITHOUT_TIME]:
        ts = ts.split("T")[0]
    return ts


def __write_measures_history_csv_as_table(file: str, wanted_metrics: types.KeyList, data: dict[str, str], **kwargs) -> None:
    """Writes measures history of object list in CSV format"""

    mapping = {options.WITH_NAME: "name", options.BRANCH_REGEXP: "branch", options.WITH_URL: "url"}
    fields = ["key", "date"] + [v for k, v in mapping.items() if kwargs[k]] + list(wanted_metrics)

    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        print("# ", file=fd, end="")
        csvwriter.writerow(fields)
        for obj_data in data:
            hist_data = {}
            if "history" not in obj_data:
                continue
            for ts, key, val in obj_data["history"]:
                ts = __get_ts(ts, **kwargs)
                if ts not in hist_data:
                    hist_data[ts] = {"date": ts} | {k: obj_data.get(k, "") for k in ("key", "name", "branch", "url")}
                hist_data[ts] |= {key: val}
            for _, d in sorted(hist_data.items()):
                csvwriter.writerow([d.get(i, "") for i in fields])


def __write_measures_history_csv_as_list(file: str, data: dict[str, str], **kwargs) -> None:
    """Writes measures history of object list in CSV format"""

    mapping = {options.WITH_NAME: "name", options.BRANCH_REGEXP: "branch"}
    header_list = ["timestamp", "key"] + [v for k, v in mapping.items() if kwargs[k]] + ["metric", "value"]
    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        print("# ", file=fd, end="")
        csvwriter.writerow(header_list)
        for component_data in data:
            if "history" not in component_data:
                continue
            constant_data = [component_data["key"]] + [component_data[v] for k, v in mapping.items() if kwargs[k]]
            for ts, key, val in component_data["history"]:
                csvwriter.writerow([__get_ts(ts, **kwargs)] + constant_data + [key, val])


def __write_measures_history_csv(file: str, wanted_metrics: types.KeyList, data: dict[str, str], **kwargs) -> None:
    """Writes measures history of object list in CSV format"""
    if kwargs["asTable"]:
        __write_measures_history_csv_as_table(file, wanted_metrics, data, **kwargs)
    else:
        __write_measures_history_csv_as_list(file, data, **kwargs)


def __write_measures_csv(file: str, wanted_metrics: types.KeyList, data: dict[str, str], **kwargs) -> None:
    """writes measures in CSV"""
    mapping = {options.WITH_NAME: "name", options.BRANCH_REGEXP: "branch", options.WITH_TAGS: "tags", options.WITH_URL: "url"}
    header_list = ["key", "type", "lastAnalysis"] + [v for k, v in mapping.items() if kwargs[k]] + list(wanted_metrics)
    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
        print("# ", file=fd, end="")
        csvwriter.writerow(header_list)
        for comp_data in data:
            csvwriter.writerow([comp_data.get(m, "") for m in header_list])


def __check_options_vs_edition(edition: str, params: dict[str, str]) -> dict[str, str]:
    """Checks and potentially modify params according to edition of the target platform"""
    if edition == c.CE and params[options.BRANCH_REGEXP]:
        util.exit_fatal("Branch parameter forbidden with Community Edition / Community Build", exit_code=errcodes.UNSUPPORTED_OPERATION)
    if edition in (c.CE, c.DE) and params[options.COMPONENT_TYPE] == "portfolio":
        log.warning("SonarQube Server instance is a %s edition, there are no portfolios", edition)
        util.exit_fatal("SonarQube Server instance is a %s edition, there are no portfolios", exit_code=errcodes.UNSUPPORTED_OPERATION)
    return params


def main() -> None:
    """Entry point for sonar-measures-export"""
    start_time = util.start_clock()
    try:
        kwargs = util.convert_args(__parse_args("Extract measures of projects, apps or portfolios"))
        kwargs["ratings"] = "numbers" if kwargs["ratingsAsNumbers"] else "letters"
        kwargs["percents"] = "percents" if kwargs["percentsAsString"] else "float"
        kwargs["dates"] = "dateonly" if kwargs["datesWithoutTime"] else "datetime"
        if kwargs[options.COMPONENT_TYPE] == "portfolios" and kwargs[options.WITH_TAGS]:
            util.exit_fatal(
                f"Portfolios have no tags, can't use option --{options.WITH_TAGS} with --{options.PORTFOLIOS}", exit_code=errcodes.ARGS_ERROR
            )
        endpoint = platform.Platform(**kwargs)
        endpoint.verify_connection()
        endpoint.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")

        wanted_metrics = __get_wanted_metrics(endpoint=endpoint, wanted_metrics=set(kwargs[options.METRIC_KEYS]))
        file = kwargs.pop(options.REPORT_FILE)
        fmt = util.deduct_format(kwargs[options.FORMAT], file)
        kwargs = __check_options_vs_edition(edition=endpoint.edition(), params=kwargs)
        kwargs[options.WITH_NAME] = True

        obj_list = component_helper.get_components(
            endpoint=endpoint,
            component_type=kwargs[options.COMPONENT_TYPE],
            key_regexp=kwargs[options.KEY_REGEXP],
            branch_regexp=kwargs[options.BRANCH_REGEXP],
        )
        if kwargs["history"]:
            measure_list = []
            for obj in obj_list:
                try:
                    measure_list.append(__get_measures_history(obj, wanted_metrics, kwargs))
                except Exception:
                    continue
            measure_list = [o for o in measure_list if o]
            if fmt == "json":
                with util.open_file(file) as fd:
                    print(util.json_dump(measure_list), file=fd)
            else:
                __write_measures_history_csv(file, wanted_metrics, measure_list, **kwargs)
        else:
            measure_list = [__get_measures(obj, wanted_metrics, kwargs) for obj in obj_list]
            measure_list = [o for o in measure_list if o]
            if fmt == "json":
                measure_list = [util.none_to_zero(m, "^.*(issues|violations)$") for m in measure_list]
                with util.open_file(file) as fd:
                    print(util.json_dump(measure_list), file=fd)
            else:
                __write_measures_csv(file=file, wanted_metrics=wanted_metrics, data=measure_list, **kwargs)

        if file:
            log.info("File '%s' created", file)
        nb_proj = len({obj.concerned_object if obj.concerned_object is not None else obj for obj in obj_list})
        nb_branches = len(obj_list)
        log.info("%d %s, %d branches exported from %s", nb_proj, kwargs[options.COMPONENT_TYPE], nb_branches, kwargs[options.URL])
    except (options.ArgumentsError, exceptions.ObjectNotFound) as e:
        util.exit_fatal(e.message, e.errcode)
    except exceptions.UnsupportedOperation as e:
        util.exit_fatal(e.message, errcodes.UNSUPPORTED_OPERATION)
    except (PermissionError, FileNotFoundError) as e:
        util.exit_fatal(f"OS error while writing LoCs: {e}", exit_code=errcodes.OS_ERROR)
    util.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
