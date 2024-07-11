#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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

    Abstraction of the SonarQube platform or instance concept

"""

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

import sonar.logging as log
import sonar.utilities as util

from sonar import errcodes, settings, devops, version, sif
from sonar.permissions import permissions, global_permissions, permission_templates
from sonar.audit import rules, config
import sonar.audit.severities as sev
import sonar.audit.types as typ
import sonar.audit.problem as pb

WRONG_CONFIG_MSG = "Audit config property %s has wrong value %s, skipping audit"

_NON_EXISTING_SETTING_SKIPPED = "Setting %s does not exist, skipping..."
_HTTP_ERROR = "%s Error: %s HTTP status code %d - %s"

_SONAR_TOOLS_AGENT = {"user-agent": f"sonar-tools {version.PACKAGE_VERSION}"}
_UPDATE_CENTER = "https://raw.githubusercontent.com/SonarSource/sonar-update-center-properties/master/update-center-source.properties"

LTA = None
LATEST = None
_HARDCODED_LTA = (9, 9, 5)
_HARDCODED_LATEST = (10, 5, 1)

_SERVER_ID_KEY = "Server ID"


class Platform:
    """Abstraction of the SonarQube "platform" concept"""

    def __init__(self, url: str, token: str, org: str = None, cert_file: str = None, http_timeout: int = 10, **kwargs) -> None:
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
        self.url = url.rstrip("/").lower()  #: SonarQube URL
        self.__token = token
        self.__cert_file = cert_file
        self.__user_data = None
        self._version = None
        self.__sys_info = None
        self.__global_nav = None
        self._server_id = None
        self._permissions = None
        self.http_timeout = http_timeout
        self.organization = org
        self.__is_sonarcloud = util.is_sonarcloud_url(self.url)

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
        :return: the SonarQube platform version, or 0.0.0 for SonarCloud
        :rtype: tuple or str
        """
        if self.is_sonarcloud():
            return "sonarcloud" if as_string else tuple(int(n) for n in [0, 0, 0][0:digits])
        if digits < 1 or digits > 3:
            digits = 3
        if self._version is None:
            self._version = self.get("/api/server/version").text.split(".")
            log.debug("Version = %s", self._version)
        if as_string:
            return ".".join(self._version[0:digits])
        else:
            return tuple(int(n) for n in self._version[0:digits])

    def edition(self):
        """
        :return: the SonarQube platform edition
        :rtype: str ("community", "developer", "enterprise" or "datacenter")
        """
        if self.is_sonarcloud():
            return "sonarcloud"
        if "edition" in self.global_nav():
            return util.edition_normalize(self.global_nav()["edition"])
        else:
            return util.edition_normalize(self.sys_info()["Statistics"]["edition"])

    def user(self) -> str:
        """Returns the user corresponding to the provided token"""
        return self.user_data()["login"]

    def user_data(self) -> dict[str, str]:
        """Returns the user data corresponding to the provided token"""
        if self.__user_data is None:
            self.__user_data = json.loads(self.get("api/users/current").text)
        return self.__user_data

    def server_id(self):
        """
        :return: the SonarQube platform server id
        :rtype: str
        """
        if self._server_id is not None:
            return self._server_id
        if self.__sys_info is not None and _SERVER_ID_KEY in self.__sys_info["System"]:
            self._server_id = self.__sys_info["System"][_SERVER_ID_KEY]
        else:
            self._server_id = json.loads(self.get("system/status").text)["id"]
        return self._server_id

    def is_sonarcloud(self) -> bool:
        """
        :return: whether the target platform is SonarCloud
        :rtype: bool
        """
        return self.__is_sonarcloud

    def basics(self):
        """
        :return: the 3 basic information of the platform: ServerId, Edition and Version
        :rtype: dict{"serverId": <id>, "edition": <edition>, "version": <version>}
        """
        if self.is_sonarcloud():
            return {"edition": self.edition()}

        return {
            "version": self.version(as_string=True),
            "edition": self.edition(),
            "serverId": self.server_id(),
        }

    def get(self, api: str, params: dict[str, str] = None, exit_on_error: bool = False, mute: tuple[HTTPStatus] = ()) -> requests.Response:
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
        return self.__run_request(requests.get, api, params, exit_on_error, mute)

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
        return self.__run_request(requests.post, api, params, exit_on_error, mute)

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
        return self.__run_request(requests.delete, api, params, exit_on_error, mute)

    def __run_request(
        self, request: callable, api: str, params: dict[str, str] = None, exit_on_error: bool = False, mute: tuple[HTTPStatus] = ()
    ) -> requests.Response:
        """Makes an HTTP request to SonarQube"""
        api = _normalize_api(api)
        headers = _SONAR_TOOLS_AGENT
        if params is None:
            params = {}
        if self.is_sonarcloud():
            headers["Authorization"] = f"Bearer {self.__token}"
            params["organization"] = self.organization
        log.debug("%s: %s", getattr(request, "__name__", repr(request)).upper(), self.__urlstring(api, params))

        try:
            retry = True
            while retry:
                r = request(
                    url=self.url + api,
                    auth=self.__credentials(),
                    verify=self.__cert_file,
                    headers=headers,
                    params=params,
                    timeout=self.http_timeout,
                )
                (retry, new_url) = _check_for_retry(r)
                if retry:
                    self.url = new_url
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if exit_on_error or (r.status_code not in mute and r.status_code == HTTPStatus.UNAUTHORIZED):
                util.log_and_exit(r)
            else:
                _, msg = util.http_error(r)
                if r.status_code in mute:
                    log.debug(_HTTP_ERROR, "GET", self.__urlstring(api, params), r.status_code, msg)
                else:
                    log.error(_HTTP_ERROR, "GET", self.__urlstring(api, params), r.status_code, msg)
                raise e
        except requests.exceptions.Timeout as e:
            util.exit_fatal(str(e), errcodes.HTTP_TIMEOUT)
        except requests.RequestException as e:
            util.exit_fatal(str(e), errcodes.SONAR_API)
        return r

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
        if self.is_sonarcloud():
            return {"System": {_SERVER_ID_KEY: "sonarcloud"}}
        if self.__sys_info is None:
            success, counter = False, 0
            while not success:
                try:
                    resp = self.get("system/info", mute=(HTTPStatus.INTERNAL_SERVER_ERROR,))
                    success = True
                except HTTPError as e:
                    # Hack: SonarQube randomly returns Error 500 on this API, retry up to 10 times
                    if e.response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR and counter < 10:
                        log.error("HTTP Error 500 for api/system/info, retrying...")
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
        if self.is_sonarcloud():
            return "postgres"
        if self.version() < (9, 7, 0):
            return self.sys_info()["Statistics"]["database"]["name"]
        return self.sys_info()["Database"]["Database"]

    def plugins(self):
        """
        :return: the SonarQube platform plugins
        :rtype: dict
        """
        if self.is_sonarcloud():
            return {}
        if self.version() < (9, 7, 0):
            return self.sys_info()["Statistics"]["plugins"]
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
            for setting_key in "value", "values", "fieldValues":
                if setting_key in s:
                    platform_settings[s["key"]] = s[setting_key]
        return platform_settings

    def __settings(self, settings_list: list[str] = None, include_not_set: bool = False) -> dict[str, settings.Setting]:
        log.info("getting global settings")
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
        from sonar import webhooks

        return webhooks.get_list(self)

    def export(self, export_settings: dict[str, str], full: bool = False) -> dict[str, str]:
        """Exports the global platform properties as JSON

        :param full: Whether to also export properties that cannot be set, defaults to False
        :type full: bool, optional
        :return: dict of all properties with their values
        :rtype: dict
        """
        log.info("Exporting platform global settings")
        json_data = {}
        for s in self.__settings(include_not_set=export_settings["EXPORT_DEFAULTS"]).values():
            if s.is_internal():
                continue
            (categ, subcateg) = s.category()
            if self.is_sonarcloud() and categ == settings.THIRD_PARTY_SETTINGS:
                # What is reported as 3rd part are SonarCloud internal settings
                continue
            util.update_json(json_data, categ, subcateg, s.to_json(export_settings["INLINE_LISTS"]))

        hooks = {}
        for wb in self.webhooks().values():
            j = util.remove_nones(wb.to_json(full))
            j.pop("name", None)
            hooks[wb.name] = j
        if len(hooks) > 0:
            json_data[settings.GENERAL_SETTINGS].update({"webhooks": hooks})
        json_data["permissions"] = self.global_permissions().export(export_settings=export_settings)
        json_data["permissionTemplates"] = permission_templates.export(self, export_settings=export_settings)
        if not self.is_sonarcloud():
            json_data[settings.DEVOPS_INTEGRATION] = devops.export(self, export_settings=export_settings)
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
        log.debug("Current WH %s", str(current_wh_names))
        for wh_name, wh in webhooks_data.items():
            log.debug("Updating wh with name %s", wh_name)
            if wh_name in current_wh_names:
                current_wh[wh_map[wh_name]].update(name=wh_name, **wh)
            # else:
            #     webhooks.update(name=wh_name, endpoint=self, project=None, **wh)

    def import_config(self, config_data):
        """Imports a whole SonarQube platform global configuration represented as JSON

        :param config_data: the configuration representation
        :type config_data: dict
        :return: Nothing
        """
        if "globalSettings" not in config_data:
            log.info("No global settings to import")
            return
        config_data = config_data["globalSettings"]
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
        log.info("--- Auditing global settings ---")
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

        problems += (
            self._audit_project_default_visibility()
            + self._audit_global_permissions()
            + self._audit_logs(audit_settings)
            + permission_templates.audit(self, audit_settings)
        )
        for wh in self.webhooks().values():
            problems += wh.audit()

        if self.is_sonarcloud():
            return problems

        pf_sif = self.sys_info()
        if self.version() >= (9, 7, 0):
            # Hack: Manually add edition in SIF (it's removed starting from 9.7 :-()
            pf_sif["edition"] = self.edition()
        problems += (
            _audit_maintainability_rating_grid(platform_settings, audit_settings, settings_url)
            + self._audit_admin_password()
            + self._audit_lta_latest()
            + sif.Sif(pf_sif, self).audit(audit_settings)
            + permission_templates.audit(self, audit_settings)
        )
        return problems

    def _audit_logs(self, audit_settings: dict[str, str]) -> list[pb.Problem]:
        if not audit_settings.get("audit.logs", True):
            log.info("Logs audit is disabled, skipping logs audit...")
            return []
        log_map = {"app": "sonar.log", "ce": "ce.log", "web": "web.log", "es": "es.log"}
        problems = []
        for logtype, logfile in log_map.items():
            logs = self.get("system/logs", params={"name": logtype}).text
            for line in logs.splitlines():
                log.debug("Inspection log line %s", line)
                try:
                    (_, level, _) = line.split(" ", maxsplit=2)
                except ValueError:
                    # Not the standard log line, must be a stacktrace or something, just skip
                    continue
                rule = None
                if level == "ERROR":
                    log.warning("Error found in %s: %s", logfile, line)
                    rule = rules.get_rule(rules.RuleId.ERROR_IN_LOGS)
                elif level == "WARN":
                    log.warning("Warning found in %s: %s", logfile, line)
                    rule = rules.get_rule(rules.RuleId.WARNING_IN_LOGS)
                if rule is not None:
                    problems.append(pb.Problem(broken_rule=rule, msg=rule.msg.format(logfile, line), concerned_object=f"{self.url}/admin/system"))
        logs = self.get("system/logs", params={"name": "deprecation"}).text
        nb_deprecation = len(logs.splitlines())
        if nb_deprecation > 0:
            rule = rules.get_rule(rules.RuleId.DEPRECATION_WARNINGS)
            msg = rule.msg.format(nb_deprecation)
            problems.append(pb.Problem(broken_rule=rule, msg=msg, concerned_object=f"{self.url}/admin/system"))
            log.warning(msg)
        return problems

    def _audit_project_default_visibility(self):
        log.info("Auditing project default visibility")
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
        log.info("Project default visibility is '%s'", visi)
        if config.get_property("checkDefaultProjectVisibility") and visi != "private":
            rule = rules.get_rule(rules.RuleId.SETTING_PROJ_DEFAULT_VISIBILITY)
            problems.append(pb.Problem(broken_rule=rule, msg=rule.msg.format(visi), concerned_object=f"{self.url}/admin/projects_management"))
        return problems

    def _audit_admin_password(self):
        log.info("Auditing admin password")
        problems = []
        try:
            r = requests.get(url=self.url + "/api/authentication/validate", auth=("admin", "admin"), timeout=self.http_timeout)
            data = json.loads(r.text)
            if data.get("valid", False):
                rule = rules.get_rule(rules.RuleId.DEFAULT_ADMIN_PASSWORD)
                problems.append(pb.Problem(broken_rule=rule, msg=rule.msg, concerned_object=self.url))
            else:
                log.info("User 'admin' default password has been changed")
        except requests.RequestException as e:
            util.exit_fatal(str(e), errcodes.SONAR_API)
        return problems

    def __audit_group_permissions(self):
        log.info("Auditing group global permissions")
        problems = []
        perms_url = f"{self.url}/admin/permissions"
        groups = self.global_permissions().groups()
        if len(groups) > 10:
            rule = rules.get_rule(rule_id=rules.RuleId.RISKY_GLOBAL_PERMISSIONS)
            msg = f"Too many ({len(groups)}) groups with global permissions"
            problems.append(pb.Problem(broken_rule=rule, msg=msg, concerned_object=perms_url))

        for gr_name, gr_perms in groups.items():
            if gr_name == "Anyone":
                rule = rules.get_rule(rules.RuleId.ANYONE_WITH_GLOBAL_PERMS)
                problems.append(pb.Problem(broken_rule=rule, msg=rule.msg, concerned_object=perms_url))
            if gr_name == "sonar-users" and (
                "admin" in gr_perms or "gateadmin" in gr_perms or "profileadmin" in gr_perms or "provisioning" in gr_perms
            ):
                rule = rules.get_rule(rules.RuleId.SONAR_USERS_WITH_ELEVATED_PERMS)
                problems.append(pb.Problem(broken_rule=rule, msg=rule.msg, concerned_object=perms_url))

        maxis = {"admin": 2, "gateadmin": 2, "profileadmin": 2, "scan": 2, "provisioning": 3}
        for key, name in permissions.ENTERPRISE_GLOBAL_PERMISSIONS.items():
            counter = self.global_permissions().count(perm_type="groups", perm_filter=(key,))
            if key in maxis and counter > maxis[key]:
                rule = rules.get_rule(rule_id=rules.RuleId.RISKY_GLOBAL_PERMISSIONS)
                msg = f"Too many ({counter}) groups with permission '{name}', {maxis[key]} max recommended"
                problems.append(pb.Problem(broken_rule=rule, msg=msg, concerned_object=perms_url))
        return problems

    def __audit_user_permissions(self):
        log.info("Auditing users global permissions")
        problems = []
        perms_url = f"{self.url}/admin/permissions"
        users = self.global_permissions().users()
        if len(users) > 10:
            rule = rules.get_rule(rule_id=rules.RuleId.RISKY_GLOBAL_PERMISSIONS)
            msg = f"Too many ({len(users)}) users with direct global permissions, use groups instead"
            problems.append(pb.Problem(broken_rule=rule, msg=msg, concerned_object=perms_url))

        maxis = {"admin": 3, "gateadmin": 3, "profileadmin": 3, "scan": 3, "provisioning": 3}
        for key, name in permissions.ENTERPRISE_GLOBAL_PERMISSIONS.items():
            counter = self.global_permissions().count(perm_type="users", perm_filter=(key,))
            if key in maxis and counter > maxis[key]:
                rule = rules.get_rule(rule_id=rules.RuleId.RISKY_GLOBAL_PERMISSIONS)
                msg = f"Too many ({counter}) users with permission '{name}', use groups instead"
                problems.append(pb.Problem(broken_rule=rule, msg=msg, concerned_object=perms_url))
        return problems

    def _audit_global_permissions(self):
        log.info("--- Auditing global permissions ---")
        return self.__audit_user_permissions() + self.__audit_group_permissions()

    def _audit_lta_latest(self) -> list[pb.Problem]:
        if self.is_sonarcloud():
            return []
        sq_vers, v = self.version(3), None
        if sq_vers < lta(2):
            rule = rules.get_rule(rules.RuleId.BELOW_LTA)
            v = lta()
        elif sq_vers < lta(3):
            rule = rules.get_rule(rules.RuleId.LTA_PATCH_MISSING)
            v = lta()
        elif sq_vers[:2] > lta(2) and sq_vers < latest(2):
            rule = rules.get_rule(rules.RuleId.BELOW_LATEST)
            v = latest()
        if not v:
            return []
        msg = rule.msg.format(_version_as_string(sq_vers), _version_as_string(v))
        return [pb.Problem(broken_rule=rule, msg=msg, concerned_object=self.url)]


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
        log.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    if v[0] not in platform_settings:
        log.warning(_NON_EXISTING_SETTING_SKIPPED, v[0])
        return []
    log.info("Auditing that setting %s has common/recommended value '%s'", v[0], v[1])
    s = platform_settings.get(v[0], "")
    if s == v[1]:
        return []
    rule = rules.get_rule(rules.RuleId.DUBIOUS_GLOBAL_SETTING)
    msg = f"Setting {v[0]} has potentially incorrect or unsafe value '{s}'"
    return [pb.Problem(broken_rule=rule, msg=msg, concerned_object=url)]


