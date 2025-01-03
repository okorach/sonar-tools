#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2024-2025 Olivier Korach
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

from cli import options, config
from sonar import exceptions, errcodes, utilities, version
import sonar.util.constants as c
import sonar.logging as log
from sonar import platform

TOOL_NAME = "sonar-migration"


def __parse_args(desc: str) -> object:
    """Defines CLI arguments and parses them"""
    parser = options.set_common_args(desc)
    parser = options.set_key_arg(parser)
    parser = options.set_output_file_args(parser, allowed_formats=("json",))
    parser = options.add_thread_arg(parser, "migration export")
    parser = options.set_what(parser, what_list=config.WHAT_EVERYTHING, operation="export")
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
    args = options.parse_and_check(parser=parser, logger_name=TOOL_NAME, is_migration=True)
    return args


def main() -> None:
    """Main entry point for sonar-config"""
    start_time = utilities.start_clock()
    try:
        kwargs = utilities.convert_args(__parse_args("Extract SonarQube to SonarCloud migration data"))
        endpoint = platform.Platform(**kwargs)
        endpoint.verify_connection()
        endpoint.set_user_agent(f"{TOOL_NAME} {version.MIGRATION_TOOL_VERSION}")
    except (options.ArgumentsError, exceptions.ObjectNotFound) as e:
        utilities.exit_fatal(e.message, e.errcode)

    what = utilities.check_what(kwargs.pop(options.WHAT, None), config.WHAT_EVERYTHING, "exported")
    if options.WHAT_PROFILES in what and options.WHAT_RULES not in what:
        what.append(options.WHAT_RULES)
    kwargs[options.FORMAT] = "json"
    if kwargs[options.REPORT_FILE] is None:
        kwargs[options.REPORT_FILE] = f"sonar-migration.{endpoint.server_id()}.json"
    try:
        config.export_config(endpoint, what, mode="MIGRATION", **kwargs)
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
