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
from sonar import measures, permissions, components, branches, projects
import sonar.sqobject as sq
import sonar.aggregations as aggr
import sonar.utilities as util
from sonar.audit import rules

_OBJECTS = {}
_MAP = {}

_GET_API = "applications/show"
_CREATE_API = "applications/create"

class Application(aggr.Aggregation):
    def __init__(self, key, endpoint, data=None, name=None, create_data=None):
        super().__init__(key, endpoint)
        self._branches = None
        self._projects = None
        self._description = None
        if create_data is not None:
            self.name = name
            util.logger.info("Creating %s", str(self))
            util.logger.debug("from %s", util.json_dump(create_data))
            resp = self.post(
                _CREATE_API, params={"key": self.key, "name": self.name, "visibility": create_data.get("visibility", None)}
            )
            self.key = json.loads(resp.text)["application"]["key"]
            self._load(api=_GET_API, key_name="application")
            self.key = key
        else:
            self._load(api=_GET_API, data=data)
        util.logger.debug("Created %s", str(self))
        _OBJECTS[self.key] = self
        _MAP[self.name] = self.key

    def __str__(self):
        return f"application key '{self.key}'"

    def _load_full(self):
        data = json.loads(self.get(_GET_API, params={"application": self.key}).text)
        self._json = data["application"]
        self._description = self._json.get("description", None)

    def projects(self):
        if self._projects is not None:
            return self._projects
        self._projects = {}
        if "projects" not in self._json:
            self._load_full()
        for p in self._json["projects"]:
            self._projects[p["key"]] = p["branch"]
        return self._projects

    def branch_exists(self, branch):
        return branch in self.branches()

    def branch_is_main(self, branch):
        return branch in self.branches() and self._branches[branch]["isMain"]

    def set_branch(self, branch_name, branch_data):
        project_list, branch_list = [], []
        for p in branch_data.get("projects", []):
            if isinstance(p, dict):
                pkey = p["projectKey"]
                bname = p["branch"]
            else:
                pkey = p
                bname = branch_data["projects"][p]
            if projects.exists(pkey, self.endpoint) and branches.exists(bname, pkey, self.endpoint):
                project_list.append(pkey)
                br_obj = branches.get_object(bname, pkey, self.endpoint)
                branch_list.append("" if br_obj.is_main() else bname)
            else:
                util.logger.warning("Branch '%s' or project '%s' does not exist, cannot create application branch", bname, pkey)

        if len(project_list) > 0:
            params = {"application": self.key, "branch": branch_name, "project": project_list, "projectBranch": branch_list}
            api = "applications/create_branch"
            if self.branch_exists(branch_name):
                api = "applications/update_branch"
                params["name"] = params["branch"]
            self.post(api, params=params)

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
        _ = self.post("applications/delete", params={"application": self.key})
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

    def set_permissions(self, data):
        permissions.set_permissions(self.endpoint, data.get("permissions", None), project_key=self.key)

    def add_projects(self, project_list):
        current_projects = self.projects().keys()
        for proj in project_list:
            if proj in current_projects:
                util.logger.info("Won't add project '%s' to %s, it's already added", proj, str(self))
                continue
            util.logger.info("Adding project '%s' to %s", proj, str(self))
            self.post("applications/add_project", params={"application": self.key, "project": proj})

    def update(self, data):
        self.set_permissions(data)
        self.add_projects(_project_list(data))
        for name, branch_data in data.get("branches", {}).items():
            self.set_branch(name, branch_data)


def _project_list(data):
    plist = {}
    for b in data.get("branches", {}).values():
        if isinstance(b["projects"], dict):
            plist.update(b["projects"])
        else:
            for p in b["projects"]:
                plist[p["projectKey"]] = ""
    return plist.keys()


def count(endpoint=None):
    data = json.loads(endpoint.get(components.SEARCH_API, params={"ps": 1, "filter": "qualifier = APP"}))
    return data["paging"]["total"]


def search(endpoint, params=None):
    app_list = {}
    edition = endpoint.edition()
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
            endpoint=endpoint
        )
    return app_list


def get_list(endpoint):
    return search(endpoint=endpoint)


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


def get_object(name, endpoint=None):
    if len(_OBJECTS) == 0 or name not in _MAP:
        get_list(endpoint)
    if name not in _MAP:
        return None
    return _OBJECTS[_MAP[name]]


def create(endpoint, name, key, data=None):
    if key not in _OBJECTS:
        get_list(endpoint)
    o = _OBJECTS.get(key)
    if o is None:
        o = Application(endpoint=endpoint, name=name, key=key, create_data=data)
    else:
        util.logger.info("%s already exist, creation skipped", str(o))
    return o


def create_or_update(endpoint, name, key, data):
    if key not in _OBJECTS:
        get_list(endpoint)
    o = _OBJECTS.get(key, None)
    if o is None:
        util.logger.debug("Application key '%s' does not exist, creating...", key)
        o = create(name=name, key=key, endpoint=endpoint, data=data)
    o.update(data)


def import_config(endpoint, config_data):
    if "applications" not in config_data:
        util.logger.info("No applications to import")
        return
    util.logger.info("Importing applications")
    search(endpoint=endpoint)
    for key, data in config_data["applications"].items():
        util.logger.info("Importing application key '%s'", key)
        create_or_update(endpoint=endpoint, name=data["name"], key=key, data=data)

def search_by_name(endpoint, name):
    return util.search_by_name(endpoint, name, components.SEARCH_API, "components", extra_params={"qualifiers": "APP"})
