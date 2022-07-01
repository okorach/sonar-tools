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
from http import HTTPStatus
from sonar import measures, components, options, settings
from sonar.projects import projects, branches
from sonar.permissions import application_permissions
import sonar.sqobject as sq
import sonar.aggregations as aggr
import sonar.utilities as util
from sonar.audit import rules

_OBJECTS = {}
_MAP = {}

_GET_API = "applications/show"
_CREATE_API = "applications/create"

_IMPORTABLE_PROPERTIES = ("key", "name", "description", "visibility", "branches", "permissions", "tags")


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
            resp = self.post(_CREATE_API, params={"key": self.key, "name": self.name, "visibility": create_data.get("visibility", None)})
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

    def permissions(self):
        if self._permissions is None:
            self._permissions = application_permissions.ApplicationPermissions(self)
        return self._permissions

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
            (pkey, bname) = (p["projectKey"], p["branch"]) if isinstance(p, dict) else (p, branch_data["projects"][p])
            o_proj = projects.get_object(pkey, self.endpoint)
            if not o_proj:
                util.logger.warning("Project '%s' not found, cannot add to %s branch", pkey, str(self))
                continue
            if bname == settings.DEFAULT_SETTING:
                bname = o_proj.main_branch().name
            if branches.exists(bname, pkey, self.endpoint):
                project_list.append(pkey)
                branch_list.append(bname)
            else:
                util.logger.warning("Branch '%s' not found, cannot add to %s branch", bname, str(self))

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
            br["projects"] = {}
            for proj in data["application"]["projects"]:
                br["projects"][proj["key"]] = proj["branch"]

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
        return self._audit_empty(audit_settings) + self._audit_singleton(audit_settings) + self._audit_bg_task(audit_settings)

    def get_measures(self, metrics_list):
        m = measures.get(self.key, metrics_list, endpoint=self.endpoint)
        if "ncloc" in m:
            self._ncloc = 0 if m["ncloc"] is None else int(m["ncloc"])
        return m

    def export(self, full=False):
        util.logger.info("Exporting %s", str(self))
        self._load_full()
        json_data = self._json.copy()
        json_data.update(
            {
                "key": self.key,
                "name": self.name,
                "description": None if self._description == "" else self._description,
                "visibility": self.visibility(),
                # 'projects': self.projects(),
                "branches": self.branches(),
                "permissions": self.permissions().export(),
                "tags": util.list_to_csv(self.tags(), separator=", "),
            }
        )
        return util.remove_nones(util.filter_export(json_data, _IMPORTABLE_PROPERTIES, full))

    def set_permissions(self, data):
        self.permissions().set(data.get("permissions", None))

    def set_tags(self, tags):
        if tags is None or len(tags) == 0:
            return
        if isinstance(tags, list):
            my_tags = util.list_to_csv(tags)
        else:
            my_tags = util.csv_normalize(tags)
        self.post("applications/set_tags", params={"application": self.key, "tags": my_tags})
        self._tags = util.csv_to_list(my_tags)

    def add_projects(self, project_list):
        current_projects = self.projects().keys()
        ok = True
        for proj in project_list:
            if proj in current_projects:
                util.logger.debug("Won't add project '%s' to %s, it's already added", proj, str(self))
                continue
            util.logger.debug("Adding project '%s' to %s", proj, str(self))
            r = self.post("applications/add_project", params={"application": self.key, "project": proj}, exit_on_error=False)
            if r.status_code == HTTPStatus.NOT_FOUND:
                util.logger.warning("Project '%s' not found, can't be added to %s", proj, self)
            else:
                ok = ok and r.ok
        return ok

    def update(self, data):
        self.set_permissions(data)
        self.add_projects(_project_list(data))
        self.set_tags(data.get("tags", None))
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
    if endpoint.edition() == "community":
        return {}
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
            endpoint=endpoint,
        )
    return app_list


def get_list(endpoint, key_list=None):
    if endpoint.edition() == "community":
        return {}
    if key_list is None or len(key_list) == 0:
        util.logger.info("Listing applications")
        return search(endpoint=endpoint)
    object_list = {}
    for key in util.csv_to_list(key_list):
        object_list[key] = get_object_by_key(key, endpoint=endpoint)
        if object_list[key] is None:
            raise options.NonExistingObjectError(key, f"Application key '{key}' does not exist")
    return object_list


def export(endpoint, key_list=None, full=False):
    apps_settings = {k: app.export(full) for k, app in get_list(endpoint, key_list).items()}
    for k in apps_settings:
        apps_settings[k].pop("key")
    return apps_settings


def audit(audit_settings, endpoint=None, key_list=None):
    if not audit_settings["audit.applications"]:
        util.logger.debug("Auditing applications is disabled, skipping...")
        return []
    util.logger.info("--- Auditing applications ---")
    problems = []
    for obj in get_list(endpoint, key_list=key_list).values():
        problems += obj.audit(audit_settings)
    return problems


def get_object(name, endpoint=None):
    # TODO - Don't re-read all apps every time a new app is searched
    if len(_OBJECTS) == 0 or name not in _MAP:
        get_list(endpoint)
    if name not in _MAP:
        return None
    return _OBJECTS[_MAP[name]]


def get_object_by_key(key, endpoint=None):
    if len(_OBJECTS) == 0:
        get_list(endpoint)
    if key not in _OBJECTS:
        return None
    return _OBJECTS[key]


def create(endpoint, name, key, data=None):
    if endpoint.edition() == "community":
        return None
    if key not in _OBJECTS:
        get_list(endpoint)
    o = _OBJECTS.get(key)
    if o is None:
        o = Application(endpoint=endpoint, name=name, key=key, create_data=data)
    else:
        util.logger.info("%s already exist, creation skipped", str(o))
    return o


def create_or_update(endpoint, name, key, data):
    if endpoint.edition() == "community":
        util.logger.warning("Can't create applications on a community edition")
        return
    if key not in _OBJECTS:
        get_list(endpoint)
    o = _OBJECTS.get(key, None)
    if o is None:
        util.logger.debug("Application key '%s' does not exist, creating...", key)
        o = create(name=name, key=key, endpoint=endpoint, data=data)
    o.update(data)


def import_config(endpoint, config_data, key_list=None):
    if "applications" not in config_data:
        util.logger.info("No applications to import")
        return
    if endpoint.edition() == "community":
        util.logger.warning("Can't be import applications in a community edition")
        return
    util.logger.info("Importing applications")
    search(endpoint=endpoint)
    new_key_list = util.csv_to_list(key_list)
    for key, data in config_data["applications"].items():
        if new_key_list and key not in new_key_list:
            continue
        util.logger.info("Importing application key '%s'", key)
        create_or_update(endpoint=endpoint, name=data["name"], key=key, data=data)


def search_by_name(endpoint, name):
    return util.search_by_name(endpoint, name, components.SEARCH_API, "components", extra_params={"qualifiers": "APP"})
