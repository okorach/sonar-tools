#!/usr/bin/env python3
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

from typing import TextIO, Any
from threading import Thread
from queue import Queue

import json
import yaml

from cli import options
from sonar import exceptions, errcodes, utilities, version
from sonar.util import types, constants as c
from sonar.util import platform_helper as pfhelp
from sonar.util import project_helper as pjhelp
from sonar.util import portfolio_helper as foliohelp
from sonar.util import qualityprofile_helper as qphelp
from sonar.util import rule_helper as rhelp

import sonar.logging as log
from sonar import platform, rules, qualityprofiles, qualitygates, users, groups
from sonar import projects, portfolios, applications
from sonar.util import component_helper

TOOL_NAME = "sonar-config"

DONT_INLINE_LISTS = "dontInlineLists"
FULL_EXPORT = "fullExport"
EXPORT_EMPTY = "exportEmpty"

_SECTIONS_TO_SORT = ("projects", "applications", "portfolios", "users", "groups", "qualityGates", "qualityProfiles")
_SECTIONS_ORDER = (
    "platform",
    "globalSettings",
    "qualityGates",
    "qualityProfiles",
    "projects",
    "applications",
    "portfolios",
    "users",
    "groups",
    "rules",
)

_MIGRATION_EXPORT_SETTINGS = {
    "FULL_EXPORT": False,
    "INLINE_LISTS": False,
    EXPORT_EMPTY: True,
}

_EXPORT_CALLS = {
    c.CONFIG_KEY_PLATFORM: [c.CONFIG_KEY_PLATFORM, platform.basics],
    options.WHAT_SETTINGS: [c.CONFIG_KEY_SETTINGS, platform.export],
    options.WHAT_RULES: [c.CONFIG_KEY_RULES, rules.export],
    options.WHAT_PROFILES: [c.CONFIG_KEY_PROFILES, qualityprofiles.export],
    options.WHAT_GATES: [c.CONFIG_KEY_GATES, qualitygates.export],
    options.WHAT_PROJECTS: [c.CONFIG_KEY_PROJECTS, projects.export],
    options.WHAT_APPS: [c.CONFIG_KEY_APPS, applications.export],
    options.WHAT_PORTFOLIOS: [c.CONFIG_KEY_PORTFOLIOS, portfolios.export],
    options.WHAT_USERS: [c.CONFIG_KEY_USERS, users.export],
    options.WHAT_GROUPS: [c.CONFIG_KEY_GROUPS, groups.export],
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
    parser.add_argument(
        "--convertFrom",
        required=False,
        help="Source sonar-config old JSON format",
    )
    parser.add_argument(
        "--convertTo",
        required=False,
        help="Target sonar-config new JSON format",
    )
    return options.parse_and_check(parser=parser, logger_name=TOOL_NAME)


def __normalize_json(json_data: dict[str, any], remove_empty: bool = True, remove_none: bool = True) -> dict[str, any]:
    """Sorts a JSON file and optionally remove empty and none values"""
    sort_fields = {"users": "login", "groups": "name", "qualityGates": "name", "qualityProfiles": "language"}
    log.info("Normalizing JSON - remove empty = %s, remove nones = %s", str(remove_empty), str(remove_none))
    json_data = utilities.clean_data(json_data, remove_none=remove_none, remove_empty=remove_empty)
    json_data = utilities.order_keys(json_data, *_SECTIONS_ORDER)
    for key in [k for k in _SECTIONS_TO_SORT if k in json_data]:
        if isinstance(json_data[key], dict):
            json_data[key] = {k: json_data[key][k] for k in sorted(json_data[key])}
        else:
            json_data[key] = utilities.sort_list_by_key(json_data[key], sort_fields.get(key, "key"))
    return json_data


def __normalize_file(file: str, format: str) -> bool:
    """Normalizes a JSON or YAML file to order keys in a meaningful order (not necessarily alphabetically)
    :param str file: Filename to normalize
    :param str format: File format (json or yaml)
    :return: whether normaizalization succeeded"""
    try:
        with utilities.open_file(file, mode="r") as fd:
            json_data = json.loads(fd.read())
    except json.decoder.JSONDecodeError:
        log.warning("JSON Decode error while normalizing JSON file '%s', is file complete?", file)
        return False
    json_data = __normalize_json(json_data, remove_empty=False, remove_none=True)
    with utilities.open_file(file, mode="w") as fd:
        if format == "yaml":
            print(yaml.dump(json_data, sort_keys=False), file=fd)
        else:
            print(utilities.json_dump(json_data), file=fd)
    return True


def write_objects(queue: Queue[types.ObjectJsonRepr], fd: TextIO, object_type: str, export_settings: types.ConfigSettings) -> None:
    """
    Thread to write projects in the JSON file
    """
    done = False
    prefix = ""
    log.info("Waiting %s to write...", object_type)
    objects_exported_as_lists = ("projects", "applications", "users", "portfolios")
    objects_exported_as_whole = ("qualityGates", "groups", "qualityProfiles")
    log.info("Waiting %s to write...", object_type)
    if object_type in objects_exported_as_lists:
        start, stop = ("[", "]")
    elif object_type in objects_exported_as_whole:
        start, stop = ("", "")
    else:
        start, stop = ("{", "}")
    print(f'"{object_type}": ' + start, file=fd)
    while not done:
        obj_json = queue.get()
        if not (done := obj_json is utilities.WRITE_END):
            if object_type == "groups":
                obj_json = __prep_json_for_write(obj_json, {**export_settings, EXPORT_EMPTY: True})
            else:
                obj_json = __prep_json_for_write(obj_json, export_settings)
            key = "" if isinstance(obj_json, list) else obj_json.get("key", obj_json.get("login", obj_json.get("name", "unknown")))
            log.debug("Writing %s key '%s'", object_type[:-1], key)
            if object_type in objects_exported_as_lists or object_type in objects_exported_as_whole:
                print(f"{prefix}{utilities.json_dump(obj_json)}", end="", file=fd)
            else:
                log.debug("Writing %s", object_type)
                print(f"{prefix}{utilities.json_dump(obj_json)[2:-1]}", end="", file=fd)
            prefix = ",\n"
        queue.task_done()
    print("\n" + stop, file=fd, end="")
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
            "SKIP_ISSUES": kwargs.get("skipIssues", False),
        }
    )
    if mode == "MIGRATION":
        export_settings |= _MIGRATION_EXPORT_SETTINGS
    log.info("Exporting with settings: %s", utilities.json_dump(export_settings, redact_tokens=True))
    if "projects" in what and kwargs[options.KEY_REGEXP]:
        if len(component_helper.get_components(endpoint, "projects", kwargs[options.KEY_REGEXP])) == 0:
            utilities.final_exit(errcodes.WRONG_SEARCH_CRITERIA, f"No projects matching regexp '{kwargs[options.KEY_REGEXP]}'")

    what.append(c.CONFIG_KEY_PLATFORM)
    log.info("Exporting configuration from %s", kwargs[options.URL])

    is_first = True
    write_q = Queue(maxsize=0)
    with utilities.open_file(file, mode="w") as fd:
        print("{", file=fd)
        for what_item, call_data in _EXPORT_CALLS.items():
            if what_item not in what:
                continue
            ndx, func = call_data
            if not is_first:
                print(",", file=fd)
            is_first = False
            worker = Thread(target=write_objects, args=(write_q, fd, ndx, export_settings))
            worker.daemon = True
            worker.name = f"Write{ndx[:1].upper()}{ndx[1:10]}"
            worker.start()
            try:
                func(endpoint, export_settings=export_settings, key_list=kwargs[options.KEY_REGEXP], write_q=write_q)
            except exceptions.UnsupportedOperation as e:
                log.warning(e.message)
                write_q and write_q.put(utilities.WRITE_END)
            write_q.join()
        print("\n}", file=fd)

    if file:
        __normalize_file(file, kwargs[options.FORMAT])
    else:
        log.info("Output is stdout, skipping normalization")
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
            json_data = utilities.clean_data(json_data, remove_empty=True)
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
        utilities.final_exit(errcodes.OS_ERROR, f"OS error while reading file: {e}")
    key_list = kwargs[options.KEY_REGEXP]

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


