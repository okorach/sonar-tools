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
'''
    Exports SonarQube platform configuration as JSON
'''
import sys
from sonar import env, version, settings, devops, projects, qualityprofiles, qualitygates
import sonar.utilities as util

"""
def __open_output(file):
    if file is None:
        fd = sys.stdout
        util.logger.info("Dumping report to stdout")
    else:
        fd = open(file, "w", encoding='utf-8')
        util.logger.info("Dumping report to file '%s'", file)
    return fd


def __close_output(file, fd):
    if file is not None:
        fd.close()
        util.logger.info("File '%s' generated", file)
"""

def __parse_args(desc):
    parser = util.set_common_args(desc)
    parser = util.set_project_args(parser)
    parser = util.set_output_file_args(parser)
    args = util.parse_and_check_token(parser)
    util.check_environment(vars(args))
    util.logger.info('sonar-tools version %s', version.PACKAGE_VERSION)
    return args


def main():
    args = __parse_args('Extract SonarQube platform configuration')
    endpoint = env.Environment(some_url=args.url, some_token=args.token)

    platform_settings = endpoint.settings(include_not_set=True)
    platform_settings[settings.DEVOPS_INTEGRATION] = list(devops.settings(endpoint).values())
    platform_settings['qualityProfiles'] = qualityprofiles.get_list(endpoint, include_rules=True)
    platform_settings['qualityGates'] = qualitygates.get_list(endpoint, as_json=True)
    project_settings = {}
    for p in projects.get_projects_list(str_key_list=None, endpoint=endpoint).values():
        project_settings[p.key] = p.settings()
    print(util.json_dump({'platform': platform_settings, 'projects': project_settings}))
    nbr_settings = len(platform_settings)
    for categ in settings.CATEGORIES:
        if categ in platform_settings:
            nbr_settings += len(platform_settings[categ]) - 1
    util.logger.info("Exported %s settings", nbr_settings)
    sys.exit(0)


if __name__ == '__main__':
    main()