def _audit_setting_in_range(key, platform_settings, audit_settings, sq_version, url):
    v = _get_multiple_values(5, audit_settings[key], "MEDIUM", "CONFIGURATION")
    if v is None:
        log.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    if v[0] not in platform_settings:
        log.warning(_NON_EXISTING_SETTING_SKIPPED, v[0])
        return []
    if v[0] == "sonar.dbcleaner.daysBeforeDeletingInactiveShortLivingBranches" and sq_version >= (8, 0, 0):
        log.error("Setting %s is ineffective on SonaQube 8.0+, skipping audit", v[0])
        return []
    value, min_v, max_v = float(platform_settings[v[0]]), float(v[1]), float(v[2])
    log.info(
        "Auditing that setting %s is within recommended range [%.2f-%.2f]",
        v[0],
        min_v,
        max_v,
    )
    if min_v <= value <= max_v:
        return []
    rule = rules.get_rule(rules.RuleId.DUBIOUS_GLOBAL_SETTING)
    msg = f"Setting '{v[0]}' value {platform_settings[v[0]]} is outside recommended range [{v[1]}-{v[2]}]"
    return [pb.Problem(broken_rule=rule, msg=msg, concerned_object=url)]


def _audit_setting_set(key, check_is_set, platform_settings, audit_settings, url):
    v = _get_multiple_values(3, audit_settings[key], "MEDIUM", "CONFIGURATION")
    if v is None:
        log.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    log.info("Auditing whether setting %s is set or not", v[0])
    if platform_settings.get(v[0], "") == "":  # Setting is not set
        if check_is_set:
            rule = rules.get_rule(rules.RuleId.SETTING_NOT_SET)
            return [pb.Problem(broken_rule=rule, msg=rule.msg.format(v[0]), concerned_object=url)]
        log.info("Setting %s is not set", v[0])
    else:
        if not check_is_set:
            rule = rules.get_rule(rules.RuleId.SETTING_SET)
            return [pb.Problem(broken_rule=rule, msg=rule.msg, concerned_object=url)]
        log.info("Setting %s is set with value %s", v[0], platform_settings[v[0]])
    return []


