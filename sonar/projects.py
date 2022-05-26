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
import pytz
from sonar import (
    env,
    components,
    qualityprofiles,
    tasks,
    custom_measures,
    pull_requests,
    branches,
    measures,
    options,
    settings,
)
from sonar.findings import issues, hotspots
import sonar.sqobject as sq
import sonar.utilities as util
import sonar.permissions as perms

from sonar.audit import rules, severities
import sonar.audit.problem as pb

_PROJECTS = {}

MAX_PAGE_SIZE = 500
PROJECT_SEARCH_API = "projects/search"
PRJ_QUALIFIER = "TRK"
APP_QUALIFIER = "APP"

_BIND_SEP = ":::"


class Project(components.Component):
    def __init__(self, key, endpoint=None, data=None):
        self.visibility = None
        self.main_branch_last_analysis_date = "undefined"
        self.all_branches_last_analysis_date = "undefined"
        self._user_permissions = None
        self._group_permissions = None
        self.branches = None
        self.pull_requests = None
        self._ncloc_with_branches = None
        self._binding = {"has_binding": True, "binding": None}
        super().__init__(key, endpoint)
        self.__load__(data)
        _PROJECTS[key] = self
        util.logger.debug("Created object %s", str(self))

    def __str__(self):
        return f"project '{self.key}'"

    def __load__(self, data=None):
        """Loads a project object with contents of an api/projects/search call"""
        if data is None:
            resp = env.get(PROJECT_SEARCH_API, ctxt=self.endpoint, params={"projects": self.key})
            data = json.loads(resp.text)
            if not data["components"]:
                raise env.NonExistingObjectError(self.key, "Project key does not exist")
            data = data["components"][0]
        self.name = data["name"]
        self.visibility = data["visibility"]
        if "lastAnalysisDate" in data:
            self.main_branch_last_analysis_date = util.string_to_date(data["lastAnalysisDate"])
        else:
            self.main_branch_last_analysis_date = None
        self.revision = data.get("revision", None)

    #    def __del__(self):
    #        # del PROJECTS[self.key]

    def url(self):
        return f"{self.endpoint.url}/dashboard?id={self.key}"

    def get_name(self):
        if self.name is None:
            self.__load__()
        return self.name

    def get_visibility(self):
        if self.visibility is None:
            self.__load__()
        return self.visibility

    def last_analysis_date(self, include_branches=False):
        if self.main_branch_last_analysis_date == "undefined":
            self.__load__()
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

    def get_branches(self):
        if self.endpoint.edition() == "community":
            util.logger.debug("Branches not available in Community Edition")
            return []

        if self.branches is None:
            resp = env.get(
                "project_branches/list",
                params={"project": self.key},
                ctxt=self.endpoint,
            )
            data = json.loads(resp.text)
            self.branches = []
            for b in data["branches"]:
                self.branches.append(branches.get_object(b["name"], self, data=b))
        return self.branches

    def get_pull_requests(self):
        if self.endpoint.edition() == "community":
            util.logger.debug("Pull requests not available in Community Edition")
            return []

        if self.pull_requests is None:
            resp = env.get(
                "project_pull_requests/list",
                params={"project": self.key},
                ctxt=self.endpoint,
            )
            data = json.loads(resp.text)
            self.pull_requests = []
            for p in data["pullRequests"]:
                self.pull_requests.append(pull_requests.get_object(p["key"], self, p))
        return self.pull_requests

    def permissions(self, perm_type):
        p = perms.get(self.endpoint, perm_type)
        if perm_type == "groups":
            self._group_permissions = p
        else:
            self._user_permissions = p
        return p

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
            resp = env.get(
                "alm_settings/get_binding",
                ctxt=self.endpoint,
                params={"project": self.key},
                exit_on_error=False,
            )
            # 8.9 returns 404, 9.x returns 400
            if resp.status_code in (400, 404):
                self._binding["has_binding"] = False
            elif resp.status_code // 100 == 2:
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
        counts = perms.counts(self.permissions("users"), perms.PROJECT_PERMISSIONS)
        max_users = audit_settings["audit.projects.permissions.maxUsers"]
        if counts["overall"] > max_users:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_USERS)
            msg = rule.msg.format(str(self), counts["overall"])
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_admins = audit_settings["audit.projects.permissions.maxAdminUsers"]
        if counts["admin"] > max_admins:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ADM_USERS)
            msg = rule.msg.format(str(self), counts["admin"], max_admins)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        return problems

    def __audit_group_permissions__(self, audit_settings):
        problems = []
        groups = self.permissions("groups")
        for gr in groups:
            p = gr["permissions"]
            if not p:
                continue
            # -- Checks for Anyone, sonar-user
            if gr["name"] != "Anyone" and gr["id"] != 2:
                continue
            if "issueadmin" in p or "scan" in p or "securityhotspotadmin" in p or "admin" in p:
                if gr["name"] == "Anyone":
                    rule = rules.get_rule(rules.RuleId.PROJ_PERM_ANYONE)
                else:
                    rule = rules.get_rule(rules.RuleId.PROJ_PERM_SONAR_USERS_ELEVATED_PERMS)
                msg = rule.msg.format(gr["name"], str(self))
                problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))
            else:
                util.logger.info(
                    "Group '%s' has browse permissions on %s. \
Is this normal ?",
                    gr["name"],
                    str(self.key),
                )

        counts = perms.counts(groups, perms.PROJECT_PERMISSIONS)
        max_perms = audit_settings["audit.projects.permissions.maxGroups"]
        if counts["overall"] > max_perms:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_GROUPS)
            msg = rule.msg.format(str(self), counts["overall"], max_perms)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_scan = audit_settings["audit.projects.permissions.maxScanGroups"]
        if counts["scan"] > max_scan:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_SCAN_GROUPS)
            msg = rule.msg.format(str(self), counts["scan"], max_scan)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_issue_adm = audit_settings["audit.projects.permissions.maxIssueAdminGroups"]
        if counts["issueadmin"] > max_issue_adm:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ISSUE_ADM_GROUPS)
            msg = rule.msg.format(str(self), counts["issueadmin"], max_issue_adm)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_spots_adm = audit_settings["audit.projects.permissions.maxHotspotAdminGroups"]
        if counts["securityhotspotadmin"] > max_spots_adm:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_HOTSPOT_ADM_GROUPS)
            msg = rule.msg.format(str(self), counts["securityhotspotadmin"], max_spots_adm)
            problems.append(pb.Problem(rule.type, rule.severity, msg, concerned_object=self))

        max_admins = audit_settings["audit.projects.permissions.maxAdminGroups"]
        if counts["admin"] > max_admins:
            rule = rules.get_rule(rules.RuleId.PROJ_PERM_MAX_ADM_GROUPS)
            problems.append(
                pb.Problem(
                    rule.type,
                    rule.severity,
                    rule.msg.format(str(self), counts["admin"], max_admins),
                    concerned_object=self,
                )
            )
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
        resp = env.get("navigation/component", ctxt=self.endpoint, params={"component": self.key})
        data = json.loads(resp.text)
        visi = data["visibility"]
        if visi != "private":
            rule = rules.get_rule(rules.RuleId.PROJ_VISIBILITY)
            return [
                pb.Problem(
                    rule.type,
                    rule.severity,
                    rule.msg.format(str(self), visi),
                    concerned_object=self,
                )
            ]

        util.logger.debug("%s visibility is private", str(self))
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
            or not audit_settings["audit.projects.bindings"]
            or not audit_settings["audit.projects.bindings.validation"]
            or not self.has_binding()
        ):
            util.logger.info(
                "Community edition, binding validation disabled or %s has no binding, skipping binding validation...",
                str(self),
            )
            return []
        resp = env.get(
            "alm_settings/validate_binding",
            ctxt=self.endpoint,
            params={"project": self.key},
            exit_on_error=False,
        )
        if resp.status_code // 100 == 2:
            util.logger.debug("%s binding is valid", str(self))
            return []
        # 8.9 returns 404, 9.x returns 400
        elif resp.status_code in (400, 404):
            rule = rules.get_rule(rules.RuleId.PROJ_INVALID_BINDING)
            return [
                pb.Problem(
                    rule.type,
                    rule.severity,
                    rule.msg.format(str(self)),
                    concerned_object=self,
                )
            ]
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
            raise env.UnsupportedOperation(
                "Project export is only available with Enterprise and Datacenter Edition, or with SonarQube 9.2 or higher for any Edition"
            )
        resp = env.post("project_dump/export", params={"key": self.key}, ctxt=self.endpoint)
        if resp.status_code != 200:
            return {"status": f"HTTP_ERROR {resp.status_code}"}
        data = json.loads(resp.text)
        status = tasks.Task(data["taskId"], endpoint=self.endpoint, data=data).wait_for_completion(timeout=timeout)
        if status != tasks.SUCCESS:
            util.logger.error("%s export %s", str(self), status)
            return {"status": status}
        resp = env.get("project_dump/status", params={"key": self.key}, ctxt=self.endpoint)
        data = json.loads(resp.text)
        dump_file = data["exportedDump"]
        util.logger.debug("%s export %s, dump file %s", str(self), status, dump_file)
        return {"status": status, "file": dump_file}

    def export_async(self):
        util.logger.info("Exporting %s (asynchronously)", str(self))
        resp = env.post("project_dump/export", params={"key": self.key}, ctxt=self.endpoint)
        if resp.status_code != 200:
            return None
        data = json.loads(resp.text)
        return data["taskId"]

    def import_zip(self):
        util.logger.info("Importing %s (asynchronously)", str(self))
        if self.endpoint.edition() not in ["enterprise", "datacenter"]:
            raise env.UnsupportedOperation("Project import is only available with Enterprise and Datacenter Edition")
        resp = env.post("project_dump/import", params={"key": self.key}, ctxt=self.endpoint)
        return resp.status_code

    def search_custom_measures(self):
        return custom_measures.search(self.key, self.endpoint)

    def get_findings(self, branch=None, pr=None):

        if self.endpoint.version() < (9, 1, 0) or self.endpoint.edition() not in (
            "enterprise",
            "datacenter",
        ):
            return {}

        findings_list = {}
        params = {"project": self.key}
        if branch is not None:
            params["branch"] = branch
        elif pr is not None:
            params["pullRequest"] = pr

        resp = env.get("projects/export_findings", params=params, ctxt=self.endpoint)
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
        qp_list = qualityprofiles.get_list(self.endpoint)
        projects_qp = {}
        for qp in qp_list.values():
            if qp.selected_for_project(self.key):
                projects_qp[qp.key] = qp
        return projects_qp

    def quality_gate(self):
        data = json.loads(self.get(api="qualitygates/get_by_project", params={"project": self.key}).text)
        return (data["qualityGate"]["name"], data["qualityGate"]["default"])

    def links(self):
        data = json.loads(self.get(api="project_links/search", params={"projectKey": self.key}).text)
        link_list = None
        for link in data["links"]:
            if link_list is None:
                link_list = []
            link_list.append({"type": link["type"], "url": link["url"]})
        return link_list

    def webhooks(self):
        data = json.loads(self.get("webhooks/list", params={"project": self.key}).text)
        if len(data.get("webhooks", [])) > 0:
            return data["webhooks"]
        else:
            return None

    def __settings_add_new_code(self, json_data):
        nc = self.new_code_periods()
        if nc:
            if settings.GENERAL_SETTINGS not in json_data:
                json_data[settings.GENERAL_SETTINGS] = {}
            json_data[settings.GENERAL_SETTINGS].update({settings.NEW_CODE_PERIOD: nc})

    def __settings_add_binding(self, json_data):
        binding = self.binding()
        if binding:
            # Remove redundant fields
            binding.pop("alm", None)
            binding.pop("url", None)
            if not binding["monorepo"]:
                binding.pop("monorepo")
            json_data[settings.DEVOPS_INTEGRATION] = binding

    def __settings_add_qp(self, json_data):
        qp_json = {}
        for qp in self.quality_profiles().values():
            qp_json[qp.language] = f"{qp.key} {qp.name}"
        if len(qp_json) > 0:
            json_data["qualityProfiles"] = qp_json

    def __settings_add_links(self, json_data):
        p_links = self.links()
        if p_links is not None:
            json_data["links"] = p_links

    def __settings_add_permissions(self, json_data):
        json_data["permissions"] = {}
        for ptype in ("users", "groups"):
            permiss = perms.simplify(perms.get(self.endpoint, ptype, projectKey=self.key))
            if len(permiss) > 0:
                json_data["permissions"][ptype] = permiss

    def export(self, settings_list=None, include_inherited=False):
        util.logger.info("Exporting %s", str(self))
        settings_dict = settings.get_bulk(
            endpoint=self,
            project=self,
            settings_list=settings_list,
            include_not_set=False,
        )
        json_data = {"key": self.key, "name": self.name}
        for s in settings_dict.values():
            if not include_inherited and s.inherited:
                continue
            (categ, subcateg) = s.category()
            util.update_json(json_data, categ, subcateg, s.to_json())

        self.__settings_add_binding(json_data)
        self.__settings_add_new_code(json_data)
        self.__settings_add_qp(json_data)
        self.__settings_add_links(json_data)
        self.__settings_add_permissions(json_data)

        (json_data["qualityGate"], is_default) = self.quality_gate()
        if is_default:
            json_data.pop("qualityGate")

        whooks = self.webhooks()
        if whooks is not None:
            for wh in whooks:
                wh.pop("key", None)
                wh.pop("latestDelivery", None)
            if settings.GENERAL_SETTINGS not in json_data:
                json_data[settings.GENERAL_SETTINGS] = {}
            json_data[settings.GENERAL_SETTINGS].update({"webhooks": whooks})
        return json_data

    def new_code_periods(self):
        nc = {}
        data = json.loads(self.get(api="new_code_periods/show", params={"project": self.key}).text)
        new_code = settings.new_code_to_string(data)
        if new_code is None:
            return None
        nc[settings.DEFAULT_SETTING] = new_code
        data = json.loads(self.get(api="new_code_periods/list", params={"project": self.key}).text)
        for b in data["newCodePeriods"]:
            new_code = settings.new_code_to_string(b)
            if new_code is None:
                continue
            nc[b["branchKey"]] = new_code
        return nc


