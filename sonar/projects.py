#
# sonar-tools
# Copyright (C) 2019-2022 Olivier Korach
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

    Abstraction of the SonarQube "project" concept

"""
import datetime
import re
import json
from http import HTTPStatus
import pytz
from sonar import sqobject, components, qualitygates, qualityprofiles, tasks, options, settings, webhooks, devops
from sonar import pull_requests, branches, measures, custom_measures
from sonar.findings import issues, hotspots
import sonar.utilities as util
import sonar.permissions as perms

from sonar.audit import rules, severities
import sonar.audit.problem as pb

_OBJECTS = {}

MAX_PAGE_SIZE = 500
_SEARCH_API = "projects/search"
_CREATE_API = "projects/create"
PRJ_QUALIFIER = "TRK"
APP_QUALIFIER = "APP"

_BIND_SEP = ":::"


class Project(components.Component):
    def __init__(self, key, endpoint=None, data=None, create_data=None):
        super().__init__(key, endpoint)
        self.main_branch_last_analysis_date = "undefined"
        self.all_branches_last_analysis_date = "undefined"
        self._permissions = None
        self.branches = None
        self.pull_requests = None
        self._ncloc_with_branches = None
        self._binding = {"has_binding": True, "binding": None}
        super().__init__(key, endpoint)
        if create_data is not None:
            util.logger.info("Creating %s", str(self))
            util.logger.debug("from %s", util.json_dump(create_data))
            self.post(
                _CREATE_API, params={"project": self.key, "name": create_data.get("name", None), "visibility": create_data.get("visibility", None)}
            )
            self.__load()
        else:
            self.__load(data)
        _OBJECTS[key] = self
        util.logger.debug("Created %s", str(self))

    def __str__(self):
        return f"project '{self.key}'"

    def __load(self, data=None):
        """Loads a project object with contents of an api/projects/search call"""
        if data is None:
            data = json.loads(self.get(_SEARCH_API, params={"projects": self.key}).text)
            if not data["components"]:
                raise options.NonExistingObjectError(self.key, "Project key does not exist")
            data = data["components"][0]
        self.name = data["name"]
        self._visibility = data["visibility"]
        if "lastAnalysisDate" in data:
            self.main_branch_last_analysis_date = util.string_to_date(data["lastAnalysisDate"])
        else:
            self.main_branch_last_analysis_date = None
        self.revision = data.get("revision", None)

    def url(self):
        return f"{self.endpoint.url}/dashboard?id={self.key}"

    def last_analysis_date(self, include_branches=False):
        if self.main_branch_last_analysis_date == "undefined":
            self.__load()
        if not include_branches:
            return self.main_branch_last_analysis_date
        if self.all_branches_last_analysis_date != "undefined":
            return self.all_branches_last_analysis_date

        self.all_branches_last_analysis_date = self.main_branch_last_analysis_date
        if self.endpoint.version() >= (9, 2, 0):
            # Starting from 9.2 project last analysis date takes into account branches and PR
            return self.all_branches_last_analysis_date

        for b in self.get_branches() + self.get_pull_requests():
            if b.last_analysis_date() is None:
                continue
            b_ana_date = b.last_analysis_date()
            if self.all_branches_last_analysis_date is None or b_ana_date > self.all_branches_last_analysis_date:
                self.all_branches_last_analysis_date = b_ana_date
        return self.all_branches_last_analysis_date

    def ncloc_with_branches(self):
        if self._ncloc_with_branches is not None:
            return self._ncloc_with_branches
        self._ncloc_with_branches = self.ncloc()
        if self.endpoint.edition() != "community":
            for b in self.get_branches() + self.get_pull_requests():
                if b.ncloc() > self._ncloc_with_branches:
                    self._ncloc_with_branches = b.ncloc()
        return self._ncloc_with_branches

    def get_measures(self, metrics_list):
        m = measures.get(self.key, metrics_list, endpoint=self.endpoint)
        if "ncloc" in m:
            self._ncloc = 0 if m["ncloc"] is None else int(m["ncloc"])
        return m

    def get_branches(self, include_main=True):
        if self.endpoint.edition() == "community":
            util.logger.debug("Branches not available in Community Edition")
            return []

        if self.branches is None:
            data = json.loads(self.get("project_branches/list", params={"project": self.key}).text)
            self.branches = []
            for b in data["branches"]:
                if b.get("isMain", False) and not include_main:
                    continue
                self.branches.append(branches.get_object(b["name"], self, data=b, endpoint=self.endpoint))
        return self.branches

    def get_pull_requests(self):
        if self.endpoint.edition() == "community":
            util.logger.debug("Pull requests not available in Community Edition")
            return []

        if self.pull_requests is None:
            data = json.loads(
                self.get(
                    "project_pull_requests/list",
                    params={"project": self.key},
                ).text
            )
            self.pull_requests = []
            for p in data["pullRequests"]:
                self.pull_requests.append(pull_requests.get_object(p["key"], self, p))
        return self.pull_requests

    def delete(self, api="projects/delete", params=None):
        loc = int(self.get_measure("ncloc", fallback="0"))
        util.logger.info("Deleting %s, name '%s' with %d LoCs", str(self), self.name, loc)
        if not super().post("projects/delete", params={"project": self.key}):
            util.logger.error("%s deletion failed", str(self))
            return False
        util.logger.info("Successfully deleted %s - %d LoCs", str(self), loc)
        return True

    def has_binding(self):
        _ = self.binding()
        return self._binding["has_binding"]

    def binding(self):
        if self._binding["has_binding"] and self._binding["binding"] is None:
            resp = self.get("alm_settings/get_binding", params={"project": self.key}, exit_on_error=False)
            # Hack: 8.9 returns 404, 9.x returns 400
            if resp.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
                self._binding["has_binding"] = False
            elif resp.ok:
                self._binding["has_binding"] = True
                self._binding["binding"] = json.loads(resp.text)
            else:
                util.exit_fatal(
                    f"alm_settings/get_binding returning status code {resp.status_code}, exiting",
                    options.ERR_SONAR_API,
                )
        return self._binding["binding"]

    def is_part_of_monorepo(self):
        if self.binding() is None:
            return False
        return self.binding()["monorepo"]

    def binding_key(self):
        p_bind = self.binding()
        if p_bind is None:
            return None
        key = p_bind["alm"] + _BIND_SEP + p_bind["repository"]
        if p_bind["alm"] in ("azure", "bitbucket"):
            key += _BIND_SEP + p_bind["slug"]
        return key

    def age_of_last_analysis(self):
        today = datetime.datetime.today().replace(tzinfo=pytz.UTC)
        last_analysis = self.last_analysis_date(include_branches=True)
        if last_analysis is None:
            return None
        return abs(today - last_analysis).days

    def __audit_user_permissions__(self, audit_settings):
        problems = []
        user_count = self.permissions().count("users")
        max_users = audit_settings["audit.projects.permissions.maxUsers"]
        if user_count > max_users:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_USERS)
            msg = rule.msg.format(str(self), user_count)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_admins = audit_settings["audit.projects.permissions.maxAdminUsers"]
        admin_count = self.permissions().count("users", ("admin"))
        if admin_count > max_admins:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ADM_USERS)
            msg = rule.msg.format(str(self), admin_count, max_admins)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        return problems

    def __audit_group_permissions__(self, audit_settings):
        problems = []
        groups = counts = self.permissions().read().to_json(perm_type="groups")
        for gr_name, gr_perms in groups.items():
            # -- Checks for Anyone, sonar-user
            if gr_name not in ("Anyone", "sonar-users"):
                continue
            if "issueadmin" in gr_perms or "scan" in gr_perms or "securityhotspotadmin" in gr_perms or "admin" in gr_perms:
                if gr_name == "Anyone":
                    rule = rules.get_rule(rules.RuleId.PROJ_PERM_ANYONE)
                else:
                    rule = rules.get_rule(rules.RuleId.PROJ_PERM_SONAR_USERS_ELEVATED_PERMS)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg.format(gr_name, str(self)), concerned_object=self))
            else:
                util.logger.info("Group '%s' has browse permissions on %s. Is this normal ?", gr_name, str(self))

        max_perms = audit_settings["audit.projects.permissions.maxGroups"]
        counter = self.permissions().count(perm_type="groups", perm_filter=perms.PROJECT_PERMISSIONS)
        if counter > max_perms:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_GROUPS)
            msg = rule.msg.format(str(self), counter, max_perms)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_scan = audit_settings["audit.projects.permissions.maxScanGroups"]
        counter = self.permissions().count(perm_type="groups", perm_filter=("scan"))
        if counter > max_scan:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_SCAN_GROUPS)
            msg = rule.msg.format(str(self), counts["scan"], max_scan)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_issue_adm = audit_settings["audit.projects.permissions.maxIssueAdminGroups"]
        counter = self._permissions.count(perm_type="groups", perm_filter=("issueadmin"))
        if counter > max_issue_adm:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ISSUE_ADM_GROUPS)
            msg = rule.msg.format(str(self), counts["issueadmin"], max_issue_adm)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_spots_adm = audit_settings["audit.projects.permissions.maxHotspotAdminGroups"]
        counter = self._permissions.count(perm_type="groups", perm_filter=("securityhotspotadmin"))
        if counter > max_spots_adm:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_HOTSPOT_ADM_GROUPS)
            msg = rule.msg.format(str(self), counter, max_spots_adm)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_admins = audit_settings["audit.projects.permissions.maxAdminGroups"]
        counter = self._permissions.count(perm_type="groups", perm_filter=("admin"))
        if counter > max_admins:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ADM_GROUPS)
            msg = rule.msg.format(str(self), counter, max_admins)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
        return problems

    def __audit_permissions__(self, audit_settings):
        if not audit_settings["audit.projects.permissions"]:
            util.logger.debug("Auditing project permissions is disabled by configuration, skipping")
            return []
        util.logger.debug("Auditing %s permissions", str(self))
        problems = self.__audit_user_permissions__(audit_settings) + self.__audit_group_permissions__(audit_settings)
        if not problems:
            util.logger.debug("No issue found in %s permissions", str(self))
        return problems

    def __audit_last_analysis__(self, audit_settings):
        util.logger.debug("Auditing %s last analysis date", str(self))
        problems = []
        age = self.age_of_last_analysis()
        if age is None:
            if not audit_settings["audit.projects.neverAnalyzed"]:
                util.logger.debug("Auditing of never analyzed projects is disabled, skipping")
            else:
                rule = rules.get_rule(rules.RuleId.PROJ_NOT_ANALYZED)
                msg = rule.msg.format(str(self))
                problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
            return problems

        max_age = audit_settings["audit.projects.maxLastAnalysisAge"]
        if max_age == 0:
            util.logger.debug("Auditing of projects with old analysis date is disabled, skipping")
        elif age > max_age:
            rule = rules.get_rule(rules.RuleId.PROJ_LAST_ANALYSIS)
            severity = severities.Severity.HIGH if age > 365 else rule.severity
            loc = self.get_measure("ncloc", fallback="0")
            msg = rule.msg.format(str(self), loc, age)
            problems.append(pb.Problem(rule.type, severity, msg, concerned_object=self))

        util.logger.debug("%s last analysis is %d days old", str(self), age)
        return problems

    def __audit_branches(self, audit_settings):
        if not audit_settings["audit.projects.branches"]:
            util.logger.debug("Auditing of branchs is disabled, skipping...")
            return []
        util.logger.debug("Auditing %s branches", str(self))
        problems = []
        for branch in self.get_branches():
            problems += branch.audit(audit_settings)
        return problems

    def __audit_pull_requests(self, audit_settings):
        max_age = audit_settings["audit.projects.pullRequests.maxLastAnalysisAge"]
        if max_age == 0:
            util.logger.debug("Auditing of pull request last analysis age is disabled, skipping...")
            return []
        problems = []
        for pr in self.get_pull_requests():
            problems += pr.audit(audit_settings)
        return problems

    def __audit_visibility__(self, audit_settings):
        if not audit_settings.get("audit.projects.visibility", True):
            util.logger.debug("Project visibility audit is disabled by configuration, skipping...")
            return []
        util.logger.debug("Auditing %s visibility", str(self))
        if self.visibility() != "private":
            rule = rules.get_rule(rules.RuleId.PROJ_VISIBILITY)
            return [
                pb.Problem(
                    rule.type,
                    rule.severity,
                    rule.msg.format(str(self), self.visibility()),
                    concerned_object=self,
                )
            ]

        util.logger.debug("%s visibility is 'private'", str(self))
        return []

    def __audit_languages__(self, audit_settings):
        if not audit_settings.get("audit.xmlLoc.suspicious", False):
            util.logger.debug("XML LoCs count audit disabled by configuration, skipping")
            return []
        util.logger.debug("Auditing %s suspicious XML LoC count", str(self))

        total_locs = 0
        languages = {}
        resp = self.get_measure("ncloc_language_distribution")
        if resp is None:
            return []
        for lang in self.get_measure("ncloc_language_distribution").split(";"):
            (lang, ncloc) = lang.split("=")
            languages[lang] = int(ncloc)
            total_locs += int(ncloc)
        if total_locs > 100000 and "xml" in languages and (languages["xml"] / total_locs) > 0.5:
            rule = rules.get_rule(rules.RuleId.PROJ_XML_LOCS)
            return [
                pb.Problem(
                    rule.type,
                    rule.severity,
                    rule.format(str(self), languages["xml"]),
                    concerned_object=self,
                )
            ]
        util.logger.debug("%s XML LoCs count seems reasonable", str(self))
        return []

    def __audit_bg_tasks(self, audit_settings):
        last_task = tasks.search_last(component_key=self.key, endpoint=self.endpoint)
        if last_task is not None:
            return last_task.audit(audit_settings)
        return []

    def __audit_zero_loc(self, audit_settings):
        if (
            (not audit_settings["audit.projects.branches"] or self.endpoint.edition() == "community")
            and self.last_analysis_date() is not None
            and self.ncloc() == 0
        ):
            rule = rules.get_rule(rules.RuleId.PROJ_ZERO_LOC)
            return [
                pb.Problem(
                    rule.type,
                    rule.severity,
                    rule.msg.format(str(self)),
                    concerned_object=self,
                )
            ]
        return []

    def __audit_binding_valid(self, audit_settings):
        if (
            self.endpoint.edition() == "community"
            or not audit_settings["audit.projects.bindings.validation"]
            or not self.has_binding()
        ):
            util.logger.info(
                "Community edition, binding validation disabled or %s has no binding, skipping binding validation...",
                str(self),
            )
            return []
        resp = self.get("alm_settings/validate_binding", params={"project": self.key}, exit_on_error=False)
        if resp.ok:
            util.logger.debug("%s binding is valid", str(self))
            return []
        # Hack: 8.9 returns 404, 9.x returns 400
        elif resp.status_code in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND):
            rule = rules.get_rule(rules.RuleId.PROJ_INVALID_BINDING)
            return [pb.Problem(rule.type, rule.severity, rule.msg.format(str(self)), concerned_object=self)]
        else:
            util.exit_fatal(
                f"alm_settings/get_binding returning status code {resp.status_code}, exiting",
                options.ERR_SONAR_API,
            )

    def audit(self, audit_settings):
        util.logger.debug("Auditing %s", str(self))
        return (
            self.__audit_last_analysis__(audit_settings)
            + self.__audit_branches(audit_settings)
            + self.__audit_pull_requests(audit_settings)
            + self.__audit_visibility__(audit_settings)
            + self.__audit_languages__(audit_settings)
            + self.__audit_permissions__(audit_settings)
            + self.__audit_bg_tasks(audit_settings)
            + self.__audit_binding_valid(audit_settings)
            + self.__audit_zero_loc(audit_settings)
        )

    def export_zip(self, timeout=180):
        util.logger.info("Exporting %s (synchronously)", str(self))
        if self.endpoint.version() < (9, 2, 0) and self.endpoint.edition() not in ("enterprise", "datacenter"):
            raise options.UnsupportedOperation(
                "Project export is only available with Enterprise and Datacenter Edition, or with SonarQube 9.2 or higher for any Edition"
            )
        resp = self.post("project_dump/export", params={"key": self.key})
        if not resp.ok:
            return {"status": f"HTTP_ERROR {resp.status_code}"}
        data = json.loads(resp.text)
        status = tasks.Task(data["taskId"], endpoint=self.endpoint, data=data).wait_for_completion(timeout=timeout)
        if status != tasks.SUCCESS:
            util.logger.error("%s export %s", str(self), status)
            return {"status": status}
        data = json.loads(self.get("project_dump/status", params={"key": self.key}).text)
        dump_file = data["exportedDump"]
        util.logger.debug("%s export %s, dump file %s", str(self), status, dump_file)
        return {"status": status, "file": dump_file}

    def export_async(self):
        util.logger.info("Exporting %s (asynchronously)", str(self))
        resp = self.post("project_dump/export", params={"key": self.key})
        if resp.ok:
            data = json.loads(resp.text)
            return data["taskId"]
        return None

    def import_zip(self):
        util.logger.info("Importing %s (asynchronously)", str(self))
        if self.endpoint.edition() not in ["enterprise", "datacenter"]:
            raise options.UnsupportedOperation("Project import is only available with Enterprise and Datacenter Edition")
        resp = self.post("project_dump/import", params={"key": self.key})
        return resp.status_code

    def search_custom_measures(self):
        return custom_measures.search(self.endpoint, self.key)

    def get_findings(self, branch=None, pr=None):
        if self.endpoint.version() < (9, 1, 0) or self.endpoint.edition() not in ("enterprise", "datacenter"):
            return {}

        findings_list = {}
        params = {"project": self.key}
        if branch is not None:
            params["branch"] = branch
        elif pr is not None:
            params["pullRequest"] = pr

        resp = self.get("projects/export_findings", params=params)
        data = json.loads(resp.text)["export_findings"]
        findings_conflicts = {
            "SECURITY_HOTSPOT": 0,
            "BUG": 0,
            "CODE_SMELL": 0,
            "VULNERABILITY": 0,
        }
        nbr_findings = {
            "SECURITY_HOTSPOT": 0,
            "BUG": 0,
            "CODE_SMELL": 0,
            "VULNERABILITY": 0,
        }
        util.logger.debug(util.json_dump(data))
        for i in data:
            key = i["key"]
            if key in findings_list:
                util.logger.warning("Finding %s (%s) already in past findings", i["key"], i["type"])
                findings_conflicts[i["type"]] += 1
            # FIXME - Hack for wrong projectKey returned in PR
            # m = re.search(r"(\w+):PULL_REQUEST:(\w+)", i['projectKey'])
            i["projectKey"] = self.key
            i["branch"] = branch
            i["pullRequest"] = pr
            nbr_findings[i["type"]] += 1
            if i["type"] == "SECURITY_HOTSPOT":
                findings_list[key] = hotspots.get_object(key, endpoint=self.endpoint, data=i, from_export=True)
            else:
                findings_list[key] = issues.get_object(key, endpoint=self.endpoint, data=i, from_export=True)
        for t in ("SECURITY_HOTSPOT", "BUG", "CODE_SMELL", "VULNERABILITY"):
            if findings_conflicts[t] > 0:
                util.logger.warning(
                    "%d %s findings missed because of JSON conflict",
                    findings_conflicts[t],
                    t,
                )
        util.logger.info(
            "%d findings exported for %s branch %s PR %s",
            len(findings_list),
            str(self),
            branch,
            pr,
        )
        for t in ("SECURITY_HOTSPOT", "BUG", "CODE_SMELL", "VULNERABILITY"):
            util.logger.info("%d %s exported", nbr_findings[t], t)

        return findings_list

    def dump_data(self, **opts):
        data = {
            "type": "project",
            "key": self.key,
            "name": self.name,
            "ncloc": self.ncloc_with_branches(),
        }
        if opts.get(options.WITH_URL, False):
            data["url"] = self.url()
        if opts.get(options.WITH_LAST_ANALYSIS, False):
            data["lastAnalysis"] = self.last_analysis()
        return data

    def sync(self, another_project, sync_settings):
        tgt_branches = another_project.get_branches()
        report = []
        counters = {}
        for b_src in self.get_branches():
            for b_tgt in tgt_branches:
                if b_src.name == b_tgt.name:
                    (tmp_report, tmp_counts) = b_src.sync(b_tgt, sync_settings=sync_settings)
                    report += tmp_report
                    counters = util.dict_add(counters, tmp_counts)
        return (report, counters)

    def sync_branches(self, sync_settings):
        my_branches = self.get_branches()
        report = []
        counters = {}
        for b_src in my_branches:
            for b_tgt in my_branches:
                if b_src.name == b_tgt.name:
                    continue
                (tmp_report, tmp_counts) = b_src.sync(b_tgt, sync_settings=sync_settings)
                report += tmp_report
                counters = util.dict_add(counters, tmp_counts)
        return (report, counters)

    def quality_profiles(self):
        util.logger.debug("Exporting quality profiles for %s", str(self))
        qp_list = qualityprofiles.get_list(self.endpoint)
        projects_qp = {}
        for qp in qp_list.values():
            if qp.selected_for_project(self.key):
                projects_qp[qp.key] = qp
        return projects_qp

    def quality_gate(self):
        data = json.loads(self.get(api="qualitygates/get_by_project", params={"project": self.key}).text)
        return (data["qualityGate"]["name"], data["qualityGate"]["default"])

    def webhooks(self):
        util.logger.debug("Getting PROJ webhooks for %s")
        return webhooks.get_list(endpoint=self.endpoint, project_key=self.key)

    def links(self):
        data = json.loads(self.get(api="project_links/search", params={"projectKey": self.key}).text)
        link_list = None
        for link in data["links"]:
            if link_list is None:
                link_list = []
            link_list.append({"type": link["type"], "name": link.get("name", link["type"]), "url": link["url"]})
        return link_list

    def __export_get_binding(self):
        binding = self.binding()
        if binding:
            # Remove redundant fields
            binding.pop("alm", None)
            binding.pop("url", None)
            if not binding["monorepo"]:
                binding.pop("monorepo")
        return binding

    def __export_get_qp(self):
        qp_json = {qp.language: f"{qp.name}" for qp in self.quality_profiles().values()}
        if len(qp_json) == 0:
            return None
        return qp_json

    def __get_branch_export(self):
        branch_data = {}
        my_branches = self.get_branches()
        nb_branches = len(my_branches)
        for branch in my_branches:
            exp = branch.export(full_export=False)
            if nb_branches == 1 and branch.is_main() and len(exp) <= 1:
                # Don't export main branch with no data
                continue
            branch_data[branch.name] = exp
        if len(branch_data) == 0:
            return None
        # If there is only 1 branch with no specific config except being main, don't return anything
        if len(branch_data) == 1 and len(exp) <= 1:
            return None
        return util.remove_nones(branch_data)

    def export(self, settings_list=None, include_inherited=False, full_export=False):
        util.logger.info("Exporting %s", str(self))
        settings_dict = settings.get_bulk(endpoint=self, component=self, settings_list=settings_list, include_not_set=False)
        json_data = {"key": self.key, "name": self.name}
        for s in settings_dict.values():
            if not include_inherited and s.inherited:
                continue
            json_data.update(s.to_json())

        json_data["binding"] = self.__export_get_binding()
        json_data[settings.NEW_CODE_PERIOD] = self.new_code()
        json_data["qualityProfiles"] = self.__export_get_qp()
        json_data["links"] = self.links()
        json_data["permissions"] = self.permissions().to_json(csv=True)
        json_data["branches"] = self.__get_branch_export()
        json_data["tags"] = util.list_to_csv(self.tags(), separator=", ")
        json_data["visibility"] = self.visibility()
        (json_data["qualityGate"], qg_is_default) = self.quality_gate()
        if qg_is_default:
            json_data.pop("qualityGate")

        json_data["webhooks"] = webhooks.export(self.endpoint, self.key)

        if full_export:
            pass
            # self.__add_optional_export(json_data)

        return util.remove_nones(json_data)

    def new_code(self, include_branches=False):
        nc = {}
        data = json.loads(self.get(api="new_code_periods/show", params={"project": self.key}).text)
        new_code = settings.new_code_to_string(data)
        if new_code is None or not include_branches:
            return new_code
        nc[settings.DEFAULT_SETTING] = new_code
        data = json.loads(self.get(api="new_code_periods/list", params={"project": self.key}).text)
        for b in data["newCodePeriods"]:
            new_code = settings.new_code_to_string(b)
            if new_code is None:
                continue
            nc[b["branchKey"]] = new_code
        return nc

    def permissions(self):
        if self._permissions is None:
            self._permissions = perms.ProjectPermissions(self)
        return self._permissions

    def set_permissions(self, data):
        self.permissions().set(data)

    def set_links(self, data):
        params = {"projectKey": self.key}
        for link in data.get("links", {}):
            if "type" in link and link["type"] != "custom":
                continue
            params.update(link)
            self.post("project_links/create", params=params)

    def set_tags(self, tags):
        if tags is None or len(tags) == 0:
            return
        if isinstance(tags, list):
            my_tags = util.list_to_csv(tags)
        else:
            my_tags = util.csv_normalize(tags)
        self.post("project_tags/set", params={"project": self.key, "tags": my_tags})
        self._tags = util.csv_to_list(my_tags)

    def set_quality_gate(self, quality_gate):
        if quality_gate is None:
            return False
        if qualitygates.get_object(quality_gate, endpoint=self.endpoint) is None:
            util.logger.warning("Quality gate '%s' does not exist, can't set it for %s", quality_gate, str(self))
            return False
        util.logger.debug("Setting quality gate '%s' for %s", quality_gate, str(self))
        r = self.post("qualitygates/select", params={"projectKey": self.key, "gateName": quality_gate})
        return r.ok

    def set_quality_profile(self, language, profile_name):
        if not qualityprofiles.exists(language=language, name=profile_name, endpoint=self.endpoint):
            util.logger.warning("Quality profile '%s' in language '%s' does not exist, can't set it for %s", profile_name, language, str(self))
            return False
        util.logger.debug("Setting quality profile '%s' of language '%s' for %s", profile_name, language, str(self))
        r = self.post("qualityprofiles/add_project", params={"project": self.key, "qualityProfile": profile_name, "language": language})
        return r.ok

    def rename_main_branch(self, main_branch_name):
        for b in self.get_branches():
            if b.is_main():
                return b.rename(main_branch_name)
        util.logger.warning("No main branch to rename found for %s", str(self))
        return False

    def set_webhooks(self, webhook_data):
        current_wh = self.webhooks()
        current_wh_names = [wh.name for wh in current_wh.values()]
        wh_map = {wh.name: k for k, wh in current_wh.items()}
        # FIXME: Handle several webhooks with same name
        for wh_name, wh in webhook_data.items():
            if wh_name in current_wh_names:
                current_wh[wh_map[wh_name]].update(name=wh_name, **wh)
            else:
                webhooks.update(name=wh_name, endpoint=self.endpoint, project=self.key, **wh)

    def set_settings(self, data):
        util.logger.debug("Setting %s settings with %s", str(self), util.json_dump(data))
        for key, value in data.items():
            if key in ("branches", settings.NEW_CODE_PERIOD):
                continue
            if key == "webhooks":
                self.set_webhooks(value)
            else:
                settings.set_setting(endpoint=self.endpoint, key=key, value=value, component=self)

        nc = data.get(settings.NEW_CODE_PERIOD, None)
        if nc is not None:
            (nc_type, nc_val) = settings.decode(settings.NEW_CODE_PERIOD, nc)
            settings.set_new_code_period(self.endpoint, nc_type, nc_val, project_key=self.key)
        # TODO: Update branches (main, new code definition, keepWhenInactive)
        # util.logger.debug("Checking main branch")
        # for branch, branch_data in data.get("branches", {}).items():
        #    if branches.exists(branch_name=branch, project_key=self.key, endpoint=self.endpoint):
        #        branches.get_object(branch, self, endpoint=self.endpoint).update(branch_data)()

    def set_devops_binding(self, data):
        util.logger.debug("Setting devops binding of %s to %s", str(self), util.json_dump(data))
        alm_key = data["key"]
        if not devops.platform_exists(alm_key, self.endpoint):
            util.logger.warning("DevOps platform '%s' does not exists, can't set it for %s", alm_key, str(self))
            return False
        alm_type = devops.platform_type(platform_key=alm_key, endpoint=self.endpoint)
        mono = data.get("monorepo", False)
        repo = data["repository"]
        if alm_type == "github":
            self.set_github_binding(alm_key, repository=repo, monorepo=mono, summary_comment=data.get("summaryComment", True))
        elif alm_type == "gitlab":
            self.set_gitlab_binding(alm_key, repository=repo, monorepo=mono)
        elif alm_type == "azure":
            self.set_azure_devops_binding(alm_key, repository=repo, monorepo=mono, slug=data["slug"])
        elif alm_type == "bitbucket":
            self.set_bitbucket_binding(alm_key, repository=repo, monorepo=mono, slug=data["slug"])
        elif alm_type == "bitbucketcloud":
            self.set_bitbucketcloud_binding(alm_key, repository=repo, monorepo=mono)
        else:
            util.logger.error("Invalid devops platform type '%s' for %s, setting skipped", alm_key, str(self))
            return False
        return True

    def __std_binding_params(self, alm_key, repo, monorepo):
        return {"almSetting": alm_key, "project": self.key, "repository": repo, "monorepo": str(monorepo).lower()}

    def set_github_binding(self, devops_platform_key, repository, monorepo=False, summary_comment=True):
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        params["summaryCommentEnabled"] = str(summary_comment).lower()
        self.post("alm_settings/set_github_binding", params=params)

    def set_gitlab_binding(self, devops_platform_key, repository, monorepo=False):
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        self.post("alm_settings/set_gitlab_binding", params=params)

    def set_bitbucket_binding(self, devops_platform_key, repository, slug, monorepo=False):
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        params["slug"] = slug
        self.post("alm_settings/set_bitbucket_binding", params=params)

    def set_bitbucketcloud_binding(self, devops_platform_key, repository, monorepo=False):
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        self.post("alm_settings/set_bitbucketcloud_binding", params=params)

    def set_azure_devops_binding(self, devops_platform_key, slug, repository, monorepo=False):
        params = self.__std_binding_params(devops_platform_key, repository, monorepo)
        params["projectName"] = slug
        params["repositoryName"] = params.pop("repository")
        self.post("alm_settings/set_azure_binding", params=params)

    def update(self, data):
        self.set_permissions(data.get("permissions", None))
        self.set_links(data)
        self.set_tags(data.get("tags", None))
        self.set_quality_gate(data.get("qualityGate", None))
        for lang, qp_name in data.get("qualityProfiles", {}).items():
            res = qp_name.split(" ", maxsplit=1)
            profile = " ".join(res[1:]) if len(res) > 1 else qp_name
            self.set_quality_profile(language=lang, profile_name=profile)
        for bname, bdata in data.get("branches", {}).items():
            if bdata.get("isMain", False):
                self.rename_main_branch(bname)
                break
        if "binding" in data:
            self.set_devops_binding(data["binding"])
        else:
            util.logger.debug("%s has no devops binding, skipped", str(self))
        settings_to_apply = {
            k: v for k, v in data.items() if k not in ("permissions", "tags", "links", "qualityGate", "qualityProfiles", "binding", "name")
        }
        # TODO: Set branch settings
        self.set_settings(settings_to_apply)


def count(endpoint, params=None):
    new_params = {} if params is None else params.copy()
    new_params.update({"ps": 1, "p": 1})
    data = json.loads(endpoint.get(_SEARCH_API, params=params))
    return data["paging"]["total"]


def search(endpoint, params=None):
    new_params = {} if params is None else params.copy()
    new_params["qualifiers"] = "TRK"
    return sqobject.search_objects(
        api="projects/search",
        params=new_params,
        key_field="key",
        returned_field="components",
        endpoint=endpoint,
        object_class=Project,
    )


def get_list(endpoint, key_list=None):
    if key_list is None:
        util.logger.info("Listing projects")
        return search(endpoint=endpoint)
    object_list = {}
    for key in util.csv_to_list(key_list):
        object_list[key] = get_object(key, endpoint=endpoint)
        if object_list[key] is None:
            raise options.NonExistingObjectError(key, f"Project key '{key}' does not exist")
    return object_list


def key_obj(key_or_obj):
    if isinstance(key_or_obj, str):
        return (key_or_obj, _OBJECTS.get(key_or_obj, None))
    else:
        return (key_or_obj.key, key_or_obj)


def get_object(key, endpoint):
    if len(_OBJECTS) == 0:
        get_list(endpoint=endpoint)
    if key not in _OBJECTS:
        return None
    return _OBJECTS[key]


def audit(audit_settings, endpoint=None):
    util.logger.info("--- Auditing projects ---")
    plist = search(endpoint)
    is_community = endpoint.edition() == "community"
    problems = []
    bindings = {}
    for key, p in plist.items():
        problems += p.audit(audit_settings)
        if not is_community and audit_settings["audit.projects.bindings"] and not p.is_part_of_monorepo():
            bindkey = p.binding_key()
            if bindkey is not None and bindkey in bindings:
                rule = rules.get_rule(rules.RuleId.PROJ_DUPLICATE_BINDING)
                problems.append(
                    pb.Problem(
                        rule.type,
                        rule.severity,
                        rule.msg.format(str(p), str(bindings[bindkey])),
                        concerned_object=p,
                    )
                )
            else:
                bindings[bindkey] = p
        if not audit_settings["audit.projects.duplicates"]:
            continue
        util.logger.debug("Auditing for potential duplicate projects")
        for key2 in plist:
            if key2 != key and re.match(key2, key):
                rule = rules.get_rule(rules.RuleId.PROJ_DUPLICATE)
                problems.append(
                    pb.Problem(
                        rule.type,
                        rule.severity,
                        rule.msg.format(str(p), key2),
                        concerned_object=p,
                    )
                )

    if not audit_settings.get("audit.projects.duplicates", False):
        util.logger.info("Project duplicates auditing was disabled by configuration")
    return problems


def export(endpoint, key_list=None):
    project_settings = {k: p.export() for k, p in get_list(endpoint=endpoint, key_list=key_list).items()}
    for k in project_settings:
        project_settings[k].pop("key")
    return project_settings


def exists(key, endpoint):
    return len(search(params={"projects": key}, endpoint=endpoint)) > 0


def get_measures(key, metrics_list, branch=None, pull_request=None, endpoint=None):
    if branch is not None:
        obj = branches.get_object(key, branch, endpoint=endpoint)
    elif pull_request is not None:
        obj = pull_requests.get_object(key, pull_request, endpoint=endpoint)
    else:
        obj = get_object(key, endpoint=endpoint)

    return obj.get_measures(metrics_list)


def loc_csv_header(**kwargs):
    arr = ["# Project Key"]
    if kwargs[options.WITH_NAME]:
        arr.append("Project name")
    arr.append("LoC")
    if kwargs[options.WITH_LAST_ANALYSIS]:
        arr.append("Last analysis")
    if kwargs[options.WITH_URL]:
        arr.append("URL")
    return arr


def create(key, endpoint=None, data=None):
    o = get_object(key=key, endpoint=endpoint)
    if o is None:
        o = Project(key=key, endpoint=endpoint, create_data=data)
    else:
        util.logger.info("%s already exist, creation skipped", str(o))
    return o


def create_or_update(endpoint, key, data):
    o = get_object(key=key, endpoint=endpoint)
    if o is None:
        util.logger.debug("Project key '%s' does not exist, creating...", key)
        o = create(key=key, endpoint=endpoint, data=data)
    o.update(data)


def import_config(endpoint, config_data, key_list=None):
    if "projects" not in config_data:
        util.logger.info("No projects to import")
        return
    util.logger.info("Importing projects")
    get_list(endpoint=endpoint)
    nb_projects = len(config_data["projects"])
    i = 0
    new_key_list = util.csv_to_list(key_list)
    for key, data in config_data["projects"].items():
        if new_key_list and key not in new_key_list:
            continue
        util.logger.info("Importing project key '%s'", key)
        create_or_update(endpoint, key, data)
        i += 1
        if i % 20 == 0 or i == nb_projects:
            util.logger.info("Imported %d/%d projects (%d%%)", i, nb_projects, (i * 100 // nb_projects))
