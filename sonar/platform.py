#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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

from http import HTTPStatus
import sys
import os
import time
import datetime
import json
import tempfile
import requests
import jprops
from requests.exceptions import HTTPError

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
_HTTP_ERROR = "%s Error: %s HTTP status code %d"

_SONAR_TOOLS_AGENT = {"user-agent": f"sonar-tools {version.PACKAGE_VERSION}"}
_UPDATE_CENTER = "https://raw.githubusercontent.com/SonarSource/sonar-update-center-properties/master/update-center-source.properties"

LTS = None
LATEST = None
_HARDCODED_LTS = (9, 9, 3)
_HARDCODED_LATEST = (10, 3, 0)


class Platform:
    """Abstraction of the SonarQube "platform" concept"""

    def __init__(self, some_url, some_token, cert_file=None):
        """Creates a SonarQube platform object

        :param some_url: base URL of the SonarQube platform
        :type some_url: str
        :param some_token: token to connect to the platform
        :type some_token: str
        :param cert_file: Client certificate, if any needed, defaults to None
        :type cert_file: str, optional
        :return: the SonarQube object
        :rtype: Platform
        """
        self.url = some_url  #: SonarQube URL
        self.__token = some_token
        self.__cert_file = cert_file
        self._version = None
        self.__sys_info = None
        self.__global_nav = None
        self._server_id = None
        self._permissions = None

    def __str__(self):
        """
        :return: string representation of the SonarQube connection, with the token recognizable but largely redacted
        :rtype: str
        """
        return f"{util.redacted_token(self.__token)}@{self.url}"

    def __credentials(self):
        return (self.__token, "")

    def version(self, digits=3, as_string=False):
        """Returns the SonarQube platform version

        :param digits: Number of digits to include in the version, defaults to 3
        :type digits: int, optional
        :param as_string: Whether to return the version as string or tuple, default to False (ie returns a tuple)
        :type as_string: bool, optional
        :return: the SonarQube platform version
        :rtype: tuple or str
        """
        if digits < 1 or digits > 3:
            digits = 3
        if self._version is None:
            self._version = self.get("/api/server/version").text.split(".")
        if as_string:
            return ".".join(self._version[0:digits])
        else:
            return tuple(int(n) for n in self._version[0:digits])

    def edition(self):
        """
        :return: the SonarQube platform edition
        :rtype: str ("community", "developer", "enterprise" or "datacenter")
        """
        if self.version() < (9, 7, 0):
            return self.sys_info()["Statistics"]["edition"]
        else:
            return self.global_nav()["edition"]

    def server_id(self):
        """
        :return: the SonarQube platform server id
        :rtype: str
        """
        if self._server_id is not None:
            return self._server_id
        if self.__sys_info is not None and "Server ID" in self.__sys_info["System"]:
            self._server_id = self.__sys_info["System"]["Server ID"]
        else:
            self._server_id = json.loads(self.get("system/status").text)["id"]
        return self._server_id

    def basics(self):
        """
        :return: the 3 basic information of the platform: ServerId, Edition and Version
        :rtype: dict{"serverId": <id>, "edition": <edition>, "version": <version>}
        """
        return {
            "version": self.version(as_string=True),
            "edition": self.edition(),
            "serverId": self.server_id(),
        }

    def get(self, api, params=None, exit_on_error=False, mute=()):
        """Makes an HTTP GET request to SonarQube

        :param api: API to invoke (without the platform base URL)
        :type api: str
        :param params: params to pass in the HTTP request, defaults to None
        :type params: dict, optional
        :param exit_on_error: When to fail fast and exit if the HTTP status code is not 2XX, defaults to True
        :type exit_on_error: bool, optional
        :param mute: Tuple of HTTP Error codes to mute (ie not write an error log for), defaults to None.
        Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :type mute: tuple, optional
        :return: the result of the HTTP request
        :rtype: request.Response
        """
        api = _normalize_api(api)
        util.logger.debug("GET: %s", self.__urlstring(api, params))
        try:
            r = requests.get(url=self.url + api, auth=self.__credentials(), verify=self.__cert_file, headers=_SONAR_TOOLS_AGENT, params=params)
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if exit_on_error or (r.status_code not in mute and r.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN)):
                util.log_and_exit(r)
            else:
                if r.status_code in mute:
                    util.logger.debug(_HTTP_ERROR, "GET", self.__urlstring(api, params), r.status_code)
                else:
                    util.logger.error(_HTTP_ERROR, "GET", self.__urlstring(api, params), r.status_code)
                raise e
        except requests.RequestException as e:
            util.exit_fatal(str(e), options.ERR_SONAR_API)
        return r

    def post(self, api, params=None, exit_on_error=False, mute=()):
        """Makes an HTTP POST request to SonarQube

        :param api: API to invoke (without the platform base URL)
        :type api: str
        :param params: params to pass in the HTTP request, defaults to None
        :type params: dict, optional
        :param exit_on_error: When to fail fast and exit if the HTTP status code is not 2XX, defaults to True
        :type exit_on_error: bool, optional
        :param mute: HTTP Error codes to mute (ie not write an error log for), defaults to None
        Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :type mute: tuple, optional
        :return: the result of the HTTP request
        :rtype: request.Response
        """
        api = _normalize_api(api)
        util.logger.debug("POST: %s", self.__urlstring(api, params))
        try:
            r = requests.post(url=self.url + api, auth=self.__credentials(), verify=self.__cert_file, headers=_SONAR_TOOLS_AGENT, data=params)
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            if exit_on_error or r.status_code in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                util.log_and_exit(r)
            else:
                if r.status_code in mute:
                    util.logger.debug(_HTTP_ERROR, "POST", self.__urlstring(api, params), r.status_code)
                else:
                    util.logger.error(_HTTP_ERROR, "POST", self.__urlstring(api, params), r.status_code)
                raise
        except requests.RequestException as e:
            util.exit_fatal(str(e), options.ERR_SONAR_API)
        return r

    def delete(self, api, params=None, exit_on_error=False, mute=()):
        """Makes an HTTP DELETE request to SonarQube

        :param api: API to invoke (without the platform base URL)
        :type api: str
        :param params: params to pass in the HTTP request, defaults to None
        :type params: dict, optional
        :param exit_on_error: When to fail fast and exit if the HTTP status code is not 2XX, defaults to True
        :type exit_on_error: bool, optional
        :param mute: HTTP Error codes to mute (ie not write an error log for), defaults to None
        Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :type mute: tuple, optional
        :return: the result of the HTTP request
        :rtype: request.Response
        """
        api = _normalize_api(api)
        util.logger.debug("DELETE: %s", self.__urlstring(api, params))
        try:
            r = requests.delete(url=self.url + api, auth=self.__credentials(), verify=self.__cert_file, params=params, headers=_SONAR_TOOLS_AGENT)
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            if exit_on_error:
                util.log_and_exit(r)
            else:
                if r.status_code in mute:
                    util.logger.debug(_HTTP_ERROR, "DELETE", self.__urlstring(api, params), r.status_code)
                else:
                    util.logger.error(_HTTP_ERROR, "DELETE", self.__urlstring(api, params), r.status_code)
                raise
        except requests.RequestException as e:
            util.exit_fatal(str(e), options.ERR_SONAR_API)

    def global_permissions(self):
        """Returns the SonarQube platform global permissions

        :return: dict{"users": {<login>: <permissions comma separated>, ...}, "groups"; {<name>: <permissions comma separated>, ...}}}
        :rtype: dict
        """
        if self._permissions is None:
            self._permissions = global_permissions.GlobalPermissions(self)
        return self._permissions

    def sys_info(self):
        """
        :return: the SonarQube platform system info file
        :rtype: dict
        """
        if self.__sys_info is None:
            success, counter = False, 0
            while not success:
                try:
                    resp = self.get("system/info", mute=(HTTPStatus.INTERNAL_SERVER_ERROR,))
                    success = True
                except HTTPError as e:
                    # Hack: SonarQube randomly returns Error 500 on this API, retry up to 10 times
                    if e.response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR and counter < 10:
                        util.logger.error("HTTP Error 500 for api/system/info, retrying...")
                        time.sleep(0.5)
                        counter += 1
                    else:
                        raise e
            self.__sys_info = json.loads(resp.text)
            success = True
        return self.__sys_info

    def global_nav(self):
        """
        :return: the SonarQube platform global navigation data
        :rtype: dict
        """
        if self.__global_nav is None:
            resp = self.get("navigation/global", mute=(HTTPStatus.INTERNAL_SERVER_ERROR,))
            self.__global_nav = json.loads(resp.text)
        return self.__global_nav

    def database(self):
        """
        :return: the SonarQube platform backend database
        :rtype: str
        """
        if self.version() < (9, 7, 0):
            return self.sys_info()["Statistics"]["database"]["name"]
        else:
            return self.sys_info()["Database"]["Database"]

    def plugins(self):
        """
        :return: the SonarQube platform plugins
        :rtype: dict
        """
        if self.version() < (9, 7, 0):
            return self.sys_info()["Statistics"]["plugins"]
        else:
            return self.sys_info()["Plugins"]

    def get_settings(self, settings_list=None):
        """Returns a list of (or all) platform global settings value from their key

        :param key: settings_list
        :type key: list or str (comma separated)
        :return: the list of settings values
        :rtype: dict{<key>: <value>, ...}
        """
        params = util.remove_nones({"keys": util.list_to_csv(settings_list)})
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

    def __settings(self, settings_list=None, include_not_set=False):
        util.logger.info("getting global settings")
        return settings.get_bulk(endpoint=self, settings_list=settings_list, include_not_set=include_not_set)

    def get_setting(self, key):
        """Returns a platform global setting value from its key

        :param key: Setting key
        :type key: str
        :return: the setting value
        :rtype: str or dict
        """
        return self.get_settings(key).get(key, None)

    def reset_setting(self, key):
        """Resets a platform global setting to the SonarQube internal default value

        :param key: Setting key
        :type key: str
        :return: Whether the reset was successful or not
        :rtype: bool
        """
        return settings.reset_setting(self, key).ok

    def set_setting(self, key, value):
        """Sets a platform global setting

        :param key: Setting key
        :type key: str
        :param key: value
        :type key: str
        :return: Whether setting the value was successful or not
        :rtype: bool
        """
        return settings.set_setting(self, key, value)

    def __urlstring(self, api, params):
        """Returns a string corresponding to the URL and parameters"""
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
        """
        :return: the list of global webhooks
        :rtype: dict{<webhook_name>: <webhook_data>, ...}
        """
        return webhooks.get_list(self)

    def export(self, full=False):
        """Exports the global platform properties as JSON

        :param full: Whether to also export properties thatc annot be set, defaults to False
        :type full: bool, optional
        :return: dict of all properties with their values
        :rtype: dict
        """
        util.logger.info("Exporting platform global settings")
        json_data = {}
        for s in self.__settings(include_not_set=True).values():
            (categ, subcateg) = s.category()
            util.update_json(json_data, categ, subcateg, s.to_json())

        json_data[settings.GENERAL_SETTINGS].update({"webhooks": webhooks.export(self, full=full)})
        json_data["permissions"] = self.global_permissions().export()
        json_data["permissionTemplates"] = permission_templates.export(self, full=full)
        json_data[settings.DEVOPS_INTEGRATION] = devops.export(self, full=full)
        return json_data

    def set_webhooks(self, webhooks_data):
        """Sets global webhooks with a list of webhooks represented as JSON

        :param webhooks_data: the webhooks representation
        :type webhooks_data: dict
        :return: Nothing
        """
        if webhooks_data is None:
            return
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
        """Imports a whole SonarQube platform global configuration represented as JSON

        :param config_data: the configuration representation
        :type config_data: dict
        :return: Nothing
        """
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

    def audit(self, audit_settings=None):
        """Audits a global platform configuration and returns the list of problems found

        :param audit_settings: Options of what to audit and thresholds to raise problems
        :type audit_settings: dict
        :return: List of problems found, or empty list
        :rtype: list[Problem]
        """
        util.logger.info("--- Auditing global settings ---")
        problems = []
        platform_settings = self.get_settings()
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

        pf_sif = self.sys_info()
        if self.version() >= (9, 7, 0):
            # Hack: Manually add edition in SIF (it's removed starting from 9.7 :-()
            pf_sif["edition"] = self.edition()
        problems += (
            _audit_maintainability_rating_grid(platform_settings, audit_settings, settings_url)
            + self._audit_project_default_visibility()
            + self._audit_admin_password()
            + self._audit_global_permissions()
            + self._audit_lts_latest()
            + sif.Sif(pf_sif, self).audit(audit_settings)
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
        if sq_vers < lts(2):
            rule = rules.get_rule(rules.RuleId.BELOW_LTS)
            v = lts()
        elif sq_vers < lts(3):
            rule = rules.get_rule(rules.RuleId.LTS_PATCH_MISSING)
            v = lts()
        elif sq_vers < latest(2):
            rule = rules.get_rule(rules.RuleId.BELOW_LATEST)
            v = latest()
        if not v:
            return []
        msg = rule.msg.format(_version_as_string(sq_vers), _version_as_string(v))
        return [pb.Problem(rule.type, rule.severity, msg, concerned_object=self.url)]


# --------------------- Static methods -----------------
# this is a pointer to the module object instance itself.
this = sys.modules[__name__]
this.context = Platform(os.getenv("SONAR_HOST_URL", "http://localhost:9000"), os.getenv("SONAR_TOKEN", ""))


def _normalize_api(api):
    api = api.lower()
    if api.startswith("/api"):
        pass
    elif api.startswith("api"):
        api = "/" + api
    elif api.startswith("/"):
        api = "/api" + api
    else:
        api = "/api/" + api
    return api


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


def __lts_and_latest():
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


def lts(digits=3):
    """
    :return: the current SonarQube LTS version
    :params digits: number of digits to consider in the version (min 1, max 3), defaults to 3
    :type digits: int, optional
    :rtype: tuple (x, y, z)
    """
    if digits < 1 or digits > 3:
        digits = 3
    return __lts_and_latest()[0][0:digits]


def latest(digits=3):
    """
    :return: the current SonarQube LATEST version
    :params digits: number of digits to consider in the version (min 1, max 3), defaults to 3
    :type digits: int, optional
    :rtype: tuple (x, y, z)
    """
    if digits < 1 or digits > 3:
        digits = 3
    return __lts_and_latest()[1][0:digits]
