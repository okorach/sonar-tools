#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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
    Exports rules
"""
import sys
import csv

from cli import options
import sonar.logging as log
from sonar import rules, platform, exceptions, errcodes, version
import sonar.utilities as util

TOOL_NAME = "sonar-rules"


def __parse_args(desc: str) -> object:
    """Sets and parses CLI arguments"""
    parser = options.set_common_args(desc)
    parser = options.set_output_file_args(parser, allowed_formats=("json", "csv"))
    parser = options.add_language_arg(parser, "rules")
    parser = options.add_import_export_arg(parser, "rules", import_opt=False)
    args = options.parse_and_check(parser=parser, logger_name=TOOL_NAME)
    return args


def __write_rules_csv(file: str, rule_list: dict[str, rules.Rule], separator: str = ",") -> None:
    """Writes a rule list in a CSV file (or stdout)"""
    with util.open_file(file) as fd:
        csvwriter = csv.writer(fd, delimiter=separator, quotechar='"', quoting=csv.QUOTE_MINIMAL)
        print("# ", file=fd, end="")
        if list(rule_list.values())[0].endpoint.version() >= (10, 2, 0):
            csvwriter.writerow(rules.CSV_EXPORT_FIELDS)
        else:
            csvwriter.writerow(rules.LEGACY_CSV_EXPORT_FIELDS)
        for rule in rule_list.values():
            csvwriter.writerow([str(x) for x in rule.to_csv()])


def __write_rules_json(file: str, rule_list: dict[str, rules.Rule]) -> None:
    """Writes a rule list in a JSON file (or stdout)"""
    with util.open_file(file) as fd:
        print("[", end="", file=fd)
        is_first = True
        for rule in rule_list.values():
            if not is_first:
                print(",", end="", file=fd)
            print(util.json_dump(rule.to_json()), file=fd)
            is_first = False
        print("\n]\n", file=fd)


def main() -> int:
    """Main entry point"""
    start_time = util.start_clock()
    try:
        kwargs = util.convert_args(__parse_args("Extract rules"))
        endpoint = platform.Platform(**kwargs)
        endpoint.verify_connection()
        endpoint.set_user_agent(f"{TOOL_NAME} {version.PACKAGE_VERSION}")
    except (options.ArgumentsError, exceptions.ObjectNotFound) as e:
        util.exit_fatal(e.message, e.errcode)
    file = kwargs[options.REPORT_FILE]
    fmt = util.deduct_format(kwargs[options.FORMAT], file)

    params = {"include_external": "false"}
    if options.LANGUAGES in kwargs:
        params["languages"] = kwargs[options.LANGUAGES]
    rule_list = rules.get_list(endpoint=endpoint, use_cache=False, **params)

    try:
        if fmt == "csv":
            __write_rules_csv(file=file, rule_list=rule_list, separator=kwargs[options.CSV_SEPARATOR])
        else:
            __write_rules_json(file=file, rule_list=rule_list)
    except (PermissionError, FileNotFoundError) as e:
        util.exit_fatal(f"OS error while projects export file: {e}", exit_code=errcodes.OS_ERROR)

    log.info("%d rules exported from %s", len(rule_list), endpoint.url)
    util.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
