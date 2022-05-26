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
"""

    Abstraction of the SonarQube "application" concept

"""
import json
from sonar import env, measures, permissions
import sonar.sqobject as sq
import sonar.aggregations as aggr
import sonar.utilities as util
from sonar.audit import rules

_OBJECTS = {}
_GET_API = "applications/show"


class Application(aggr.Aggregation):
    def __init__(self, key, endpoint, data=None):
        super().__init__(key, endpoint)
        self._branches = None
        self._projects = None
        self._description = None
        self._load(data)
        _OBJECTS[key] = self

    def __str__(self):
        return f"application key '{self.key}'"

    def _load(self, data=None, api=None, key_name="application"):
        """Loads an object with contents of data"""
        super()._load(data=data, api=_GET_API, key_name="key")

    def _load_full(self):
        data = json.loads(env.get(_GET_API, ctxt=self.endpoint, params={"application": self.key}).text)
        self._json = data["application"]
        self._description = self._json.get("description", None)

    def projects(self):
        if self._projects is not None:
            return self._projects
        self._projects = []
        if "projects" not in self._json:
            self._load_full()
        for p in self._json["projects"]:
            self._projects.append({"key": p["key"], "branch": p["branch"]})
        return self._projects

    def branches(self):
        if self._branches is not None:
            return self._branches
        if "branches" not in self._json:
            self._load_full()
        params = {"application": self.key}
        self._branches = {}

        for br in self._json["branches"]:
            if not br["isMain"]:
                br.pop("isMain")
            b_name = br.pop("name")
            params["branch"] = b_name
            data = json.loads(self.get(_GET_API, params=params).text)
            br["projects"] = []
            for proj in data["application"]["projects"]:
                proj["projectKey"] = proj.pop("key")
                for k in ("selected", "name", "enabled", "isMain"):
                    proj.pop(k, None)
                br["projects"].append(proj)

            self._branches[b_name] = br

        return self._branches

    def delete(self, api="applications/delete", params=None):
        _ = env.post("applications/delete", ctxt=self.endpoint, params={"application": self.key})
        return True

    def _audit_empty(self, audit_settings):
        if not audit_settings["audit.applications.empty"]:
            util.logger.debug("Auditing empty applications is disabled, skipping...")
            return []
        return super()._audit_empty_aggregation(broken_rule=rules.RuleId.APPLICATION_EMPTY)

    def _audit_singleton(self, audit_settings):
        if not audit_settings["audit.applications.singleton"]:
            util.logger.debug("Auditing singleton applications is disabled, skipping...")
            return []
        return super()._audit_singleton_aggregation(broken_rule=rules.RuleId.APPLICATION_SINGLETON)

    def audit(self, audit_settings):
        util.logger.info("Auditing %s", str(self))
        return self._audit_empty(audit_settings) + self._audit_singleton(audit_settings)

    def get_measures(self, metrics_list):
        m = measures.get(self.key, metrics_list, endpoint=self.endpoint)
        if "ncloc" in m:
            self._ncloc = 0 if m["ncloc"] is None else int(m["ncloc"])
        return m

    def export(self):
        util.logger.info("Exporting %s", str(self))
        self._load_full()
        json_data = {
            "key": self.key,
            "name": self.name,
            "description": self._description,
            "visibility": self.visibility(),
            # 'projects': self.projects(),
            "branches": self.branches(),
            "permissions": permissions.export(self.endpoint, self.key),
        }
        return util.remove_nones(json_data)


def count(endpoint=None):
    resp = env.get(
        "api/components/search_projects",
        params={"ps": 1, "filter": "qualifier = APP"},
        ctxt=endpoint,
    )
    data = json.loads(resp.text)
    return data["paging"]["total"]


def search(params=None, endpoint=None):
    app_list = {}
    edition = env.edition(ctxt=endpoint)
    if edition == "community":
        util.logger.info("No applications in %s edition", edition)
    else:
        new_params = {"filter": "qualifier = APP"}
        if params is not None:
            new_params.update(params)
        app_list = sq.search_objects(
            api="api/components/search_projects",
            params=new_params,
            returned_field="components",
            key_field="key",
            object_class=Application,
            endpoint=endpoint,
        )
    return app_list


def get(key, sqenv=None):
    if key not in _OBJECTS:
        _OBJECTS[key] = Application(key=key, endpoint=sqenv)
    return _OBJECTS[key]


def audit(audit_settings, endpoint=None):
    if not audit_settings["audit.applications"]:
        util.logger.debug("Auditing applications is disabled, skipping...")
        return []
    util.logger.info("--- Auditing applications ---")
    objects_list = search(endpoint=endpoint)
    problems = []
    for _, obj in objects_list.items():
        problems += obj.audit(audit_settings)
    return problems
