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

    Abstraction of the SonarQube "platform" concept

"""
from http import HTTPStatus
import sys
import os
import re
import time
import datetime
import json
import tempfile
import requests
import jprops

import sonar.utilities as util

from sonar import options, settings, devops, webhooks, version
from sonar.permissions import permissions, global_permissions, permission_templates
from sonar.audit import rules, config
import sonar.audit.severities as sev
import sonar.audit.types as typ
import sonar.audit.problem as pb

from sonar import sif

WRONG_CONFIG_MSG = "Audit config property %s has wrong value %s, skipping audit"

_NON_EXISTING_SETTING_SKIPPED = "Setting %s does not exist, skipping..."

_SONAR_TOOLS_AGENT = {"user-agent": f"sonar-tools {version.PACKAGE_VERSION}"}
_UPDATE_CENTER = "https://raw.githubusercontent.com/SonarSource/sonar-update-center-properties/master/update-center-source.properties"

LTS = None
LATEST = None
_HARDCODED_LTS = (8, 9, 9)
_HARDCODED_LATEST = (9, 5, 0)


class Environment:
    def __init__(self, some_url, some_token, cert_file=None):
        self.url = some_url
        self.token = some_token
        self.cert_file = cert_file
        self._version = None
        self._sys_info = None
        self._server_id = None
        self._permissions = None

    def __str__(self):
        return f"{util.redacted_token(self.token)}@{self.url}"

    def set_env(self, some_url, some_token, cert_file=None):
        self.url = some_url
        self.token = some_token
        self.cert_file = cert_file
        util.logger.debug("Setting environment: %s", str(self))

    def credentials(self):
        return (self.token, "")

    def version(self, digits=3, as_string=False):
        if digits < 1 or digits > 3:
            digits = 3
        if self._version is None:
            self._version = self.get("/api/server/version").text.split(".")
        if as_string:
            return ".".join(self._version[0:digits])
        else:
            return tuple(int(n) for n in self._version[0:digits])

    def global_permissions(self):
        if self._permissions is None:
            self._permissions = global_permissions.GlobalPermissions(self)
        return self._permissions

    def server_id(self):
        if self._server_id is not None:
            return self._server_id
        if self._sys_info is not None and "Server ID" in self._sys_info["System"]:
            self._server_id = self._sys_info["System"]["Server ID"]
        else:
            self._server_id = json.loads(self.get("system/status").text)["id"]
        return self._server_id

    def sys_info(self):
        if self._sys_info is None:
            success, counter = False, 0
            while not success and counter < 10:
                resp = self.get("system/info", exit_on_error=False)
                if resp.ok:
                    self._sys_info = json.loads(resp.text)
                    success = True
                else:
                    # Hack: SonarQube randomly returns Error 500, retry in that case
                    if resp.status_code == HTTPStatus.INTERNAL_SERVER_ERROR:
                        util.logger.error("HTTP Error 500 for api/system/info, retrying...")
                        counter += 1
                        time.sleep(1)
                    else:
                        util.logger.error("HTTP Error %d for api/system/info", resp.status_code)
                        success = True
        return self._sys_info

    def edition(self):
        return self.sys_info()["Statistics"]["edition"]

    def database(self):
        return self.sys_info()["Statistics"]["database"]["name"]

    def plugins(self):
        return self.sys_info()["Statistics"]["plugins"]

    def __lts_and_latest(self):
        global LTS
        global LATEST
        if LTS is None:
            util.logger.debug("Attempting to reach Sonar update center")
            _, tmpfile = tempfile.mkstemp(prefix="sonar-tools", suffix=".txt", text=True)
            try:
                with open(tmpfile, "w", encoding="utf-8") as fp:
                    print(requests.get(_UPDATE_CENTER, headers=_SONAR_TOOLS_AGENT).text, file=fp)
                with open(tmpfile, "r", encoding="utf-8") as fp:
                    upd_center_props = jprops.load_properties(fp)
                v = upd_center_props.get("ltsVersion", "8.9.9").split(".")
                if len(v) == 2:
                    v.append("0")
                LTS = tuple(int(n) for n in v)
                v = upd_center_props.get("publicVersions", "9.5").split(",")[-1].split(".")
                if len(v) == 2:
                    v.append("0")
                LATEST = tuple(int(n) for n in v)
                util.logger.debug("Sonar update center says LTS = %s, LATEST = %s", str(LTS), str(LATEST))
            except (EnvironmentError, requests.exceptions.HTTPError):
                LTS = _HARDCODED_LTS
                LATEST = _HARDCODED_LATEST
                util.logger.debug("Sonar update center read failed, hardcoding LTS = %s, LATEST = %s", str(LTS), str(LATEST))
            try:
                os.remove(tmpfile)
            except EnvironmentError:
                pass
        return (LTS, LATEST)

    def lts(self, digits=3):
        if digits < 1 or digits > 3:
            digits = 3
        return self.__lts_and_latest()[0][0:digits]

    def latest(self, digits=3):
        if digits < 1 or digits > 3:
            digits = 3
        return self.__lts_and_latest()[1][0:digits]

    def get(self, api, params=None, exit_on_error=True):
        api = _normalize_api(api)
        util.logger.debug("GET: %s", self.urlstring(api, params))
        try:
            r = requests.get(url=self.url + api, auth=self.credentials(), verify=self.cert_file, headers=_SONAR_TOOLS_AGENT, params=params)
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            if exit_on_error:
                util.log_and_exit(r)
        except requests.RequestException as e:
            util.exit_fatal(str(e), options.ERR_SONAR_API)
        return r

    def post(self, api, params=None, exit_on_error=True):
        api = _normalize_api(api)
        util.logger.debug("POST: %s", self.urlstring(api, params))
        try:
            r = requests.post(url=self.url + api, auth=self.credentials(), verify=self.cert_file, headers=_SONAR_TOOLS_AGENT, data=params)
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            if exit_on_error:
                util.log_and_exit(r)
        except requests.RequestException as e:
            util.exit_fatal(str(e), options.ERR_SONAR_API)
        return r

    def delete(self, api, params=None):
        api = _normalize_api(api)
        util.logger.debug("DELETE: %s", self.urlstring(api, params))
        try:
            r = requests.delete(url=self.url + api, auth=self.credentials(), verify=self.cert_file, params=params, headers=_SONAR_TOOLS_AGENT)
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            util.log_and_exit(r)
        except requests.RequestException as e:
            util.exit_fatal(str(e), options.ERR_SONAR_API)

    def get_setting(self, key):
        return self.__get_platform_settings(key).get(key, None)

    def reset_setting(self, key):
        return settings.reset_setting(self, key)

    def set_setting(self, key, value):
        return settings.set_setting(self, key, value)

    def urlstring(self, api, params):
        first = True
        url_prefix = f"{str(self)}{api}"
        if params is None:
            return url_prefix
        for p in params:
            if params[p] is None:
                continue
            sep = "?" if first else "&"
            first = False
            if isinstance(params[p], datetime.date):
                params[p] = util.format_date(params[p])
            url_prefix += f"{sep}{p}={requests.utils.quote(str(params[p]))}"
        return url_prefix

    def webhooks(self):
        return webhooks.get_list(self)

    def settings(self, settings_list=None, include_not_set=False):
        util.logger.info("getting global settings")
        return settings.get_bulk(endpoint=self, settings_list=settings_list, include_not_set=include_not_set)

    def export(self, full=False):
        util.logger.info("Exporting platform global settings")
        json_data = {}
        for s in self.settings(include_not_set=True).values():
            (categ, subcateg) = s.category()
            util.update_json(json_data, categ, subcateg, s.to_json())

        json_data[settings.GENERAL_SETTINGS].update({"webhooks": webhooks.export(self, full=full)})
        json_data["permissions"] = self.global_permissions().export()
        json_data["permissionTemplates"] = permission_templates.export(self, full=full)
        json_data[settings.DEVOPS_INTEGRATION] = devops.export(self, full=full)
        return json_data

    def set_webhooks(self, webhooks_data):
        current_wh = self.webhooks()
        # FIXME: Handle several webhooks with same name
        current_wh_names = [wh.name for wh in current_wh.values()]
        wh_map = {wh.name: k for k, wh in current_wh.items()}
        util.logger.debug("Current WH %s", str(current_wh_names))
        for wh_name, wh in webhooks_data.items():
            util.logger.debug("Updating wh with name %s", wh_name)
            if wh_name in current_wh_names:
                current_wh[wh_map[wh_name]].update(name=wh_name, **wh)
            else:
                webhooks.update(name=wh_name, endpoint=self, project=None, **wh)

    def import_config(self, config_data):
        for section in ("analysisScope", "authentication", "generalSettings", "linters", "sastConfig", "tests", "thirdParty"):
            if section not in config_data:
                continue
            for setting_key, setting_value in config_data[section].items():
                if setting_key == "webhooks":
                    self.set_webhooks(setting_value)
                else:
                    self.set_setting(setting_key, setting_value)

        if "languages" in config_data:
            for setting_value in config_data["languages"].values():
                for s, v in setting_value.items():
                    self.set_setting(s, v)

        if settings.NEW_CODE_PERIOD in config_data["generalSettings"]:
            (nc_type, nc_val) = settings.decode(settings.NEW_CODE_PERIOD, config_data["generalSettings"][settings.NEW_CODE_PERIOD])
            settings.set_new_code_period(self, nc_type, nc_val)
        permission_templates.import_config(self, config_data)
        global_permissions.import_config(self, config_data)
        devops.import_config(self, config_data)

    def basics(self):
        return {
            "version": self.version(as_string=True),
            "edition": self.edition(),
            "serverId": self.server_id(),
        }

    def __get_platform_settings(self, settings_list=None):
        params = None
        if settings_list is not None:
            params = {"keys": util.list_to_csv(settings_list)}
        resp = self.get("settings/values", params=params)
        json_s = json.loads(resp.text)
        platform_settings = {}
        for s in json_s["settings"]:
            if "value" in s:
                platform_settings[s["key"]] = s["value"]
            elif "values" in s:
                platform_settings[s["key"]] = ",".join(s["values"])
            elif "fieldValues" in s:
                platform_settings[s["key"]] = s["fieldValues"]
        return platform_settings

    def audit(self, audit_settings=None):
        util.logger.info("--- Auditing global settings ---")
        problems = []
        platform_settings = self.__get_platform_settings()
        settings_url = f"{self.url}/admin/settings"
        for key in audit_settings:
            if key.startswith("audit.globalSettings.range"):
                problems += _audit_setting_in_range(key, platform_settings, audit_settings, self.version(), settings_url)
            elif key.startswith("audit.globalSettings.value"):
                problems += _audit_setting_value(key, platform_settings, audit_settings, settings_url)
            elif key.startswith("audit.globalSettings.isSet"):
                problems += _audit_setting_set(key, True, platform_settings, audit_settings, settings_url)
            elif key.startswith("audit.globalSettings.isNotSet"):
                problems += _audit_setting_set(key, False, platform_settings, audit_settings, settings_url)

        problems += (
            _audit_maintainability_rating_grid(platform_settings, audit_settings, settings_url)
            + self._audit_project_default_visibility()
            + self._audit_admin_password()
            + self._audit_global_permissions()
            + self._audit_lts_latest()
            + sif.Sif(self.sys_info(), self).audit()
            + webhooks.audit(self)
            + permission_templates.audit(self, audit_settings)
        )
        return problems

    def _audit_project_default_visibility(self):
        util.logger.info("Auditing project default visibility")
        problems = []
        if self.version() < (8, 7, 0):
            resp = self.get(
                "navigation/organization",
                params={"organization": "default-organization"},
            )
            visi = json.loads(resp.text)["organization"]["projectVisibility"]
        else:
            resp = self.get("settings/values", params={"keys": "projects.default.visibility"})
            visi = json.loads(resp.text)["settings"][0]["value"]
        util.logger.info("Project default visibility is '%s'", visi)
        if config.get_property("checkDefaultProjectVisibility") and visi != "private":
            rule = rules.get_rule(rules.RuleId.SETTING_PROJ_DEFAULT_VISIBILITY)
            problems.append(pb.Problem(rule.type, rule.severity, rule.msq.format(visi), concerned_object=f"{self.url}/admin/projects_management"))
        return problems

    def _audit_admin_password(self):
        util.logger.info("Auditing admin password")
        problems = []
        try:
            r = requests.get(url=self.url + "/api/authentication/validate", auth=("admin", "admin"))
            data = json.loads(r.text)
            if data.get("valid", False):
                rule = rules.get_rule(rules.RuleId.DEFAULT_ADMIN_PASSWORD)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg, concerned_object=self.url))
            else:
                util.logger.info("User 'admin' default password has been changed")
        except requests.RequestException as e:
            util.exit_fatal(str(e), options.ERR_SONAR_API)
        return problems

    def __audit_group_permissions(self):
        util.logger.info("Auditing group global permissions")
        problems = []
        perms_url = f"{self.url}/admin/permissions"
        groups = self.global_permissions().groups()
        if len(groups) > 10:
            msg = f"Too many ({len(groups)}) groups with global permissions"
            problems.append(pb.Problem(typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM, msg, concerned_object=perms_url))

        for gr_name, gr_perms in groups.items():
            if gr_name == "Anyone":
                rule = rules.get_rule(rules.RuleId.ANYONE_WITH_GLOBAL_PERMS)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg, concerned_object=perms_url))
            if gr_name == "sonar-users" and (
                "admin" in gr_perms or "gateadmin" in gr_perms or "profileadmin" in gr_perms or "provisioning" in gr_perms
            ):
                rule = rules.get_rule(rules.RuleId.SONAR_USERS_WITH_ELEVATED_PERMS)
                problems.append(pb.Problem(rule.type, rule.severity, rule.msg, concerned_object=perms_url))

        maxis = {"admin": 2, "gateadmin": 2, "profileadmin": 2, "scan": 2, "provisioning": 3}
        for key, name in permissions.ENTERPRISE_GLOBAL_PERMISSIONS.items():
            counter = self.global_permissions().count(perm_type="groups", perm_filter=(key))
            if key in maxis and counter > maxis[key]:
                msg = f"Too many ({counter}) groups with permission '{name}', {maxis[key]} max recommended"
                problems.append(pb.Problem(typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM, msg, concerned_object=perms_url))
        return problems

    def __audit_user_permissions(self):
        util.logger.info("Auditing users global permissions")
        problems = []
        perms_url = f"{self.url}/admin/permissions"
        users = self.global_permissions().users()
        if len(users) > 10:
            msg = f"Too many ({len(users)}) users with direct global permissions, use groups instead"
            problems.append(pb.Problem(typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM, msg, concerned_object=perms_url))

        maxis = {"admin": 3, "gateadmin": 3, "profileadmin": 3, "scan": 3, "provisioning": 3}
        for key, name in permissions.ENTERPRISE_GLOBAL_PERMISSIONS.items():
            counter = self.global_permissions().count(perm_type="users", perm_filter=(key))
            if key in maxis and counter > maxis[key]:
                msg = f"Too many ({counter}) users with permission '{name}', use groups instead"
                problems.append(pb.Problem(typ.Type.BAD_PRACTICE, sev.Severity.MEDIUM, msg, concerned_object=perms_url))
        return problems

    def _audit_global_permissions(self):
        util.logger.info("--- Auditing global permissions ---")
        return self.__audit_user_permissions() + self.__audit_group_permissions()

    def _audit_lts_latest(self):
        sq_vers, v = self.version(3), None
        if sq_vers < self.lts(2):
            rule = rules.get_rule(rules.RuleId.BELOW_LTS)
            v = self.lts()
        elif sq_vers < self.lts(3):
            rule = rules.get_rule(rules.RuleId.LTS_PATCH_MISSING)
            v = self.lts()
        elif sq_vers < self.latest(2):
            rule = rules.get_rule(rules.RuleId.BELOW_LATEST)
            v = self.latest()
        if not v:
            return []
        msg = rule.msg.format(_version_as_string(sq_vers), _version_as_string(v))
        return [pb.Problem(rule.type, rule.severity, msg, concerned_object=self.url)]


# --------------------- Static methods -----------------
# this is a pointer to the module object instance itself.
this = sys.modules[__name__]
this.context = Environment("http://localhost:9000", "")


def set_env(some_url, some_token):
    this.context = Environment(some_url, some_token)
    util.logger.debug("Setting GLOBAL environment: %s@%s", util.redacted_token(some_token), some_url)


def _normalize_api(api):
    api = api.lower()
    if re.match(r"/api", api):
        pass
    elif re.match(r"api", api):
        api = "/" + api
    elif re.match(r"/", api):
        api = "/api" + api
    else:
        api = "/api/" + api
    return api


def post(api, params=None, ctxt=None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.post(api, params)


def edition(ctxt=None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.edition()


def delete(api, params=None, ctxt=None):
    if ctxt is None:
        ctxt = this.context
    return ctxt.delete(api, params)


def _audit_setting_value(key, platform_settings, audit_settings, url):
    v = _get_multiple_values(4, audit_settings[key], "MEDIUM", "CONFIGURATION")
    if v is None:
        util.logger.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    if v[0] not in platform_settings:
        util.logger.warning(_NON_EXISTING_SETTING_SKIPPED, v[0])
        return []
    util.logger.info("Auditing that setting %s has common/recommended value '%s'", v[0], v[1])
    s = platform_settings.get(v[0], "")
    if s == v[1]:
        return []
    return [pb.Problem(v[2], v[3], f"Setting {v[0]} has potentially incorrect or unsafe value '{s}'", concerned_object=url)]


def _audit_setting_in_range(key, platform_settings, audit_settings, sq_version, url):
    v = _get_multiple_values(5, audit_settings[key], "MEDIUM", "CONFIGURATION")
    if v is None:
        util.logger.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    if v[0] not in platform_settings:
        util.logger.warning(_NON_EXISTING_SETTING_SKIPPED, v[0])
        return []
    if v[0] == "sonar.dbcleaner.daysBeforeDeletingInactiveShortLivingBranches" and sq_version >= (8, 0, 0):
        util.logger.error("Setting %s is ineffective on SonaQube 8.0+, skipping audit", v[0])
        return []
    value, min_v, max_v = float(platform_settings[v[0]]), float(v[1]), float(v[2])
    util.logger.info(
        "Auditing that setting %s is within recommended range [%f-%f]",
        v[0],
        min_v,
        max_v,
    )
    if min_v <= value <= max_v:
        return []
    return [
        pb.Problem(v[4], v[3], f"Setting '{v[0]}' value {platform_settings[v[0]]} is outside recommended range [{v[1]}-{v[2]}]", concerned_object=url)
    ]


def _audit_setting_set(key, check_is_set, platform_settings, audit_settings, url):
    v = _get_multiple_values(3, audit_settings[key], "MEDIUM", "CONFIGURATION")
    if v is None:
        util.logger.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    if key not in platform_settings:
        util.logger.warning(_NON_EXISTING_SETTING_SKIPPED, key)
        return []
    util.logger.info("Auditing whether setting %s is set or not", key)
    problems = []
    if platform_settings[key] == "":
        if check_is_set:
            rule = rules.get_rule(rules.RuleId.SETTING_NOT_SET)
            problems = [pb.Problem(rule.type, rule.severity, rule.msg.format(key), concerned_object=url)]
        else:
            util.logger.info("Setting %s is not set", key)
    else:
        if not check_is_set:
            util.logger.info("Setting %s is set with value %s", key, platform_settings[key])
        else:
            problems = [pb.Problem(v[1], v[2], f"Setting {key} is set, although it should probably not", concerned_object=url)]

    return problems


def _audit_maintainability_rating_range(value, range, rating_letter, severity, domain, url):
    util.logger.debug(
        "Checking that maintainability rating threshold %3.0f%% for '%s' is within recommended range [%3.0f%%-%3.0f%%]",
        value * 100,
        rating_letter,
        range[0] * 100,
        range[1] * 100,
    )
    if range[0] <= value <= range[1]:
        return []
    return [
        pb.Problem(
            domain,
            severity,
            f"Maintainability rating threshold {value * 100}% for {rating_letter} "
            f"is NOT within recommended range [{range[0] * 100}%-{range[1] * 100}%]",
            concerned_object=url,
        )
    ]


def _audit_maintainability_rating_grid(platform_settings, audit_settings, url):
    thresholds = util.csv_to_list(platform_settings["sonar.technicalDebt.ratingGrid"])
    problems = []
    util.logger.debug("Auditing maintainabillity rating grid")
    for key in audit_settings:
        if not key.startswith("audit.globalSettings.maintainabilityRating"):
            continue
        (_, _, _, letter, _, _) = key.split(".")
        if letter not in ["A", "B", "C", "D"]:
            util.logger.error("Incorrect audit configuration setting %s, skipping audit", key)
            continue
        value = float(thresholds[ord(letter.upper()) - 65])
        v = _get_multiple_values(4, audit_settings[key], sev.Severity.MEDIUM, typ.Type.CONFIGURATION)
        if v is None:
            continue
        problems += _audit_maintainability_rating_range(value, (float(v[0]), float(v[1])), letter, v[2], v[3], url)
    return problems


def _get_multiple_values(n, setting, severity, domain):
    values = util.csv_to_list(setting)
    if len(values) < (n - 2):
        return None
    if len(values) == (n - 2):
        values.append(severity)
    if len(values) == (n - 1):
        values.append(domain)
    values[n - 2] = sev.to_severity(values[n - 2])
    values[n - 1] = typ.to_type(values[n - 1])
    # TODO Handle case of too many values
    return values


def _version_as_string(a_version):
    return ".".join([str(n) for n in a_version])
