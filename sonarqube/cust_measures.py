#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2021 Olivier Korach
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
    This script manipulates custom measures. You may:

    Update a custom measure value:
        Usage: cust_measures.py -t <SQ_TOKEN> -u <SQ_URL> -k <projectKey> -m <metricKey> --updateValue <value>
'''

import sonarqube.env
import sonarqube.custom_measures as cust_measures
import sonarqube.utilities as utils


def parse_args(desc):
    parser = utils.set_common_args(desc)
    parser = utils.set_component_args(parser)
    parser.add_argument('-m', '--metricKey', required=True, help='What custom metric to work on')
    parser.add_argument('--value', required=False, help='Updates the value of the metric')
    parser.add_argument('--description', required=False, help='Updates the description of the metric')
    return utils.parse_and_check_token(parser)


def main():
    args = parse_args('Manipulate custom metrics')
    sqenv = sonarqube.env.Environment(url=args.url, token=args.token)
    sonarqube.env.set_env(args.url, args.token)

    # Remove unset params from the dict
    params = vars(args)
    for key in params.copy():
        if params[key] is None:
            del params[key]
    # Add SQ environment
    params.update({'env': sqenv})

    if params.get('value', None) is not None:
        cust_measures.update(project_key=params['componentKeys'], metric_key=params['metricKey'],
            value=params['value'], description=params.get('description', None))

if __name__ == '__main__':
    main()
