#!/usr/local/bin/python3
#
# sonar-tools
# Copyright (C) 2019-2020 Olivier Korach
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

Collects the history of metrics of a project

'''

import json
import requests

# Mandatory script input parameters
root_url = 'http://localhost:9000/'
token = '3d2e0b9797f75c0ccd55e082808ac17005c3f49f'
credentials = (token, '')
csv_sep = ";"

metrics = 'ncloc,new_violations,new_bugs,complexity,coverage,sqale_index'
key = 'org.sonarsource.java:java'
print("date" + csv_sep + metrics.replace(",", csv_sep))

metrics_list = metrics.split(",")

params = dict(component=key, metrics=metrics, ps=1000)
resp = requests.get(url=root_url + 'api/measures/search_history', auth=credentials, params=params)
data = json.loads(resp.text)
all_measures = data['measures']
line = key + csv_sep
p_meas = {}
for measure in all_measures:
    if 'metric' not in measure:
        continue
    p_meas[measure['metric']] = measure['value'] if 'value' in measure else ""
for measure in metrics_list:
    line = line + csv_sep
    if measure in p_meas:
        line = line + p_meas[measure]

    print(line)
