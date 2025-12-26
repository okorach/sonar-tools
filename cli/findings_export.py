#!/usr/bin/env python3
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
"""Script that exports findings as CSV, JSON, or SARIF

Usage: sonar-findings-export.py -t <SQ_TOKEN> -u <SQ_URL> [<filters>]
"""

import os
import csv
from typing import TextIO
import concurrent.futures
from argparse import Namespace
import traceback

from cli import options
from sonar.util.types import ConfigSettings
import sonar.logging as log
from sonar import platform, exceptions, errcodes, version
from sonar import hotspots, findings
from sonar import applications, portfolios
from sonar.util import issue_defs as idefs, types, component_helper
import sonar.util.constants as c

import sonar.util.misc as util
import sonar.util.common_helper as chelp

TOOL_NAME = "sonar-findings"
DATES_WITHOUT_TIME = False

_SEARCH_CRITERIA = (
    options.BRANCHES,
    options.PULL_REQUESTS,
    options.STATUSES,
    options.DATE_AFTER,
    options.DATE_BEFORE,
    options.RESOLUTIONS,
    options.SEVERITIES,
    options.TYPES,
    options.TAGS,
    options.LANGUAGES,
)

SARIF_HEADER = """{
   "version": "2.1.0",
   "$schema": "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0-rtm.4.json",
   "runs": [
       {
          "tool": {
            "driver": {
                "name": "SonarQube",
                "informationUri": "https://www.sonarsource.com/products/sonarqube/"
            }
          },
          "results": [
"""

_OPTIONS_INCOMPATIBLE_WITH_USE_FINDINGS = (
    options.STATUSES,
    options.DATE_AFTER,
    options.DATE_BEFORE,
    options.RESOLUTIONS,
    options.SEVERITIES,
    options.TYPES,
    options.TAGS,
    options.LANGUAGES,
)

_SARIF_NO_CUSTOM_PROPERTIES = "sarifNoCustomProperties"


