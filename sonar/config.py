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
"""
    Exports SonarQube platform configuration as JSON
"""
import sys
import datetime
import pytz
from sonar import (
    env,
    version,
    settings,
    projects,
    rules,
    qualityprofiles,
    qualitygates,
    portfolios,
    applications,
    users,
    groups,
    options,
)
import sonar.utilities as util


_SETTINGS = "settings"
_USERS = "users"
_GROUPS = "groups"
_GATES = "qualitygates"
_RULES = "rules"
_PROFILES = "qualityprofiles"
_PROJECTS = "projects"
_APPS = "applications"
_PORTFOLIOS = "portfolios"

_EVERYTHING = [_SETTINGS, _USERS, _GROUPS, _GATES, _RULES, _PROFILES, _PROJECTS, _APPS, _PORTFOLIOS]

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
    _SETTINGS: __JSON_KEY_SETTINGS,
    _USERS: __JSON_KEY_USERS,
    _GROUPS: __JSON_KEY_GROUPS,
    _GATES: __JSON_KEY_GATES,
    _RULES: __JSON_KEY_RULES,
    _PROFILES: __JSON_KEY_PROFILES,
    _PROJECTS: __JSON_KEY_PROJECTS,
    _APPS: __JSON_KEY_APPS,
    _PORTFOLIOS: __JSON_KEY_PORTFOLIOS,
}


def __map(k):
    return __MAP.get(k, k)


def __parse_args(desc):
    parser = util.set_common_args(desc)
    parser = util.set_project_args(parser)
    parser = util.set_output_file_args(parser, json_fmt=True, csv_fmt=False)
    parser.add_argument(
        "-w",
        "--what",
        required=False,
        default="",
        help=f"What to export or import {','.join(_EVERYTHING)}",
    )
    parser.add_argument(
        "-e",
        "--export",
        required=False,
        default=False,
        action="store_true",
        help="to export configuration (exclusive of --import)",
    )
    parser.add_argument(
        "-i",
        "--import",
        required=False,
        default=False,
        action="store_true",
        help="to import configuration (exclusive of --export)",
    )
    args = util.parse_and_check_token(parser)
    util.check_environment(vars(args))
    util.logger.info("sonar-tools version %s", version.PACKAGE_VERSION)
    return args


def __count_settings(what, sq_settings):
    nbr_settings = 0
    for s in what:
        tmp_settings = sq_settings.get(__map(s), {})
        nbr_settings += 0 if tmp_settings is None else len(tmp_settings)
    if "settings" in what:
        for categ in settings.CATEGORIES:
            if categ in sq_settings[__JSON_KEY_SETTINGS]:
                nbr_settings += len(sq_settings[__JSON_KEY_SETTINGS][categ]) - 1
    return nbr_settings


def __export_config(endpoint, what, args):
    sq_settings = {}
    sq_settings[__JSON_KEY_PLATFORM] = endpoint.basics()
    if _SETTINGS in what:
        sq_settings[__JSON_KEY_SETTINGS] = endpoint.export()
    if _RULES in what:
        sq_settings[__JSON_KEY_RULES] = rules.export(endpoint)
    if _PROFILES in what:
        if _RULES not in what:
            sq_settings[__JSON_KEY_RULES] = rules.export(endpoint)
        sq_settings[__JSON_KEY_PROFILES] = qualityprofiles.export(endpoint)
    if _GATES in what:
        sq_settings[__JSON_KEY_GATES] = qualitygates.export(endpoint)
    if _PROJECTS in what:
        project_settings = {}
        for k, p in projects.get_projects_list(str_key_list=args.projectKeys, endpoint=endpoint).items():
            project_settings[k] = p.export()
            project_settings[k].pop("key")
        sq_settings[__JSON_KEY_PROJECTS] = project_settings
    if _APPS in what:
        apps_settings = {}
        for k, app in applications.search(endpoint).items():
            apps_settings[k] = app.export()
            apps_settings[k].pop("key")
        sq_settings[__JSON_KEY_APPS] = apps_settings
    if _PORTFOLIOS in what:
        sq_settings[__JSON_KEY_PORTFOLIOS] = portfolios.export(endpoint)
    if _USERS in what:
        sq_settings[__JSON_KEY_USERS] = users.export(endpoint)
    if _GROUPS in what:
        sq_settings[__JSON_KEY_GROUPS] = groups.export(endpoint)

    util.remove_nones(sq_settings)
    with util.open_file(args.file) as fd:
        print(util.json_dump(sq_settings), file=fd)

    util.logger.info("Exported %d items", __count_settings(what, sq_settings))


def __import_config(endpoint, what, args):
    data = util.load_json_file(args.file)
    if _GROUPS in what:
        groups.import_config(endpoint, data)
    if _USERS in what:
        users.import_config(endpoint, data)
    if _GATES in what:
        qualitygates.import_config(endpoint, data)
    if _RULES in what:
        rules.import_config(endpoint, data)
    if _PROFILES in what:
        if _RULES not in what:
            rules.import_config(endpoint, data)
        qualityprofiles.import_config(endpoint, data)
    if _SETTINGS in what:
        endpoint.import_config(data["globalSettings"])
    if _PROJECTS in what:
        projects.import_config(endpoint, data)
    if _APPS in what:
        applications.import_config(endpoint, data)
    if _PORTFOLIOS in what:
        portfolios.import_config(endpoint, data)
    util.logger.info("Import finished")


def main():
    args = __parse_args("Extract SonarQube platform configuration")
    kwargs = vars(args)
    if not kwargs["export"] and not kwargs["import"]:
        util.exit_fatal("One of --export or --import option must be chosen", exit_code=options.ERR_ARGS_ERROR)
    if kwargs["export"] and kwargs["import"]:
        util.exit_fatal("--export or --import options are exclusive of each other", exit_code=options.ERR_ARGS_ERROR)

    start_time = datetime.datetime.today()

    endpoint = env.Environment(some_url=args.url, some_token=args.token)
    what = args.what
    if args.what == "":
        what = _EVERYTHING
    else:
        what = util.csv_to_list(what)
    for w in what:
        if w not in _EVERYTHING:
            util.exit_fatal(
                f"'{w}' is not something that can be imported or exported, chose among {','.join(_EVERYTHING)}",
                exit_code=options.ERR_ARGS_ERROR,
            )

    if kwargs["export"]:
        __export_config(endpoint, what, args)
    if kwargs["import"]:
        __import_config(endpoint, what, args)
    util.logger.info("Total execution time: %s", str(datetime.datetime.today() - start_time))
    sys.exit(0)


if __name__ == "__main__":
    main()
