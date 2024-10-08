#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2022-2024 Olivier Korach
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
from threading import Thread, Lock
from queue import Queue

from cli import options
from sonar import exceptions, errcodes, utilities, version
import sonar.logging as log
from sonar import platform, rules, qualityprofiles, qualitygates, users, groups
from sonar import projects, portfolios, applications

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

_WRITE_LOCK = Lock()


def __parse_args(desc):
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("json",))
    parser = options.add_thread_arg(parser, "migration export")
    parser = options.set_what(parser, what_list=_EVERYTHING, operation="export")
    parser = options.add_import_export_arg(parser, "migration")
    parser.add_argument(
        "--skipIssues",
        required=False,
        default=False,
        action="store_true",
        help="Skips the export of issues count which might be costly iin terms of API calls",
    )
    parser.add_argument(
        "--exportDefaults",
        required=False,
        default=False,
        action="store_true",
        help="Also exports settings values that are the platform defaults. "
        f"By default the export will show the value as '{utilities.DEFAULT}' "
        "and the setting will not be imported at import time",
    )
    args = options.parse_and_check(parser=parser, logger_name="sonar-migration", is_migration=True)
    return args


def write_objects(queue: Queue, fd, object_type: str) -> None:
    """
    Thread to write projects in the JSON file
    """
    done = False
    prefix = ""
    log.info("Waiting %s to write...", object_type)
    print(f'"{object_type}": ' + "{", file=fd)
    while not done:
        obj_json = queue.get()
        done = obj_json is None
        if not done:
            if object_type in ("projects", "applications", "portfolios", "users"):
                if object_type == "users":
                    key = obj_json.pop("login", None)
                else:
                    key = obj_json.pop("key", None)
                log.debug("Writing %s key '%s'", object_type[:-1], key)
                print(f'{prefix}"{key}": {utilities.json_dump(obj_json)}', end="", file=fd)
            else:
                log.debug("Writing %s", object_type)
                print(f"{prefix}{utilities.json_dump(obj_json)[2:-1]}", end="", file=fd)
            prefix = ",\n"
        queue.task_done()
    print("\n}", file=fd, end="")
    log.info("Writing %s complete", object_type)


def __export_config(endpoint: platform.Platform, what: list[str], **kwargs) -> None:
    """Exports a platform configuration in a JSON file"""
    file = kwargs[options.REPORT_FILE]
    export_settings = {
        "INLINE_LISTS": False,
        "EXPORT_DEFAULTS": True,
        # "FULL_EXPORT": kwargs["fullExport"],
        "FULL_EXPORT": False,
        "MODE": "MIGRATION",
        "THREADS": kwargs[options.NBR_THREADS],
        "SKIP_ISSUES": kwargs["skipIssues"],
    }
    if "projects" in what and kwargs[options.KEYS]:
        non_existing_projects = [key for key in kwargs[options.KEYS] if not projects.exists(key, endpoint)]
        if len(non_existing_projects) > 0:
            utilities.exit_fatal(f"Project key(s) '{','.join(non_existing_projects)}' do(es) not exist", errcodes.NO_SUCH_KEY)

    calls = {
        options.WHAT_SETTINGS: [__JSON_KEY_SETTINGS, platform.export],
        options.WHAT_RULES: [__JSON_KEY_RULES, rules.export],
        options.WHAT_PROFILES: [__JSON_KEY_PROFILES, qualityprofiles.export],
        options.WHAT_GATES: [__JSON_KEY_GATES, qualitygates.export],
        options.WHAT_PROJECTS: [__JSON_KEY_PROJECTS, projects.export],
        options.WHAT_APPS: [__JSON_KEY_APPS, applications.export],
        options.WHAT_PORTFOLIOS: [__JSON_KEY_PORTFOLIOS, portfolios.export],
        options.WHAT_USERS: [__JSON_KEY_USERS, users.export],
        options.WHAT_GROUPS: [__JSON_KEY_GROUPS, groups.export],
    }

    log.info("Exporting configuration from %s", kwargs[options.URL])
    key_list = kwargs[options.KEYS]
    sq_settings = {__JSON_KEY_PLATFORM: endpoint.basics()}
    is_first = True
    q = Queue(maxsize=0)
    with utilities.open_file(file, mode="w") as fd:
        print("{", file=fd)
        for what_item, call_data in calls.items():
            if what_item not in what:
                continue
            ndx, func = call_data
            try:
                if not is_first:
                    print(",", file=fd)
                is_first = False
                worker = Thread(target=write_objects, args=(q, fd, ndx))
                worker.daemon = True
                worker.name = f"Write{ndx[:1].upper()}{ndx[1:10]}"
                worker.start()
                sq_settings[ndx] = func(endpoint, export_settings=export_settings, key_list=key_list, write_q=q)
                q.join()
            except exceptions.UnsupportedOperation as e:
                log.warning(e.message)
        sq_settings = utilities.remove_empties(sq_settings)
        # if not kwargs.get("dontInlineLists", False):
        #    sq_settings = utilities.inline_lists(sq_settings, exceptions=("conditions",))
        print("\n}", file=fd)
    log.info("Exporting migration data from %s completed", kwargs["url"])


def main() -> None:
    """Main entry point for sonar-config"""
    start_time = utilities.start_clock()
    try:
        kwargs = utilities.convert_args(__parse_args("Extract SonarQube to SonarCloud migration data"))
        endpoint = platform.Platform(**kwargs)
        endpoint.verify_connection()
        endpoint.set_user_agent(f"sonar-migration {version.MIGRATION_TOOL_VERSION}")
    except (options.ArgumentsError, exceptions.ObjectNotFound) as e:
        utilities.exit_fatal(e.message, e.errcode)

    what = utilities.check_what(kwargs.pop(options.WHAT, None), _EVERYTHING, "exported")
    if options.WHAT_PROFILES in what and options.WHAT_RULES not in what:
        what.append(options.WHAT_RULES)
    kwargs[options.FORMAT] = "json"
    if kwargs[options.REPORT_FILE] is None:
        kwargs[options.REPORT_FILE] = f"sonar-migration.{endpoint.server_id()}.json"
    try:
        __export_config(endpoint, what, **kwargs)
    except exceptions.ObjectNotFound as e:
        utilities.exit_fatal(e.message, errcodes.NO_SUCH_KEY)
    except (PermissionError, FileNotFoundError) as e:
        utilities.exit_fatal(f"OS error while exporting config: {e}", exit_code=errcodes.OS_ERROR)
    log.info("Exporting SQ to SC migration data from %s completed", kwargs[options.URL])
    log.info("Migration file '%s' created", kwargs[options.REPORT_FILE])
    utilities.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