def count(endpoint=None, params=None):
    if params is None:
        params = {}
    params["ps"] = 1
    params["p"] = 1
    resp = env.get(PROJECT_SEARCH_API, ctxt=endpoint, params=params)
    data = json.loads(resp.text)
    return data["paging"]["total"]


def search(endpoint=None, params=None):
    new_params = {} if params is None else params.copy()
    new_params["qualifiers"] = "TRK"
    return sq.search_objects(
        api="projects/search",
        params=new_params,
        key_field="key",
        returned_field="components",
        endpoint=endpoint,
        object_class=Project,
    )


def get_key_list(endpoint=None, params=None):
    return search(endpoint, params).keys()


def get_object_list(endpoint=None, params=None):
    return search(endpoint, params).values()


def get_projects_list(str_key_list, endpoint):
    if str_key_list is None:
        util.logger.info("Getting project list")
        project_list = search(endpoint=endpoint)
    else:
        project_list = {}
        try:
            for key in util.csv_to_list(str_key_list):
                project_list[key] = get_object(key, endpoint=endpoint)
        except env.NonExistingObjectError as e:
            util.exit_fatal(
                f"Project key '{e.key}' does not exist, aborting...",
                options.ERR_NO_SUCH_PROJECT_KEY,
            )
    return project_list


def key_obj(key_or_obj):
    if isinstance(key_or_obj, str):
        return (key_or_obj, get_object(key_or_obj))
    else:
        return (key_or_obj.key, key_or_obj)


def get_object(key, data=None, endpoint=None):
    if key not in _PROJECTS:
        _ = Project(key=key, data=data, endpoint=endpoint)
    return _PROJECTS[key]


def create_project(key, name=None, visibility="private", sqenv=None):
    if name is None:
        name = key
    resp = env.post(
        "projects/create",
        ctxt=sqenv,
        params={"project": key, "name": name, "visibility": visibility},
    )
    return resp.status_code


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