def parse_args(desc: str) -> Namespace:
    """Sets CLI parameters and parses them"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("csv", "json", "sarif"))
    parser = options.add_thread_arg(parser, "findings search")
    parser = options.add_component_type_arg(parser)
    parser = options.add_branch_arg(parser)
    parser.add_argument(
        f"-{options.PULL_REQUESTS_SHORT}",
        f"--{options.PULL_REQUESTS}",
        required=False,
        default=None,
        help="Comma separated list of pull requests to export. Use * to export findings from all PRs.",
    )
    parser.add_argument(
        f"--{options.STATUSES}",
        required=False,
        help="comma separated status among " + util.list_to_csv(idefs.STATUSES + hotspots.STATUSES),
    )
    parser.add_argument(
        f"--{options.DATE_AFTER}",
        required=False,
        help="findings created on or after a given date (YYYY-MM-DD)",
    )
    parser.add_argument(
        f"--{options.DATE_BEFORE}",
        required=False,
        help="findings created on or before a given date (YYYY-MM-DD)",
    )
    parser.add_argument(
        f"--{options.RESOLUTIONS}",
        required=False,
        help="Comma separated resolution of the findings among " + util.list_to_csv(idefs.RESOLUTIONS + hotspots.RESOLUTIONS),
    )
    parser.add_argument(
        f"--{options.SEVERITIES}",
        required=False,
        help="Comma separated severities among " + util.list_to_csv(idefs.STD_SEVERITIES + hotspots.SEVERITIES),
    )
    parser.add_argument(
        f"--{options.TYPES}",
        required=False,
        help="Comma separated types among " + util.list_to_csv(idefs.STD_TYPES + hotspots.TYPES),
    )
    parser.add_argument(f"--{options.TAGS}", help="Comma separated findings tags", required=False)
    parser.add_argument(
        f"--{options.USE_FINDINGS}", required=False, default=False, action="store_true", help="Use export_findings() whenever possible"
    )
    parser.add_argument(
        f"--{_SARIF_NO_CUSTOM_PROPERTIES}",
        required=False,
        default=False,
        action="store_true",
        help="For SARIF export, turn off Sonar custom findings properties, default is turned on",
    )
    options.add_url_arg(parser)
    options.add_dateformat_arg(parser)
    options.add_language_arg(parser, "findings")
    return options.parse_and_check(parser=parser, logger_name=TOOL_NAME)


def __write_header(file: str, endpoint: platform.Platform, **kwargs) -> None:
    """Writes the file header"""
    with util.open_file(file=file) as fd:
        if kwargs[options.FORMAT] == "sarif":
            print(SARIF_HEADER, file=fd)
        elif kwargs[options.FORMAT] == "json":
            print("[\n", file=fd)
        else:
            csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
            row = findings.to_csv_header(endpoint)
            row[0] = "# " + row[0]
            if kwargs[options.WITH_URL]:
                row.append("URL")
            csvwriter.writerow(row)


def __write_footer(file: str, fmt: str) -> None:
    """Writes the closing characters of export file depending on export format"""
    if fmt not in ("json", "sarif"):
        return
    with util.open_file(file=file, mode="a") as fd:
        closing_sequence = "\n]\n}\n]\n}" if fmt == "sarif" else "\n]"
        print(f"{closing_sequence}", file=fd)


def __write_json_findings(findings_list: dict[str, findings.Finding], fd: TextIO, **kwargs: str) -> None:
    """Appends a list of findings in JSON or SARIF format in a file"""
    log.debug("in write_json_findings")
    i = len(findings_list)
    comma = ","
    for finding in findings_list.values():
        if kwargs[options.FORMAT] == "json":
            json_data = finding.to_json(DATES_WITHOUT_TIME)
        else:
            json_data = finding.to_sarif(not kwargs.get(_SARIF_NO_CUSTOM_PROPERTIES, True))
        if not kwargs[options.WITH_URL]:
            json_data.pop("url", None)
        i -= 1
        if i == 0:
            comma = ""
        print(f"{util.json_dump(json_data, indent=1)}{comma}", file=fd)


def __write_csv_findings(findings_list: dict[str, findings.Finding], fd: TextIO, **kwargs: str) -> None:
    """Appends a list of findings in a CSV file"""
    csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR])
    for finding in findings_list.values():
        row = finding.to_csv()
        if kwargs[options.WITH_URL]:
            row.append(finding.url())
        csvwriter.writerow(row)


def __write_findings(findings_list: dict[str, findings.Finding], file: str, is_first: bool, **kwargs: str) -> None:
    """Writes a list of findings in a file"""
    log.info("Writing %d more findings in format %s", len(findings_list), kwargs[options.FORMAT])
    with util.open_file(file=file, mode="a") as fd:
        if kwargs[options.FORMAT] in ("sarif", "json"):
            if not is_first:
                print(",", file=fd)
            __write_json_findings(findings_list=findings_list, fd=fd, **kwargs)
        else:
            __write_csv_findings(findings_list=findings_list, fd=fd, **kwargs)


def __verify_inputs(params: types.ApiParams) -> bool:
    """Verifies if findings-export inputs are correct"""
    errcode = errcodes.WRONG_SEARCH_CRITERIA
    diff = list(set(util.csv_to_list(params.get(options.RESOLUTIONS))) - set(idefs.RESOLUTIONS + hotspots.RESOLUTIONS))
    if diff:
        chelp.clear_cache_and_exit(errcode, f"Resolutions {diff} are not legit resolutions")

    diff = list(set(util.csv_to_list(params.get(options.STATUSES))) - set(idefs.STATUSES + hotspots.STATUSES))
    if diff:
        chelp.clear_cache_and_exit(errcode, f"Statuses {diff} are not legit statuses")

    diff = list(set(util.csv_to_list(params.get(options.SEVERITIES))) - set(idefs.STD_SEVERITIES + hotspots.SEVERITIES))
    if diff:
        chelp.clear_cache_and_exit(errcode, f"Severities {diff} are not legit severities")

    diff = list(set(util.csv_to_list(params.get(options.TYPES))) - set(idefs.STD_TYPES + hotspots.TYPES))
    if diff:
        chelp.clear_cache_and_exit(errcode, f"Types {diff} are not legit types")
    if len(params[options.CSV_SEPARATOR]) > 1:
        chelp.clear_cache_and_exit(errcode, f"CSV separator must be a single character, {params[options.CSV_SEPARATOR]} is not legit")

    return True


def has_filter(params: types.ApiParams, type_of_filter: str, filter_values: list[str]) -> bool:
    """Checks if the search parameters contain any of the specified filters"""
    log.debug("Checking if filter '%s' with allowed values %s is in params %s ", type_of_filter, str(filter_values), str(params))
    return type_of_filter in params and any(t in params[type_of_filter] for t in filter_values)


def needs_issue_search(params: types.ApiParams) -> bool:
    """Returns whether an issue search is needed based on the parameters"""
    return (options.TYPES not in params and options.STATUSES not in params and options.RESOLUTIONS not in params) or (
        has_filter(params, options.TYPES, idefs.STD_TYPES + idefs.MQR_QUALITIES)
        or has_filter(params, options.STATUSES, idefs.STATUSES)
        or has_filter(params, options.SEVERITIES, idefs.STD_SEVERITIES + idefs.MQR_SEVERITIES)
        or has_filter(params, options.RESOLUTIONS, idefs.RESOLUTIONS)
    )


def needs_hotspot_search(params: types.ApiParams) -> bool:
    """Returns whether an hotspot search is needed based on the parameters"""
    if options.TAGS in params:
        return False
    return (options.TYPES not in params and options.STATUSES not in params and options.RESOLUTIONS not in params) or (
        has_filter(params, options.TYPES, hotspots.TYPES)
        or has_filter(params, options.STATUSES, hotspots.STATUSES)
        or has_filter(params, options.SEVERITIES, hotspots.SEVERITIES)
        or has_filter(params, options.RESOLUTIONS, hotspots.RESOLUTIONS)
    )


def get_component_findings(component: object, search_findings: bool, params: ConfigSettings) -> dict[str, findings.Finding]:
    """Gets the findings of a component and puts them in a writing queue"""
    try:
        _ = next(v for k, v in params.items() if k in _SEARCH_CRITERIA and v is not None)
        search_findings = False
    except StopIteration:
        pass

    if search_findings and not isinstance(component, (applications.Application, portfolios.Portfolio)):
        return findings.export_findings(
            component.endpoint, component.key, branch=params.get("branch", None), pull_request=params.get("pullRequest", None)
        )

    new_params = params.copy()
    if options.PULL_REQUESTS in new_params:
        new_params["pullRequest"] = new_params.pop(options.PULL_REQUESTS)
    findings_list = {}
    if needs_issue_search(params):
        findings_list = component.get_issues(filters=new_params)
    if needs_hotspot_search(params):
        findings_list |= component.get_hotspots(filters=new_params)
    return findings_list


def store_findings(components_list: list[object], endpoint: platform.Platform, params: ConfigSettings) -> int:
    """Export all findings of a given project list

    :param list[Components] components_list: Components to export findings (components can be projects, branches, PRs, applications, or portfolios)
    :param Platform endpoint: SonarQube or SonarCloud endpoint
    :param ConfigSettings params: Search filtering parameters for the export
    :returns: Number of exported findings
    """
    comp_params = {k: v for k, v in params.items() if k in _SEARCH_CRITERIA}
    local_params = params.copy()
    file = local_params.pop(options.REPORT_FILE)
    __write_header(file, endpoint=endpoint, **local_params)
    total_findings = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=params.get(options.NBR_THREADS, 4), thread_name_prefix="FindingSearch") as executor:
        futures, futures_map = [], {}
        for comp in components_list:
            future = executor.submit(get_component_findings, comp, params.get(options.USE_FINDINGS, False), comp_params)
            futures.append(future)
            futures_map[future] = comp
        for future in concurrent.futures.as_completed(futures):
            comp = futures_map[future]
            try:
                found_findings = future.result(timeout=60)
                if len(found_findings) == 0:
                    continue
                __write_findings(found_findings, file, total_findings == 0, **local_params)
                total_findings += len(found_findings)
            except TimeoutError as e:
                log.error(f"Getting findings for {str(comp)} timed out after 60 seconds for {str(future)}.")
            except Exception as e:
                traceback.print_exc()
                log.error(f"Exception {str(e)} when exporting findings of {str(comp)}.")
    __write_footer(file, local_params[options.FORMAT])
    return total_findings


def __turn_off_use_findings_if_needed(endpoint: object, params: dict[str, str]) -> dict[str, str]:
    """Turn off use-findings option if some incompatible options (issue filters) are used"""
    if not params[options.USE_FINDINGS]:
        return params
    if endpoint.is_sonarcloud():
        log.warning("--%s option is not available with SonarQube Cloud, disabling the option to proceed", options.USE_FINDINGS)
        params[options.USE_FINDINGS] = False
        return params

    for p in _OPTIONS_INCOMPATIBLE_WITH_USE_FINDINGS:
        if params.get(p, None) is not None:
            log.warning("Selected search criteria %s will disable --%s", params[p], options.USE_FINDINGS)
            params[options.USE_FINDINGS] = False
            break
    return params


def main() -> None:
    """Main entry point"""
    global DATES_WITHOUT_TIME
    start_time = util.start_clock()
    try:
        kwargs = util.convert_args(parse_args("Sonar findings export"))
        sqenv = platform.Platform(**kwargs)
        sqenv.verify_connection()
        sqenv.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")

        del kwargs[options.TOKEN]
        kwargs.pop(options.HTTP_TIMEOUT, None)
        del kwargs[options.URL]
        DATES_WITHOUT_TIME = kwargs[options.DATES_WITHOUT_TIME]
        params = util.remove_nones(kwargs.copy())
        params[options.REPORT_FILE] = kwargs[options.REPORT_FILE]
        __verify_inputs(params)

        params = __turn_off_use_findings_if_needed(sqenv, params=params)
        branch_regexp = params.get(options.BRANCH_REGEXP, None)
        if sqenv.edition() == c.CE and (branch_regexp is not None or params.get(options.PULL_REQUESTS, None) is not None):
            chelp.clear_cache_and_exit(
                errcodes.UNSUPPORTED_OPERATION,
                f"Options '--{options.BRANCH_REGEXP}' and '--{options.PULL_REQUESTS}' shall not be used with Community Edition/Community Build",
            )

        components_list = component_helper.get_components(
            endpoint=sqenv,
            component_type=params[options.COMPONENT_TYPE],
            key_regexp=params.get(options.KEY_REGEXP, None),
            branch_regexp=branch_regexp,
        )
        if params[options.COMPONENT_TYPE] == "portfolios":
            components = []
            for comp in components_list:
                components += comp.components()
            components_list = components

        if len(components_list) == 0:
            br = f"and branch matching regexp '{params[options.BRANCH_REGEXP]}'" if options.BRANCH_REGEXP in params else ""
            raise exceptions.SonarException(
                f"No {params[options.COMPONENT_TYPE]} found with key matching regexp '{params.get(options.KEY_REGEXP, None)}' {br}",
                errcodes.WRONG_SEARCH_CRITERIA,
            )

        fmt, fname = params.get(options.FORMAT, None), params.get(options.REPORT_FILE, None)
        params[options.FORMAT] = util.deduct_format(fmt, fname, allowed_formats=("csv", "json", "sarif"))
        if fname is not None and os.path.exists(fname):
            os.remove(fname)

        log.info("Exporting findings for %d projects with params %s", len(components_list), str(params))
        nb_findings = 0

        nb_findings = store_findings(components_list, endpoint=sqenv, params=params)
    except (PermissionError, FileNotFoundError) as e:
        chelp.clear_cache_and_exit(errcodes.OS_ERROR, f"OS error while exporting findings: {e}")
    except exceptions.SonarException as e:
        chelp.clear_cache_and_exit(e.errcode, e.message)

    log.info(
        "Exported %d findings to %s (%d components from URL %s)",
        nb_findings,
        util.filename(params[options.REPORT_FILE]),
        len(components_list),
        sqenv.local_url,
    )
    chelp.clear_cache_and_exit(errcodes.OK, start_time=start_time)


if __name__ == "__main__":
    main()
