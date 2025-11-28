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
"""

Exports/Imports all projects of a SonarQube Server platform

"""

import json

from requests import RequestException

from cli import options
import sonar.logging as log
from sonar import errcodes, exceptions, utilities, version
from sonar import platform, projects
import sonar.util.constants as c
import sonar.util.common_helper as chelp

TOOL_NAME = "sonar-projects"

_EXPORT_IMPORT_TIMEOUT = 180
_EXPORT_IMPORT_THREADS = 1


def __export_projects(endpoint: platform.Platform, **kwargs) -> None:
    """Exports a list (or all) of projects into zip files"""
    ed = endpoint.edition()
    if ed == "sonarcloud":
        raise exceptions.UnsupportedOperation("Can't export projects on SonarQube Cloud, aborting...")
    if ed in (c.CE, c.DE) and endpoint.version()[:2] < (9, 2):
        raise exceptions.UnsupportedOperation(f"Can't export projects on {ed} Edition before 9.2, aborting...")
    dump = projects.export_zips(
        endpoint=endpoint,
        key_regexp=kwargs[options.KEY_REGEXP],
        export_timeout=kwargs.get("exportTimeout", _EXPORT_IMPORT_TIMEOUT),
        threads=kwargs.get(options.NBR_THREADS, _EXPORT_IMPORT_THREADS),
        skip_zero_loc=kwargs.get("skipZeroLoc", False),
    )
    if len(dump) == 0:
        raise exceptions.ObjectNotFound(kwargs[options.KEY_REGEXP], "No project found matching the given key regexp")
    export_data = {
        "exportSonarqubeEnvironment": {
            "url": endpoint.url(),
            "version": ".".join([str(n) for n in endpoint.version()[:2]]),
            "plugins": endpoint.plugins(),
        },
        "projects": dump,
    }

    with utilities.open_file(kwargs[options.REPORT_FILE]) as fd:
        print(utilities.json_dump(export_data), file=fd)


def __import_projects(endpoint: platform.Platform, **kwargs) -> None:
    """Imports a list of projects in SonarQube Server EE+"""
    file = kwargs[options.REPORT_FILE]
    if not file:
        raise options.ArgumentsError(f"Option --{options.REPORT_FILE} is mandatory to import")
    try:
        with open(file, "r", encoding="utf-8") as fd:
            data = json.load(fd)
    except json.JSONDecodeError as e:
        raise options.ArgumentsError(f"JSON decoding error while reading file '{file}': {str(e)}")

    if "projects" in data:
        # 3.13 and higher format
        key, status_key = "projects", "exportStatus"
    else:
        # 3.12 and lower format
        key, status_key = "project_exports", "status"
    project_list = [projdata for projdata in data[key] if projdata.get(status_key, "").startswith("SUCCESS")]
    log.info("Skipping import of %d projects since export was failed or skipped", len(data[key]) - len(project_list))
    if kwargs.get("skipZeroLoc", False):
        raw_count = len(project_list)
        project_list = [
            projdata
            for projdata in data[key]
            if projdata.get(status_key, "").startswith("SUCCESS") and "ZERO_LOC" not in projdata.get(status_key, "")
        ]
        log.info("Skipping import of %d projects since they have 0 LoC", raw_count - len(project_list))

    statuses = projects.import_zips(
        endpoint,
        project_list,
        kwargs.get(options.NBR_THREADS, _EXPORT_IMPORT_THREADS),
        import_timeout=kwargs.get("exportTimeout", _EXPORT_IMPORT_TIMEOUT),
    )
    for proj in data[key]:
        if proj["key"] in statuses:
            proj.update(statuses[proj["key"]])
        else:
            for k in ("importStatus", "importDate", "importProjectUrl"):
                proj.pop(k, None)
    data["importSonarqubeEnvironment"] = {
        "url": endpoint.url(),
        "version": ".".join([str(n) for n in endpoint.version()[:2]]),
        "plugins": endpoint.plugins(),
    }
    with open(file, "w", encoding="utf-8") as fd:
        print(utilities.json_dump(data), file=fd)


def main() -> None:
    """Main entry point of sonar-projects"""
    start_time = utilities.start_clock()
    try:
        parser = options.set_common_args("Exports/Imports all projects of a SonarQube Server platform")
        parser = options.set_key_arg(parser)
        parser = options.add_import_export_arg(parser, "projects zip")
        parser = options.set_output_file_args(parser, allowed_formats=("json",))
        parser = options.add_thread_arg(parser, "projects zip export/import", default_value=_EXPORT_IMPORT_THREADS)
        parser.add_argument(
            "--exportTimeout",
            "--importTimeout",
            required=False,
            type=int,
            default=_EXPORT_IMPORT_TIMEOUT,
            help=f"Maximum wait time for export or import of a project (default {_EXPORT_IMPORT_TIMEOUT} seconds)",
        )
        parser.add_argument(
            "--skipZeroLoc",
            action="store_true",
            default=False,
            required=False,
            help="Skips export or import of projects with zero lines of code",
        )
        kwargs = utilities.convert_args(options.parse_and_check(parser=parser, logger_name=TOOL_NAME))
        sq = platform.Platform(**kwargs)
        sq.verify_connection()
        sq.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")

        if kwargs[options.EXPORT]:
            __export_projects(sq, **kwargs)
        elif kwargs[options.IMPORT]:
            __import_projects(sq, **kwargs)
        else:
            raise options.ArgumentsError(f"One of --{options.EXPORT} or --{options.IMPORT} option must be chosen")
    except (PermissionError, FileNotFoundError) as e:
        chelp.clear_cache_and_exit(errcodes.OS_ERROR, f'OS error while {"importing" if kwargs[options.IMPORT] else "exporting"} projects zip: {e}')
    except exceptions.SonarException as e:
        chelp.clear_cache_and_exit(e.errcode, e.message)
    except RequestException as e:
        chelp.clear_cache_and_exit(errcodes.SONAR_API, f'HTTP error while {"importing" if kwargs[options.IMPORT] else "exporting"} projects zip: {e}')
    chelp.clear_cache_and_exit(errcodes.OK, start_time=start_time)


if __name__ == "__main__":
    main()
