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
    Exports SonarQube platform configuration as JSON
"""
import sys
import datetime
from sonar import platform, version, rules, qualityprofiles, qualitygates, portfolios, applications, users, groups, options, utilities, exceptions
from sonar.projects import projects

_EVERYTHING = [
    options.WHAT_SETTINGS,
    options.WHAT_USERS,
    options.WHAT_GROUPS,
    options.WHAT_GATES,
    options.WHAT_RULES,
    options.WHAT_PROFILES,
    options.WHAT_PROJECTS,
    options.WHAT_APPS,
    options.WHAT_PORTFOLIOS,
]

__JSON_KEY_PLATFORM = "platform"

__JSON_KEY_SETTINGS = "globalSettings"
__JSON_KEY_USERS = "users"
__JSON_KEY_GROUPS = "groups"
__JSON_KEY_GATES = "qualityGates"
__JSON_KEY_RULES = "rules"
__JSON_KEY_PROFILES = "qualityProfiles"
__JSON_KEY_PROJECTS = "projects"
__JSON_KEY_APPS = "applications"
__JSON_KEY_PORTFOLIOS = "portfolios"

__MAP = {
    options.WHAT_SETTINGS: __JSON_KEY_SETTINGS,
    options.WHAT_USERS: __JSON_KEY_USERS,
    options.WHAT_GROUPS: __JSON_KEY_GROUPS,
    options.WHAT_GATES: __JSON_KEY_GATES,
    options.WHAT_RULES: __JSON_KEY_RULES,
    options.WHAT_PROFILES: __JSON_KEY_PROFILES,
    options.WHAT_PROJECTS: __JSON_KEY_PROJECTS,
    options.WHAT_APPS: __JSON_KEY_APPS,
    options.WHAT_PORTFOLIOS: __JSON_KEY_PORTFOLIOS,
}


def __map(k):
    return __MAP.get(k, k)


def __parse_args(desc):
    parser = utilities.set_common_args(desc)
    parser = utilities.set_key_arg(parser)
    parser = utilities.set_output_file_args(parser, json_fmt=True, csv_fmt=False)
    parser = options.add_thread_arg(parser, "project export")
    parser = utilities.set_what(parser, what_list=_EVERYTHING, operation="export or import")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-e",
        "--export",
        required=False,
        default=False,
        action="store_true",
        help="to export configuration (exclusive of --import)",
    )
    group.add_argument(
        "-i",
        "--import",
        required=False,
        default=False,
        action="store_true",
        help="to import configuration (exclusive of --export)",
    )
    parser.add_argument(
        "--fullExport",
        required=False,
        default=False,
        action="store_true",
        help="Also exports informative data that would be ignored as part of an import. Informative field are prefixed with _."
        "This option is ignored in case of import",
    )
    args = utilities.parse_and_check_token(parser)
    utilities.check_environment(vars(args))
    utilities.check_token(args.token)
    utilities.logger.info("sonar-tools version %s", version.PACKAGE_VERSION)
    return args


def __export_config(endpoint, what, args):
    key_list = utilities.csv_to_list(args.projectKeys)
    if len(key_list) > 0 and "projects" in utilities.csv_to_list(args.what):
        for key in key_list:
            if not projects.exists(key, endpoint):
                utilities.exit_fatal(f"Project key '{key}' does not exist", options.ERR_NO_SUCH_KEY)
    utilities.logger.info("Exporting configuration from %s", args.url)
    sq_settings = {}
    sq_settings[__JSON_KEY_PLATFORM] = endpoint.basics()
    if options.WHAT_SETTINGS in what:
        sq_settings[__JSON_KEY_SETTINGS] = endpoint.export(full=args.fullExport)
    if options.WHAT_RULES in what:
        sq_settings[__JSON_KEY_RULES] = rules.export(endpoint, full=args.fullExport)
    if options.WHAT_PROFILES in what:
        if options.WHAT_RULES not in what:
            sq_settings[__JSON_KEY_RULES] = rules.export(endpoint, full=args.fullExport)
        sq_settings[__JSON_KEY_PROFILES] = qualityprofiles.export(endpoint, full=args.fullExport)
    if options.WHAT_GATES in what:
        sq_settings[__JSON_KEY_GATES] = qualitygates.export(endpoint, full=args.fullExport)
    if options.WHAT_PROJECTS in what:
        sq_settings[__JSON_KEY_PROJECTS] = projects.export(endpoint, key_list=args.projectKeys, full=args.fullExport, threads=args.threads)
    if options.WHAT_APPS in what:
        try:
            sq_settings[__JSON_KEY_APPS] = applications.export(endpoint, key_list=args.projectKeys, full=args.fullExport)
        except exceptions.UnsupportedOperation as e:
            utilities.logger.info("%s", e.message)
    if options.WHAT_PORTFOLIOS in what:
        try:
            sq_settings[__JSON_KEY_PORTFOLIOS] = portfolios.export(endpoint, key_list=args.projectKeys, full=args.fullExport)
        except exceptions.UnsupportedOperation as e:
            utilities.logger.info("%s", e.message)
    if options.WHAT_USERS in what:
        sq_settings[__JSON_KEY_USERS] = users.export(endpoint, full=args.fullExport)
    if options.WHAT_GROUPS in what:
        sq_settings[__JSON_KEY_GROUPS] = groups.export(endpoint)

    utilities.remove_nones(sq_settings)
    with utilities.open_file(args.file) as fd:
        print(utilities.json_dump(sq_settings), file=fd)
    utilities.logger.info("Exporting configuration from %s completed", args.url)


def __import_config(endpoint, what, args):
    utilities.logger.info("Importing configuration to %s", args.url)
    data = utilities.load_json_file(args.file)
    if options.WHAT_GROUPS in what:
        groups.import_config(endpoint, data)
    if options.WHAT_USERS in what:
        users.import_config(endpoint, data)
    if options.WHAT_GATES in what:
        qualitygates.import_config(endpoint, data)
    if options.WHAT_RULES in what:
        rules.import_config(endpoint, data)
    if options.WHAT_PROFILES in what:
        if options.WHAT_RULES not in what:
            rules.import_config(endpoint, data)
        qualityprofiles.import_config(endpoint, data)
    if options.WHAT_SETTINGS in what:
        endpoint.import_config(data["globalSettings"])
    if options.WHAT_PROJECTS in what:
        projects.import_config(endpoint, data, key_list=args.projectKeys)
    if options.WHAT_APPS in what:
        applications.import_config(endpoint, data, key_list=args.projectKeys)
    if options.WHAT_PORTFOLIOS in what:
        portfolios.import_config(endpoint, data, key_list=args.projectKeys)
    utilities.logger.info("Importing configuration to %s completed", args.url)


def main():
    args = __parse_args("Extract SonarQube platform configuration")
    kwargs = vars(args)
    if not kwargs["export"] and not kwargs["import"]:
        utilities.exit_fatal("One of --export or --import option must be chosen", exit_code=options.ERR_ARGS_ERROR)

    start_time = datetime.datetime.today()
    endpoint = platform.Platform(some_url=args.url, some_token=args.token, cert_file=args.clientCert)
    what = utilities.check_what(args.what, _EVERYTHING, "exported or imported")
    if kwargs["export"]:
        try:
            __export_config(endpoint, what, args)
        except exceptions.ObjectNotFound as e:
            utilities.exit_fatal(e.message, options.ERR_NO_SUCH_KEY)
    if kwargs["import"]:
        __import_config(endpoint, what, args)
    utilities.logger.info("Total execution time: %s", str(datetime.datetime.today() - start_time))
    sys.exit(0)


if __name__ == "__main__":
    main()
