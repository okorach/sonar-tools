#!/usr/local/bin/python
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
