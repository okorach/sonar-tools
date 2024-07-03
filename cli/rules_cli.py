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
from sonar import rules, platform
import sonar.utilities as util


def __parse_args(desc: str) -> object:
    """Sets and parses CLI arguments"""
    parser = options.set_common_args(desc)
    parser = options.set_output_file_args(parser)
    parser = options.add_language_arg(parser, "rules")
    parser = options.add_import_export_arg(parser, "rules", import_opt=False)
    args = options.parse_and_check(parser=parser, logger_name="sonar-rules")
    return args


def main() -> int:
    """Main entry point"""
    start_time = util.start_clock()
    kwargs = util.convert_args(__parse_args("Extract rules"))
    endpoint = platform.Platform(**kwargs)
    file = kwargs[options.OUTPUTFILE]
    fmt = util.deduct_format(kwargs[options.FORMAT], file)

    params = {}
    if options.LANGUAGES in kwargs:
        params = {"languages": util.list_to_csv(kwargs[options.LANGUAGES])}
    rule_list = rules.get_list(endpoint=endpoint, **params)

    with util.open_file(file) as fd:
        if fmt == "json":
            print("[", end="", file=fd)
        elif fmt == "csv":
            csvwriter = csv.writer(fd, delimiter=kwargs[options.CSV_SEPARATOR], quotechar='"', quoting=csv.QUOTE_MINIMAL)
        is_first = True
        for rule in rule_list.values():
            if fmt == "csv":
                csvwriter.writerow([str(x) for x in rule.to_csv()])
            elif fmt == "json":
                if not is_first:
                    print(",", end="", file=fd)
                print(util.json_dump(rule.to_json()), file=fd)
                is_first = False
        if fmt == "json":
            print("\n]\n", file=fd)

    log.info("%d rules exported", len(rule_list))
    util.stop_clock(start_time)
    sys.exit(0)


if __name__ == "__main__":
    main()