def _audit_maintainability_rating_range(value: float, range: tuple[float, float], rating_letter: str, url: str):
    log.info(
        "Checking that maintainability rating threshold %.1f%% for '%s' is within recommended range [%.1f%%-%.1f%%]",
        value * 100,
        rating_letter,
        range[0] * 100,
        range[1] * 100,
    )
    if range[0] <= value <= range[1]:
        return []
    rule = rules.get_rule(rules.RuleId.SETTING_MAINT_GRID)
    msg = rule.msg.format(f"{value * 100:.1f}", rating_letter, f"{range[0] * 100:.1f}", f"{range[1] * 100:.1f}")
    return [pb.Problem(broken_rule=rule, msg=msg, concerned_object=url)]


def _audit_maintainability_rating_grid(platform_settings, audit_settings, url):
    thresholds = util.csv_to_list(platform_settings["sonar.technicalDebt.ratingGrid"])
    problems = []
    log.info("Auditing maintainability rating grid")
    for key in audit_settings:
        if not key.startswith("audit.globalSettings.maintainabilityRating"):
            continue
        (_, _, _, letter, _, _) = key.split(".")
        if letter not in ["A", "B", "C", "D"]:
            log.error("Incorrect audit configuration setting %s, skipping audit", key)
            continue
        value = float(thresholds[ord(letter.upper()) - 65])
        v = _get_multiple_values(4, audit_settings[key], sev.Severity.MEDIUM, typ.Type.CONFIGURATION)
        if v is None:
            continue
        problems += _audit_maintainability_rating_range(value, (float(v[0]), float(v[1])), letter, url)
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


