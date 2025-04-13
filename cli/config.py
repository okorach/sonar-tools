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
    Exports SonarQube platform configuration as JSON
"""
import sys
from typing import TextIO
from threading import Thread
from queue import Queue

import json
import yaml

from cli import options
from sonar import exceptions, errcodes, utilities, version
from sonar.util import types, constants as c
import sonar.logging as log
from sonar import platform, rules, qualityprofiles, qualitygates, users, groups
from sonar import projects, portfolios, applications

TOOL_NAME = "sonar-config"

DONT_INLINE_LISTS = "dontInlineLists"
FULL_EXPORT = "fullExport"
EXPORT_EMPTY = "exportEmpty"

_EXPORT_CALLS = {
    c.CONFIG_KEY_PLATFORM: [c.CONFIG_KEY_PLATFORM, platform.basics, None],
    options.WHAT_SETTINGS: [c.CONFIG_KEY_SETTINGS, platform.export, platform.convert_for_yaml],
    options.WHAT_RULES: [c.CONFIG_KEY_RULES, rules.export, rules.convert_for_yaml],
    options.WHAT_PROFILES: [c.CONFIG_KEY_PROFILES, qualityprofiles.export, qualityprofiles.convert_for_yaml],
    options.WHAT_GATES: [c.CONFIG_KEY_GATES, qualitygates.export, qualitygates.convert_for_yaml],
    options.WHAT_PROJECTS: [c.CONFIG_KEY_PROJECTS, projects.export, projects.convert_for_yaml],
    options.WHAT_APPS: [c.CONFIG_KEY_APPS, applications.export, applications.convert_for_yaml],
    options.WHAT_PORTFOLIOS: [c.CONFIG_KEY_PORTFOLIOS, portfolios.export, portfolios.convert_for_yaml],
    options.WHAT_USERS: [c.CONFIG_KEY_USERS, users.export, users.convert_for_yaml],
    options.WHAT_GROUPS: [c.CONFIG_KEY_GROUPS, groups.export, groups.convert_for_yaml],
}

WHAT_EVERYTHING = list(_EXPORT_CALLS.keys())[1:]


def __parse_args(desc: str) -> object:
    """Sets and parses all sonar-config options"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("json", "yaml"))
    parser = options.add_thread_arg(parser, "project export")
    parser = options.set_what(parser, what_list=WHAT_EVERYTHING, operation="export or import")
    parser = options.add_import_export_arg(parser, "configuration")
    parser.add_argument(
        f"--{FULL_EXPORT}",
        required=False,
        default=False,
        action="store_true",
        help="Also exports informative data that would be ignored as part of an import. Informative field are prefixed with _."
        "This option is ignored in case of import",
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
    parser.add_argument(
        f"--{DONT_INLINE_LISTS}",
        required=False,
        default=False,
        action="store_true",
        help="By default, sonar-config exports multi-valued settings as comma separated strings instead of arrays (if there is not comma in values). "
        "Set this flag if you want to force export multi valued settings as arrays",
    )
    parser.add_argument(
        f"--{EXPORT_EMPTY}",
        required=False,
        default=False,
        action="store_true",
        help="By default, sonar-config does not export empty values, setting this flag will add empty values in the export",
    )
    return options.parse_and_check(parser=parser, logger_name=TOOL_NAME)


def __write_export(config: dict[str, str], file: str, format: str) -> None:
    """Writes the configuration in file"""
    with utilities.open_file(file) as fd:
        if format == "yaml":
            print(yaml.dump(__convert_for_yaml(config), sort_keys=False), file=fd)
        else:
            print(utilities.json_dump(config), file=fd)


def __convert_for_yaml(json_export: dict[str, any]) -> dict[str, any]:
    """Converts the default JSON produced by export to a modified version more suitable for YAML"""
    for what in WHAT_EVERYTHING:
        if what in json_export:
            yamlify_func = _EXPORT_CALLS[what][2]
            json_export[what] = yamlify_func(json_export[what])
    return json_export


def write_objects(queue: Queue[types.ObjectJsonRepr], fd: TextIO, object_type: str, export_settings: types.ConfigSettings) -> None:
    """
    Thread to write projects in the JSON file
    """
    done = False
    prefix = ""
    log.info("Waiting %s to write...", object_type)
    print(f'"{object_type}": ' + "{", file=fd)
    while not done:
        obj_json = queue.get()
        done = obj_json is utilities.WRITE_END
        if not done:
            if object_type == "groups":
                obj_json = __prep_json_for_write(obj_json, {**export_settings, EXPORT_EMPTY: True})
            else:
                obj_json = __prep_json_for_write(obj_json, export_settings)
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


def export_config(endpoint: platform.Platform, what: list[str], **kwargs) -> None:
    """Exports a platform configuration in a JSON file"""
    file = kwargs[options.REPORT_FILE]
    mode = kwargs.get("mode", "CONFIG")
    export_settings = kwargs.copy()
    export_settings.update(
        {
            "INLINE_LISTS": not kwargs.get(DONT_INLINE_LISTS, False),
            "EXPORT_DEFAULTS": True,
            "FULL_EXPORT": kwargs.get(FULL_EXPORT, False),
            "MODE": mode,
            "THREADS": kwargs[options.NBR_THREADS],
            "SKIP_ISSUES": kwargs.get("skipIssues", False),
        }
    )
    if mode == "MIGRATION":
        export_settings["FULL_EXPORT"] = False
        export_settings["INLINE_LISTS"] = False
        export_settings[EXPORT_EMPTY] = True
    log.info("Exporting with settings: %s", utilities.json_dump(export_settings, redact_tokens=True))
    if "projects" in what and kwargs[options.KEYS]:
        non_existing_projects = [key for key in kwargs[options.KEYS] if not projects.exists(key, endpoint)]
        if len(non_existing_projects) > 0:
            utilities.exit_fatal(f"Project key(s) '{','.join(non_existing_projects)}' do(es) not exist", errcodes.NO_SUCH_KEY)

    what.append(c.CONFIG_KEY_PLATFORM)
    log.info("Exporting configuration from %s", kwargs[options.URL])

    is_first = True
    write_q = Queue(maxsize=0)
    with utilities.open_file(file, mode="w") as fd:
        print("{", file=fd)
        for what_item, call_data in _EXPORT_CALLS.items():
            if what_item not in what:
                continue
            ndx, func, _ = call_data
            if not is_first:
                print(",", file=fd)
            is_first = False
            worker = Thread(target=write_objects, args=(write_q, fd, ndx, export_settings))
            worker.daemon = True
            worker.name = f"Write{ndx[:1].upper()}{ndx[1:10]}"
            worker.start()
            try:
                func(endpoint, export_settings=export_settings, key_list=kwargs[options.KEYS], write_q=write_q)
            except exceptions.UnsupportedOperation as e:
                log.warning(e.message)
                if write_q:
                    write_q.put(utilities.WRITE_END)
            write_q.join()
        print("\n}", file=fd)
    utilities.normalize_json_file(file, remove_empty=False, remove_none=True)
    log.info("Exporting %s data from %s completed", mode.lower(), kwargs[options.URL])


def __prep_json_for_write(json_data: types.ObjectJsonRepr, export_settings: types.ConfigSettings) -> types.ObjectJsonRepr:
    """Cleans up the JSON before writing"""
    log.debug("Exporting settings %s", utilities.json_dump(export_settings))
    json_data = utilities.sort_lists(json_data)
    if export_settings.get("MODE", "CONFIG") == "MIGRATION":
        return json_data
    if not export_settings.get("FULL_EXPORT", False):
        json_data = utilities.remove_nones(json_data)
        if not export_settings.get(EXPORT_EMPTY, False):
            log.debug("Removing empties")
            json_data = utilities.remove_empties(json_data)
    if export_settings.get("INLINE_LISTS", True):
        json_data = utilities.inline_lists(json_data, exceptions=("conditions",))
    return json_data


def __import_config(endpoint: platform.Platform, what: list[str], **kwargs) -> None:
    """Imports a platform configuration from a JSON file"""
    log.info("Importing configuration to %s", kwargs[options.URL])
    try:
        with open(kwargs[options.REPORT_FILE], "r", encoding="utf-8") as fd:
            data = json.loads(fd.read())
    except FileNotFoundError as e:
        utilities.exit_fatal(f"OS error while reading file: {e}", exit_code=errcodes.OS_ERROR)
    key_list = kwargs[options.KEYS]

    calls = {
        options.WHAT_GROUPS: groups.import_config,
        options.WHAT_USERS: users.import_config,
        options.WHAT_GATES: qualitygates.import_config,
        options.WHAT_RULES: rules.import_config,
        options.WHAT_PROFILES: qualityprofiles.import_config,
        options.WHAT_SETTINGS: platform.import_config,
        options.WHAT_PROJECTS: projects.import_config,
        options.WHAT_APPS: applications.import_config,
        options.WHAT_PORTFOLIOS: portfolios.import_config,
    }

    for what_item, func in calls.items():
        if what_item in what:
            try:
                func(endpoint, data, key_list=key_list)
            except exceptions.UnsupportedOperation as e:
                log.warning(e.message)
    log.info("Importing configuration to %s completed", kwargs[options.URL])


def main() -> None:
    """Main entry point for sonar-config"""
    start_time = utilities.start_clock()
    try:
        kwargs = utilities.convert_args(__parse_args("Extract SonarQube platform configuration"))
        endpoint = platform.Platform(**kwargs)
        endpoint.verify_connection()
        endpoint.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")
    except (options.ArgumentsError, exceptions.ObjectNotFound) as e:
        utilities.exit_fatal(e.message, e.errcode)
    if not kwargs[options.EXPORT] and not kwargs[options.IMPORT]:
        utilities.exit_fatal(f"One of --{options.EXPORT} or --{options.IMPORT} option must be chosen", exit_code=errcodes.ARGS_ERROR)

    what = utilities.check_what(kwargs.pop(options.WHAT, None), WHAT_EVERYTHING, "exported or imported")
    if options.WHAT_PROFILES in what and options.WHAT_RULES not in what:
        what.append(options.WHAT_RULES)
    kwargs[options.FORMAT] = utilities.deduct_format(kwargs[options.FORMAT], kwargs[options.REPORT_FILE], allowed_formats=("json", "yaml"))
    if kwargs[options.EXPORT]:
        try:
            export_config(endpoint, what, **kwargs)
        except exceptions.ObjectNotFound as e:
            utilities.exit_fatal(e.message, errcodes.NO_SUCH_KEY)
        except (PermissionError, FileNotFoundError) as e:
            utilities.exit_fatal(f"OS error while exporting config: {e}", exit_code=errcodes.OS_ERROR)
    if kwargs["import"]:
        if kwargs["file"] is None:
            utilities.exit_fatal("--file is mandatory to import configuration", errcodes.ARGS_ERROR)
        __import_config(endpoint, what, **kwargs)
    utilities.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
