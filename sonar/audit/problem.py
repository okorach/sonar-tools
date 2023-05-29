#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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

import csv
from sonar import utilities, options


class Problem:
    def __init__(self, problem_type, severity, msg, concerned_object=None):
        # dict.__init__(type=problem_type, severity=severity, message=msg)
        self.concerned_object = concerned_object
        self.type = problem_type
        self.severity = severity
        self.message = msg
        utilities.logger.warning(msg)

    def __str__(self):
        return f"Type: {self.type} - Severity: {self.severity} - Description: {self.message}"

    def to_json(self, with_url=False):
        d = vars(self).copy()
        d.pop("concerned_object")
        for k in ("severity", "type"):
            d[k] = str(d[k])
        if with_url:
            try:
                d["url"] = self.concerned_object.url()
            except AttributeError:
                d["url"] = str(self.concerned_object)
        return d


def dump_report(problems, file, **kwargs):
    utilities.logger.info("Writing report to %s", f"file '{file}'" if file else "stdout")
    if kwargs.get("format", "csv") == "json":
        __dump_json(problems=problems, file=file, **kwargs)
    else:
        __dump_csv(problems=problems, file=file, **kwargs)


def __dump_csv(problems, file, **kwargs):
    with utilities.open_file(file, "w") as fd:
        csvwriter = csv.writer(fd, delimiter=kwargs.get("separator", ","))
        for p in problems:
            csvwriter.writerow(list(p.to_json(kwargs.get(options.WITH_URL, False)).values()))


def __dump_json(problems, file, **kwargs):
    json = [p.to_json(kwargs.get(options.WITH_URL, False)) for p in problems]
    with utilities.open_file(file) as fd:
        print(utilities.json_dump(json), file=fd)