def convert_json(**kwargs) -> dict[str, Any]:
    """Converts a sonar-config report from the old to the new JSON format"""
    with open(kwargs["convertFrom"], encoding="utf-8") as fd:
        old_json = json.loads(fd.read())
    mapping = {
        "platform": pfhelp.convert_basics_json,
        "globalSettings": pfhelp.convert_global_settings_json,
        "qualityGates": qualitygates.convert_qgs_json,
        "qualityProfiles": qphelp.convert_qps_json,
        "projects": pjhelp.convert_projects_json,
        "portfolios": foliohelp.convert_portfolios_json,
        "applications": applications.convert_apps_json,
        "users": users.convert_users_json,
        "groups": groups.convert_groups_json,
        "rules": rhelp.convert_rules_json,
    }
    new_json = {}
    for k, func in mapping.items():
        if k in old_json:
            log.info("Converting %s", k)
            new_json[k] = func(old_json[k])
    new_json = __normalize_json(new_json, remove_empty=False, remove_none=True)
    with open(kwargs["convertTo"], mode="w", encoding="utf-8") as fd:
        print(utilities.json_dump(new_json), file=fd)
    return new_json


def main() -> None:
    """Main entry point for sonar-config"""
    start_time = utilities.start_clock()
    try:
        kwargs = utilities.convert_args(__parse_args("Extract SonarQube Server or Cloud platform configuration"))
        if kwargs["convertFrom"] is not None:
            convert_json(**kwargs)
            utilities.final_exit(errcodes.OK, "", start_time)
        endpoint = platform.Platform(**kwargs)
        endpoint.verify_connection()
        endpoint.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")

        if not kwargs[options.EXPORT] and not kwargs[options.IMPORT]:
            raise exceptions.SonarException(f"One of --{options.EXPORT} or --{options.IMPORT} option must be chosen", errcodes.ARGS_ERROR)

        what = utilities.check_what(kwargs.pop(options.WHAT, None), WHAT_EVERYTHING, "exported or imported")
        if options.WHAT_PROFILES in what and options.WHAT_RULES not in what:
            what.append(options.WHAT_RULES)
        kwargs[options.FORMAT] = utilities.deduct_format(kwargs[options.FORMAT], kwargs[options.REPORT_FILE], allowed_formats=("json", "yaml"))
        if kwargs[options.EXPORT]:
            export_config(endpoint, what, **kwargs)
        elif kwargs[options.IMPORT]:
            if kwargs["file"] is None:
                utilities.final_exit(errcodes.ARGS_ERROR, "--file is mandatory to import configuration")
            __import_config(endpoint, what, **kwargs)
    except exceptions.SonarException as e:
        utilities.final_exit(e.errcode, e.message)
    except (PermissionError, FileNotFoundError) as e:
        utilities.final_exit(errcodes.OS_ERROR, f"OS error while exporting config: {e}")

    utilities.final_exit(errcodes.OK, "", start_time)


if __name__ == "__main__":
    main()