def __lta_and_latest() -> tuple[tuple[int], tuple[int]]:
    """Returns the current version of LTA and LATEST, if possible querying the update center,
    using hardcoded values as fallback"""
    global LTA
    global LATEST
    if LTA is None:
        log.debug("Attempting to reach Sonar update center")
        _, tmpfile = tempfile.mkstemp(prefix="sonar-tools", suffix=".txt", text=True)
        try:
            with open(tmpfile, "w", encoding="utf-8") as fp:
                print(requests.get(_UPDATE_CENTER, headers=_SONAR_TOOLS_AGENT, timeout=10).text, file=fp)
            with open(tmpfile, "r", encoding="utf-8") as fp:
                upd_center_props = jprops.load_properties(fp)
            v = upd_center_props.get("ltsVersion", "9.9.0").split(".")
            if len(v) == 2:
                v.append("0")
            LTA = tuple(int(n) for n in v)
            v = upd_center_props.get("publicVersions", "10.4").split(",")[-1].split(".")
            if len(v) == 2:
                v.append("0")
            LATEST = tuple(int(n) for n in v)
            log.debug("Sonar update center says LTA (ex-LTS) = %s, LATEST = %s", str(LTA), str(LATEST))
        except (EnvironmentError, requests.exceptions.HTTPError):
            LTA = _HARDCODED_LTA
            LATEST = _HARDCODED_LATEST
            log.debug("Sonar update center read failed, hardcoding LTA (ex-LTS) = %s, LATEST = %s", str(LTA), str(LATEST))
        try:
            os.remove(tmpfile)
        except EnvironmentError:
            pass
    return LTA, LATEST


def lta(digits=3) -> tuple[int]:
    """
    :return: the current SonarQube LTA (ex-LTS) version
    :params digits: number of digits to consider in the version (min 1, max 3), defaults to 3
    :type digits: int, optional
    :rtype: tuple (x, y, z)
    """
    if digits < 1 or digits > 3:
        digits = 3
    return __lta_and_latest()[0][0:digits]


def latest(digits=3):
    """
    :return: the current SonarQube LATEST version
    :params digits: number of digits to consider in the version (min 1, max 3), defaults to 3
    :type digits: int, optional
    :rtype: tuple (x, y, z)
    """
    if digits < 1 or digits > 3:
        digits = 3
    return __lta_and_latest()[1][0:digits]


def _check_for_retry(response: requests.models.Response) -> tuple[bool, str]:
    """Verifies if a response had a 301 Moved permanently and if so provide the new location"""
    if len(response.history) > 0 and response.history[0].status_code == HTTPStatus.MOVED_PERMANENTLY:
        new_url = "/".join(response.history[0].headers["Location"].split("/")[0:3])
        log.debug("Moved permanently to URL %s", new_url)
        return True, new_url
    return False, None
