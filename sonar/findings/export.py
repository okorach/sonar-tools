#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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
    This script exports findings as CSV or JSON

    Usage: sonar-findings-export.py -t <SQ_TOKEN> -u <SQ_URL> [<filters>]

    Filters can be:
    [-k <projectKey>]
    [-s <statuses>] (FIXED, CLOSED, REOPENED, REVIEWED)
    [-r <resolutions>] (UNRESOLVED, FALSE-POSITIVE, WONTFIX)
    [-a <createdAfter>] findings created on or after a given date (YYYY-MM-DD)
    [-b <createdBefore>] findings created before or on a given date (YYYY-MM-DD)
    [--severities <severities>] Comma separated desired severities: BLOCKER, CRITICAL, MAJOR, MINOR, INFO
    [--types <types>] Comma separated findings types (VULNERABILITY,BUG,CODE_SMELL,SECURITY_HOTSPOT)
    [--tags]
"""
import sys
import os


from sonar import version, env, projects, options
import sonar.utilities as util
from sonar.findings import findings, issues, hotspots


def parse_args(desc):
    parser = util.set_common_args(desc)
    parser = util.set_project_args(parser)
    parser = util.set_output_file_args(parser)
    parser.add_argument(
        "-b",
        "--branches",
        required=False,
        default=None,
        help="Comma separated list of branches to export. Use * to export findings from all branches. "
        "If not specified, only findings of the main branch will be exported",
    )
    parser.add_argument(
        "-p",
        "--pullRequests",
        required=False,
        default=None,
        help="Comma separated list of pull request. Use * to export findings from all PRs. "
        "If not specified, only findings of the main branch will be exported",
    )
    parser.add_argument(
        "--statuses",
        required=False,
        help="comma separated status among " + util.list_to_csv(issues.STATUSES + hotspots.STATUSES),
    )
    parser.add_argument(
        "--createdAfter",
        required=False,
        help="findings created on or after a given date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--createdBefore",
        required=False,
        help="findings created on or before a given date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--resolutions",
        required=False,
        help="Comma separated resolution of the findings among " + util.list_to_csv(issues.RESOLUTIONS + hotspots.RESOLUTIONS),
    )
    parser.add_argument(
        "--severities",
        required=False,
        help="Comma separated severities among" + util.list_to_csv(issues.SEVERITIES + hotspots.SEVERITIES),
    )
    parser.add_argument(
        "--types",
        required=False,
        help="Comma separated types among " + util.list_to_csv(issues.TYPES + hotspots.TYPES),
    )
    parser.add_argument("--tags", help="Comma separated findings tags", required=False)
    parser.add_argument(
        "--useFindings",
        required=False,
        default=False,
        action="store_true",
        help="Use export_findings() whenever possible",
    )
    parser.add_argument(
        "--" + options.WITH_URL,
        required=False,
        default=False,
        action="store_true",
        help="Generate finding URL in the report, false by default",
    )
    return util.parse_and_check_token(parser)


def __write_header(file, format):
    if file is None:
        util.logger.info("Dumping report to stdout")
    else:
        util.logger.info("Dumping report to file '%s'", file)
    with util.open_file(file) as f:
        if format == "json":
            print("[", file=f)
        else:
            print(findings.to_csv_header(), file=f)


def __write_footer(file, format):
    if format != "json":
        return
    with util.open_file(file, mode="a") as f:
        print("]\n", file=f)


def __dump_findings(findings_list, file, file_format, is_last=False, **kwargs):
    with util.open_file(file, mode="a") as f:
        url = ""
        sep = kwargs[options.CSV_SEPARATOR]
        i = len(findings_list)
        comma = ","
        for _, finding in findings_list.items():
            i -= 1
            if file_format == "json":
                finding_json = finding.to_json()
                if not kwargs[options.WITH_URL]:
                    finding_json.pop("url", None)
                if is_last and i == 0:
                    comma = ""
                print(f"{util.json_dump(finding_json, indent=1)}{comma}\n", file=f, end="")
            else:
                if kwargs[options.WITH_URL]:
                    url = f'{sep}"{finding.url()}"'
                print(f"{finding.to_csv(sep)}{url}", file=f)


def __dump_compact(finding_list, file, **kwargs):
    new_dict = {}
    for finding in finding_list.values():
        f_json = finding.to_json()
        if not kwargs[options.WITH_URL]:
            f_json.pop("url", None)
        pkey = f_json.pop("projectKey")
        ftype = f_json.pop("type")
        if pkey in new_dict:
            if ftype in new_dict[pkey]:
                new_dict[pkey][ftype].append(f_json)
            else:
                new_dict[pkey].update({ftype: [f_json]})
        else:
            new_dict[pkey] = {ftype: [f_json]}
    with util.open_file(file) as f:
        print(util.json_dump(new_dict, indent=1), file=f)


def __get_list(project_key, list_str, list_type):
    if list_str == "*":
        project = projects.get_object(project_key)
        if list_type == "branch":
            list_array = project.get_branches()
        else:
            project.get_pull_requests()
    elif list_str is not None:
        list_array = util.csv_to_list(list_str)
    else:
        list_array = []
    return list_array


def __verify_inputs(params):
    diff = util.difference(
        util.csv_to_list(params.get("resolutions", None)),
        issues.RESOLUTIONS + hotspots.RESOLUTIONS,
    )
    if diff:
        util.exit_fatal(
            f"Resolutions {str(diff)} are not legit resolutions",
            options.ERR_WRONG_SEARCH_CRITERIA,
        )

    diff = util.difference(
        util.csv_to_list(params.get("statuses", None)),
        issues.STATUSES + hotspots.STATUSES,
    )
    if diff:
        util.exit_fatal(
            f"Statuses {str(diff)} are not legit statuses",
            options.ERR_WRONG_SEARCH_CRITERIA,
        )

    diff = util.difference(
        util.csv_to_list(params.get("severities", None)),
        issues.SEVERITIES + hotspots.SEVERITIES,
    )
    if diff:
        util.exit_fatal(
            f"Severities {str(diff)} are not legit severities",
            options.ERR_WRONG_SEARCH_CRITERIA,
        )

    diff = util.difference(util.csv_to_list(params.get("types", None)), issues.TYPES + hotspots.TYPES)
    if diff:
        util.exit_fatal(f"Types {str(diff)} are not legit types", options.ERR_WRONG_SEARCH_CRITERIA)

    return True


def __get_project_findings(key, params, endpoint):

    search_findings = params["useFindings"]
    status_list = util.csv_to_list(params.get("statuses", None))
    issues_statuses = util.intersection(status_list, issues.STATUSES)
    hotspot_statuses = util.intersection(status_list, hotspots.STATUSES)
    resol_list = util.csv_to_list(params.get("resolutions", None))
    issues_resols = util.intersection(resol_list, issues.RESOLUTIONS)
    hotspot_resols = util.intersection(resol_list, hotspots.RESOLUTIONS)
    type_list = util.csv_to_list(params.get("types", None))
    issues_types = util.intersection(type_list, issues.TYPES)
    hotspot_types = util.intersection(type_list, hotspots.TYPES)
    sev_list = util.csv_to_list(params.get("severities", None))
    issues_sevs = util.intersection(sev_list, issues.SEVERITIES)
    hotspot_sevs = util.intersection(sev_list, hotspots.SEVERITIES)

    if status_list or resol_list or type_list or sev_list:
        search_findings = False

    if search_findings:
        findings_list = issues.search_by_project(
            key,
            params=issues.get_search_criteria(params),
            endpoint=endpoint,
            search_findings=search_findings,
        )
        return findings_list

    findings_list = {}
    if (
        (issues_statuses or not status_list)
        and (issues_resols or not resol_list)
        and (issues_types or not type_list)
        and (issues_sevs or not sev_list)
    ):
        findings_list = issues.search_by_project(key, params=issues.get_search_criteria(params), endpoint=endpoint)
    else:
        util.logger.debug(
            "Status = %s, Types = %s, Resol = %s, Sev = %s",
            str(issues_statuses),
            str(issues_types),
            str(issues_resols),
            str(issues_sevs),
        )
        util.logger.info("Selected types, severities, resolutions or statuses disables issue search")
    if (
        (hotspot_statuses or not status_list)
        and (hotspot_resols or not resol_list)
        and (hotspot_types or not type_list)
        and (hotspot_sevs or not sev_list)
    ):
        findings_list.update(hotspots.search_by_project(key, endpoint=endpoint, params=hotspots.get_search_criteria(params)))
    else:
        util.logger.debug(
            "Status = %s, Types = %s, Resol = %s, Sev = %s",
            str(hotspot_statuses),
            str(hotspot_types),
            str(hotspot_resols),
            str(hotspot_sevs),
        )
        util.logger.info("Selected types, severities, resolutions or statuses disables issue search")
    return findings_list


def main():
    kwargs = vars(parse_args("Sonar findings extractor"))
    sqenv = env.Environment(some_url=kwargs["url"], some_token=kwargs["token"])
    del kwargs["token"]
    util.check_environment(kwargs)
    util.logger.info("sonar-tools version %s", version.PACKAGE_VERSION)

    project_key = kwargs.get("projectKeys", None)
    params = util.remove_nones(kwargs.copy())
    __verify_inputs(params)

    for p in (
        "statuses",
        "createdAfter",
        "createdBefore",
        "resolutions",
        "severities",
        "types",
        "tags",
    ):
        if params.get(p, None) is not None:
            if params["useFindings"]:
                util.logger.warning("Selected search criteria %s will disable --useFindings", params[p])
            params["useFindings"] = False
            break
    project_list = projects.get_projects_list(project_key, sqenv)

    fmt = kwargs["format"]
    file = kwargs.pop("file", None)
    if file is not None:
        ext = file.split(".")[-1].lower()
        if os.path.exists(file):
            os.remove(file)
        if ext in ("csv", "json"):
            fmt = ext

    util.logger.info(
        "Exporting findings for %d projects with params %s",
        len(project_list),
        str(params),
    )
    nbr_findings = 0
    __write_header(file, fmt)
    for project_key in project_list:
        all_findings = {}
        branches = __get_list(project_key, kwargs.get("branches", None), "branch")
        prs = __get_list(project_key, kwargs.get("pullRequests", None), "pullrequest")
        if branches:
            for b in branches:
                params["branch"] = b.name
                all_findings.update(__get_project_findings(project_key, params=params, endpoint=sqenv))
        params.pop("branch", None)
        if prs:
            for p in prs:
                params["pullRequest"] = p.key
                all_findings.update(__get_project_findings(project_key, params=params, endpoint=sqenv))
        params.pop("pullRequest", None)
        if not (branches or prs):
            all_findings.update(__get_project_findings(project_key, params=params, endpoint=sqenv))

        __dump_findings(all_findings, file, fmt, **kwargs)
        nbr_findings += len(all_findings)
    __write_footer(file, fmt)
    util.logger.info("Returned findings: %d", nbr_findings)
    sys.exit(0)


if __name__ == "__main__":
    main()
