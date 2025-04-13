#
# sonar-tools
# Copyright (C) 2019-2025 Olivier Korach
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
from typing import Optional
import time
import datetime
import json
import tempfile
import requests
import jprops
from requests import HTTPError, RequestException

import sonar.logging as log
import sonar.utilities as util
from sonar.util import types, constants as c

from sonar import errcodes, settings, devops, version, sif, exceptions
from sonar.permissions import permissions, global_permissions, permission_templates
from sonar.audit.rules import get_rule, RuleId
import sonar.audit.severities as sev
import sonar.audit.types as typ
from sonar.audit.problem import Problem

WRONG_CONFIG_MSG = "Audit config property %s has wrong value %s, skipping audit"

_NON_EXISTING_SETTING_SKIPPED = "Setting %s does not exist, skipping..."

_SONAR_TOOLS_AGENT = f"sonar-tools {version.PACKAGE_VERSION}"
_UPDATE_CENTER = "https://raw.githubusercontent.com/SonarSource/sonar-update-center-properties/master/update-center-source.properties"

_APP_JSON = "application/json"
LTA = None
LATEST = None
_HARDCODED_LTA = (9, 9, 6)
_HARDCODED_LATEST = (10, 6, 0)

_SERVER_ID_KEY = "Server ID"


class Platform(object):
    """Abstraction of the SonarQube "platform" concept"""

    def __init__(self, url: str, token: str, org: str = None, cert_file: Optional[str] = None, http_timeout: int = 10, **kwargs) -> None:
        """Creates a SonarQube platform object

        :param url: base URL of the SonarQube platform
        :param token: token to connect to the platform
        :param cert_file: Client certificate, if any needed, defaults to None
        :return: the SonarQube object
        :rtype: Platform
        """
        self.url = url.rstrip("/").lower()  #: SonarQube URL
        self.__token = token
        self.__cert_file = cert_file
        self.__user_data = None
        self._version = None
        self._sys_info = None
        self.__global_nav = None
        self._server_id = None
        self._permissions = None
        self.http_timeout = int(http_timeout)
        self.organization = org
        self._user_agent = _SONAR_TOOLS_AGENT
        self._global_settings_definitions = None

    def __str__(self) -> str:
        """
        Returns the string representation of the SonarQube connection, with the token recognizable but largely redacted
        """
        return f"{util.redacted_token(self.__token)}@{self.url}"

    def __credentials(self) -> tuple[str, str]:
        return self.__token, ""

    def verify_connection(self) -> None:
        try:
            log.info("Connecting to %s", self.url)
            self.get("server/version")
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, "verifying connection", catch_all=True)
            raise exceptions.ConnectionError(util.sonar_error(e.response))

    def version(self) -> tuple[int, int, int]:
        """
        Returns the SonarQube platform version or 0.0.0 for SonarCloud
        """
        if self.is_sonarcloud():
            return 0, 0, 0
        if self._version is None:
            self._version = tuple(int(n) for n in self.get("/api/server/version").text.split("."))
            log.debug("Version = %s", str(self._version))
        return self._version[0:3]

    def edition(self) -> str:
        """
        Returns the Sonar edition: "community", "developer", "enterprise", "datacenter" or "sonarcloud"
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

    def user_data(self) -> types.ApiPayload:
        """Returns the user data corresponding to the provided token"""
        if self.__user_data is None:
            self.__user_data = json.loads(self.get("api/users/current").text)
        return self.__user_data

    def set_user_agent(self, user_agent: str) -> None:
        self._user_agent = user_agent

    def server_id(self) -> str:
        """
        Returns the SonarQube instance server id
        """
        if self._server_id is not None:
            return self._server_id
        if self._sys_info is not None and _SERVER_ID_KEY in self._sys_info["System"]:
            self._server_id = self._sys_info["System"][_SERVER_ID_KEY]
        else:
            self._server_id = json.loads(self.get("system/status").text)["id"]
        return self._server_id

    def is_sonarcloud(self) -> bool:
        """
        Returns whether the target platform is SonarCloud
        """
        return util.is_sonarcloud_url(self.url)

    def basics(self) -> dict[str, str]:
        """
        :return: the 3 basic information of the platform: ServerId, Edition and Version
        :rtype: dict{"serverId": <id>, "edition": <edition>, "version": <version>}
        """

        url = self.get_setting(key="sonar.core.serverBaseURL")
        if url in (None, ""):
            url = self.url
        data = {"edition": self.edition(), "url": url}
        if self.is_sonarcloud():
            return {**data, "organization": self.organization}

        return {**data, "version": util.version_to_string(self.version()[:3]), "serverId": self.server_id(), "plugins": self.plugins()}

    def get(self, api: str, params: types.ApiParams = None, **kwargs) -> requests.Response:
        """Makes an HTTP GET request to SonarQube

        :param api: API to invoke (without the platform base URL)
        :param params: params to pass in the HTTP request, defaults to None
        :return: the HTTP response
        """
        return self.__run_request(requests.get, api, params, **kwargs)

    def post(self, api: str, params: types.ApiParams = None, **kwargs) -> requests.Response:
        """Makes an HTTP POST request to SonarQube

        :param api: API to invoke (without the platform base URL)
        :param params: params to pass in the HTTP request, defaults to None
        :return: the HTTP response
        """
        if util.is_api_v2(api):
            if "headers" in kwargs:
                kwargs["headers"]["content-type"] = _APP_JSON
            else:
                kwargs["headers"] = {"content-type": _APP_JSON}
            return self.__run_request(requests.post, api, data=json.dumps(params), **kwargs)
        else:
            return self.__run_request(requests.post, api, params, **kwargs)

    def patch(self, api: str, params: types.ApiParams = None, **kwargs) -> requests.Response:
        """Makes an HTTP PATCH request to SonarQube

        :param api: API to invoke (without the platform base URL)
        :param params: params to pass in the HTTP request, defaults to None
        :return: the HTTP response
        """
        if util.is_api_v2(api):
            if "headers" in kwargs:
                kwargs["headers"]["content-type"] = "application/merge-patch+json"
            else:
                kwargs["headers"] = {"content-type": "application/merge-patch+json"}
            return self.__run_request(requests.patch, api=api, data=json.dumps(params), **kwargs)
        else:
            return self.__run_request(requests.patch, api, params, **kwargs)

    def delete(self, api: str, params: types.ApiParams = None, **kwargs) -> requests.Response:
        """Makes an HTTP DELETE request to SonarQube

        :param api: API to invoke (without the platform base URL)
        :param params: params to pass in the HTTP request, defaults to None
        :return: the HTTP response
        """
        return self.__run_request(requests.delete, api, params, **kwargs)

    def __run_request(self, request: callable, api: str, params: types.ApiParams = None, **kwargs) -> requests.Response:
        """Makes an HTTP request to SonarQube"""
        mute = kwargs.pop("mute", ())
        api = _normalize_api(api)
        headers = {"user-agent": self._user_agent, "accept": _APP_JSON}
        headers.update(kwargs.get("headers", {}))
        if params is None:
            params = {}
        with_org = kwargs.pop("with_organization", True)
        if self.is_sonarcloud():
            headers["Authorization"] = f"Bearer {self.__token}"
            if with_org:
                params["organization"] = self.organization
        req_type, url = "", ""
        if log.get_level() <= log.DEBUG:
            req_type = getattr(request, "__name__", repr(request)).upper()
            url = self.__urlstring(api, params, kwargs.get("data", {}))
            log.debug("%s: %s", req_type, url)
        kwargs["headers"] = headers
        try:
            retry = True
            while retry:
                start = time.perf_counter_ns()
                r = request(
                    url=self.url + api,
                    auth=self.__credentials(),
                    verify=self.__cert_file,
                    params=params,
                    timeout=self.http_timeout,
                    **kwargs,
                )
                (retry, new_url) = _check_for_retry(r)
                log.debug("%s: %s took %d ms", req_type, url, (time.perf_counter_ns() - start) // 1000000)
                if retry:
                    self.url = new_url
            r.raise_for_status()
        except HTTPError as e:
            lvl = log.DEBUG if r.status_code in mute else log.ERROR
            log.log(lvl, "%s (%s request)", util.error_msg(e), req_type)
            raise e
        except (ConnectionError, RequestException) as e:
            util.handle_error(e, "")
        return r

    def get_paginated(self, api: str, return_field: str, params: types.ApiParams = None) -> types.ObjectJsonRepr:
        """Returns all pages of a paginated API"""
        new_params = {} if params is None else params.copy()
        new_params["ps"] = 500
        new_params["p"] = 1
        data = json.loads(self.get(api, params=new_params).text)
        nb_pages = util.nbr_pages(data, api_version=1)
        if nb_pages == 1:
            return data
        for page in range(2, nb_pages + 1):
            new_params["p"] = page
            data[return_field].update(json.loads(self.get(api, params=new_params).text)[return_field])
        return data

    def global_permissions(self) -> dict[str, any]:
        """Returns the SonarQube platform global permissions

        :return: dict{"users": {<login>: <permissions comma separated>, ...}, "groups"; {<name>: <permissions comma separated>, ...}}}
        :rtype: dict
        """
        if self._permissions is None:
            self._permissions = global_permissions.GlobalPermissions(self)
        return self._permissions

    def global_settings_definitions(self) -> list[dict[str, str]]:
        """Returns the platform global settings definitions"""
        if not self._global_settings_definitions:
            try:
                self._global_settings_definitions = json.loads(self.get("settings/list_definitions").text)["definitions"]
            except (ConnectionError, RequestException):
                return []
        return self._global_settings_definitions

    def sys_info(self) -> dict[str, any]:
        """
        :return: the SonarQube platform system info file
        """
        if self.is_sonarcloud():
            return {"System": {_SERVER_ID_KEY: "sonarcloud"}}
        if self._sys_info is None:
            success, counter = False, 0
            while not success:
                try:
                    resp = self.get("system/info", mute=(HTTPStatus.INTERNAL_SERVER_ERROR,))
                    success = True
                except (ConnectionError, RequestException) as e:
                    # Hack: SonarQube randomly returns Error 500 on this API, retry up to 10 times
                    if isinstance(e, HTTPError) and e.response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR and counter < 10:
                        log.error("HTTP Error 500 for api/system/info, retrying...")
                        time.sleep(0.5)
                        counter += 1
                    else:
                        log.error("%s while getting system info", util.error_msg(e))
                        raise e
            self._sys_info = json.loads(resp.text)
            success = True
        return self._sys_info

    def global_nav(self) -> dict[str, any]:
        """
        :return: the SonarQube platform global navigation data
        """
        if self.__global_nav is None:
            resp = self.get("navigation/global", mute=(HTTPStatus.INTERNAL_SERVER_ERROR,))
            self.__global_nav = json.loads(resp.text)
        return self.__global_nav

    def database(self) -> str:
        """
        :return: the SonarQube platform backend database
        """
        if self.is_sonarcloud():
            return "postgresql"
        if self.version() < (9, 7, 0):
            return self.sys_info()["Statistics"]["database"]["name"]
        return self.sys_info()["Database"]["Database"]

    def plugins(self) -> dict[str, str]:
        """
        :return: the SonarQube platform plugins
        """
        if self.is_sonarcloud():
            return {}
        sysinfo = self.sys_info()
        if "Application Nodes" in sysinfo:
            sysinfo = sysinfo["Application Nodes"][0]
        if self.version() < (9, 7, 0):
            return sysinfo["Statistics"]["plugins"]
        return sysinfo["Plugins"]

    def get_settings(self, settings_list: list[str] = None) -> dict[str, any]:
        """Returns a list of (or all) platform global settings value from their key
        :return: the list of settings values
        :rtype: dict{<key>: <value>, ...}
        """
        params = util.remove_nones({"keys": util.list_to_csv(settings_list)})
        resp = self.get(settings.Setting.API[c.GET], params=params)
        json_s = json.loads(resp.text)
        platform_settings = {}
        for s in json_s["settings"]:
            for setting_key in "value", "values", "fieldValues":
                if setting_key in s:
                    platform_settings[s["key"]] = s[setting_key]
        return platform_settings

    def __settings(self, settings_list: types.KeyList = None, include_not_set: bool = False) -> dict[str, settings.Setting]:
        log.info("getting global settings")
        settings_dict = settings.get_bulk(endpoint=self, settings_list=settings_list, include_not_set=include_not_set)
        ai_code_fix = settings.Setting.read(endpoint=self, key=settings.AI_CODE_FIX)
        if ai_code_fix:
            settings_dict[ai_code_fix.key] = ai_code_fix
        return settings_dict

    def get_setting(self, key: str) -> any:
        """Returns a platform global setting value from its key

        :param key: Setting key
        :return: the setting value
        """
        return self.get_settings(key).get(key, None)

    def reset_setting(self, key: str) -> bool:
        """Resets a platform global setting to the SonarQube internal default value

        :param key: Setting key
        :return: Whether the reset was successful or not
        """
        return settings.reset_setting(self, key)

    def set_setting(self, key: str, value: any) -> bool:
        """Sets a platform global setting

        :param key: Setting key
        :param value: Setting value
        :return: Whether setting the value was successful or not
        """
        return settings.set_setting(self, key, value)

    def __urlstring(self, api: str, params: types.ApiParams, data: str = None) -> str:
        """Returns a string corresponding to the URL and parameters"""
        url = f"{str(self)}{api}"
        if params is not None:
            good_params = {k: v for k, v in params.items() if v is not None}
            for k, v in good_params.items():
                if isinstance(v, datetime.date):
                    good_params[k] = util.format_date(v)
                elif isinstance(v, (list, tuple, set)):
                    good_params[k] = ",".join([str(x) for x in v])
            params_string = "&".join([f"{k}={requests.utils.quote(str(v))}" for k, v in good_params.items()])
            if len(params_string) > 0:
                url += f"?{params_string}"
        if data is not None and len(data) > 0:
            url += f" - BODY: {data}"
        return url

    def webhooks(self) -> dict[str, object]:
        """
        :return: the list of global webhooks
        :rtype: dict{<webhook_name>: <webhook_data>, ...}
        """
        from sonar import webhooks

        return webhooks.get_list(self)

    def export(self, export_settings: types.ConfigSettings, full: bool = False) -> types.ObjectJsonRepr:
        """Exports the global platform properties as JSON

        :param full: Whether to also export properties that cannot be set, defaults to False
        :type full: bool, optional
        :return: dict of all properties with their values
        :rtype: dict
        """
        log.info("Exporting platform global settings")
        json_data = {}
        for s in self.__settings(include_not_set=export_settings.get("EXPORT_DEFAULTS", False)).values():
            if s.is_internal():
                continue
            (categ, subcateg) = s.category()
            if self.is_sonarcloud() and categ == settings.THIRD_PARTY_SETTINGS:
                # What is reported as 3rd part are SonarCloud internal settings
                continue
            if not s.is_global():
                continue
            util.update_json(json_data, categ, subcateg, s.to_json(export_settings.get("INLINE_LISTS", True)))

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

    def set_webhooks(self, webhooks_data: types.ObjectJsonRepr) -> None:
        """Sets global webhooks with a list of webhooks represented as JSON

        :param webhooks_data: the webhooks JSON representation
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

    def import_config(self, config_data: types.ObjectJsonRepr) -> None:
        """Imports a whole SonarQube platform global configuration represented as JSON

        :param config_data: the sonar-config configuration representation of the platform
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
            try:
                settings.set_new_code_period(self, nc_type, nc_val)
            except exceptions.UnsupportedOperation as e:
                log.error(e.message)
        permission_templates.import_config(self, config_data)
        global_permissions.import_config(self, config_data)
        try:
            devops.import_config(self, config_data)
        except exceptions.UnsupportedOperation as e:
            log.warning(e.message)

    def audit(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits a global platform configuration and returns the list of problems found

        :param audit_settings: Audit options and thresholds to raise problems
        :return: List of problems found, or empty list
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
            self._audit_project_default_visibility(audit_settings)
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
        )
        return problems

    def _audit_logs(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        if not audit_settings.get("audit.logs", True):
            log.info("Logs audit is disabled, skipping logs audit...")
            return []
        if self.is_sonarcloud():
            log.info("Logs audit not available with SonarQube Cloud, skipping logs audit...")
            return []
        log_map = {"app": "sonar.log", "ce": "ce.log", "web": "web.log", "es": "es.log"}
        if self.edition() == "datacenter":
            log_map.pop("es")
        problems = []
        for logtype, logfile in log_map.items():
            try:
                logs = self.get("system/logs", params={"name": logtype}).text
            except (ConnectionError, RequestException) as e:
                util.handle_error(e, f"retrieving {logtype} logs", catch_all=True)
                continue
            i = 0
            for line in logs.splitlines():
                if i % 1000 == 0:
                    log.debug("Inspecting log line (%d) %s", i, line)
                i += 1
                try:
                    (_, level, _) = line.split(" ", maxsplit=2)
                except ValueError:
                    # Not the standard log line, must be a stacktrace or something, just skip
                    continue
                rule = None
                if level == "ERROR":
                    log.warning("Error found in %s: %s", logfile, line)
                    rule = get_rule(RuleId.ERROR_IN_LOGS)
                elif level == "WARN":
                    log.warning("Warning found in %s: %s", logfile, line)
                    rule = get_rule(RuleId.WARNING_IN_LOGS)
                if rule is not None:
                    problems.append(Problem(rule, f"{self.url}/admin/system", logfile, line))
        logs = self.get("system/logs", params={"name": "deprecation"}).text
        nb_deprecation = len(logs.splitlines())
        if nb_deprecation > 0:
            rule = get_rule(RuleId.DEPRECATION_WARNINGS)
            problems.append(Problem(rule, f"{self.url}/admin/system", nb_deprecation))
        return problems

    def _audit_project_default_visibility(self, audit_settings: types.ConfigSettings) -> list[Problem]:
        """Audits whether project default visibility is public"""
        log.info("Auditing project default visibility")
        problems = []
        if self.version() < (8, 7, 0):
            resp = self.get(
                "navigation/organization",
                params={"organization": "default-organization"},
            )
            visi = json.loads(resp.text)["organization"]["projectVisibility"]
        else:
            resp = self.get(settings.Setting.API[c.GET], params={"keys": "projects.default.visibility"})
            visi = json.loads(resp.text)["settings"][0]["value"]
        log.info("Project default visibility is '%s'", visi)
        if audit_settings.get("audit.globalSettings.defaultProjectVisibility", "private") != visi:
            rule = get_rule(RuleId.SETTING_PROJ_DEFAULT_VISIBILITY)
            problems.append(Problem(rule, f"{self.url}/admin/projects_management", visi))
        return problems

    def _audit_admin_password(self) -> list[Problem]:
        log.info("Auditing admin password")
        problems = []
        try:
            r = requests.get(url=self.url + "/api/authentication/validate", auth=("admin", "admin"), timeout=self.http_timeout)
            data = json.loads(r.text)
            if data.get("valid", False):
                problems.append(Problem(get_rule(RuleId.DEFAULT_ADMIN_PASSWORD), self.url))
            else:
                log.info("User 'admin' default password has been changed")
        except requests.RequestException as e:
            util.exit_fatal(str(e), errcodes.SONAR_API)
        return problems

    def __audit_group_permissions(self) -> list[Problem]:
        log.info("Auditing group global permissions")
        problems = []
        perms_url = f"{self.url}/admin/permissions"
        groups = self.global_permissions().groups()
        if len(groups) > 10:
            problems.append(Problem(get_rule(rule_id=RuleId.RISKY_GLOBAL_PERMISSIONS), perms_url, len(groups)))

        for gr_name, gr_perms in groups.items():
            if gr_name == "Anyone":
                problems.append(Problem(get_rule(RuleId.ANYONE_WITH_GLOBAL_PERMS), perms_url))
            if gr_name == "sonar-users" and (
                "admin" in gr_perms or "gateadmin" in gr_perms or "profileadmin" in gr_perms or "provisioning" in gr_perms
            ):
                problems.append(Problem(get_rule(RuleId.SONAR_USERS_WITH_ELEVATED_PERMS), perms_url))

        maxis = {"admin": 2, "gateadmin": 2, "profileadmin": 2, "scan": 2, "provisioning": 3}
        for key, name in permissions.ENTERPRISE_GLOBAL_PERMISSIONS.items():
            counter = self.global_permissions().count(perm_type="groups", perm_filter=(key,))
            if key in maxis and counter > maxis[key]:
                msg = f"Too many ({counter}) groups with permission '{name}', {maxis[key]} max recommended"
                problems.append(Problem(get_rule(rule_id=RuleId.RISKY_GLOBAL_PERMISSIONS), perms_url, msg))
        return problems

    def __audit_user_permissions(self) -> list[Problem]:
        log.info("Auditing users global permissions")
        problems = []
        perms_url = f"{self.url}/admin/permissions"
        users = self.global_permissions().users()
        if len(users) > 10:
            msg = f"Too many ({len(users)}) users with direct global permissions, use groups instead"
            problems.append(Problem(get_rule(rule_id=RuleId.RISKY_GLOBAL_PERMISSIONS), perms_url, msg))

        maxis = {"admin": 3, "gateadmin": 3, "profileadmin": 3, "scan": 3, "provisioning": 3}
        for key, name in permissions.ENTERPRISE_GLOBAL_PERMISSIONS.items():
            counter = self.global_permissions().count(perm_type="users", perm_filter=(key,))
            if key in maxis and counter > maxis[key]:
                msg = f"Too many ({counter}) users with permission '{name}', use groups instead"
                problems.append(Problem(get_rule(rule_id=RuleId.RISKY_GLOBAL_PERMISSIONS), perms_url, msg))
        return problems

    def _audit_global_permissions(self) -> list[Problem]:
        log.info("--- Auditing global permissions ---")
        return self.__audit_user_permissions() + self.__audit_group_permissions()

    def _audit_lta_latest(self) -> list[Problem]:
        if self.is_sonarcloud():
            return []
        sq_vers, v = self.version(), None
        if sq_vers < lta()[:2]:
            rule = get_rule(RuleId.BELOW_LTA)
            v = lta()
        elif sq_vers < lta():
            rule = get_rule(RuleId.LTA_PATCH_MISSING)
            v = lta()
        elif sq_vers[:2] > lta()[:2] and sq_vers < latest()[:2]:
            rule = get_rule(RuleId.BELOW_LATEST)
            v = latest()
        if not v:
            return []
        # pylint: disable-next=E0606
        return [Problem(rule, self.url, ".".join([str(n) for n in sq_vers]), ".".join([str(n) for n in v]))]

    def is_mqr_mode(self) -> bool:
        """Returns whether the platform is in MQR mode"""
        if self.version() >= (10, 8, 0):
            return self.get_setting(settings.MQR_ENABLED)
        return self.version() >= (10, 2, 0)


# --------------------- Static methods -----------------
# this is a pointer to the module object instance itself.
this = sys.modules[__name__]
this.context = Platform(os.getenv("SONAR_HOST_URL", "http://localhost:9000"), os.getenv("SONAR_TOKEN", ""))


def _normalize_api(api: str) -> str:
    """Normalizes an API based on its multiple original forms"""
    if api.startswith("/api/"):
        pass
    elif api.startswith("api/"):
        api = "/" + api
    elif api.startswith("/"):
        api = "/api" + api
    else:
        api = "/api/" + api
    return api


def _audit_setting_value(key: str, platform_settings: dict[str, any], audit_settings: types.ConfigSettings, url: str) -> list[Problem]:
    """Audits a particular platform setting is set to expected value"""
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
    msg = f"Setting {v[0]} has potentially incorrect or unsafe value '{s}'"
    return [Problem(get_rule(RuleId.DUBIOUS_GLOBAL_SETTING), url, msg)]


def _audit_setting_in_range(
    key: str, platform_settings: dict[str, any], audit_settings: types.ConfigSettings, sq_version: tuple[int, int, int], url: str
) -> list[Problem]:
    """Audits a particular platform setting is within expected range of values"""
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
    log.info("Auditing that setting %s is within recommended range [%.2f-%.2f]", v[0], min_v, max_v)
    if min_v <= value <= max_v:
        return []
    msg = f"Setting '{v[0]}' value {platform_settings[v[0]]} is outside recommended range [{v[1]}-{v[2]}]"
    return [Problem(get_rule(RuleId.DUBIOUS_GLOBAL_SETTING), url, msg)]


def _audit_setting_set(
    key: str, check_is_set: bool, platform_settings: dict[str, any], audit_settings: types.ConfigSettings, url: str
) -> list[Problem]:
    """Audits that a setting is set or not set"""
    v = _get_multiple_values(3, audit_settings[key], "MEDIUM", "CONFIGURATION")
    if v is None:
        log.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    log.info("Auditing whether setting %s is set or not", v[0])
    if platform_settings.get(v[0], "") == "":  # Setting is not set
        if check_is_set:
            return [Problem(get_rule(RuleId.SETTING_NOT_SET), url, v[0])]
        log.info("Setting %s is not set", v[0])
    else:
        if not check_is_set:
            return [Problem(get_rule(RuleId.SETTING_SET), url)]
        log.info("Setting %s is set with value %s", v[0], platform_settings[v[0]])
    return []


def _audit_maintainability_rating_range(value: float, range: tuple[float, float], rating_letter: str, url: str) -> list[Problem]:
    """Audits a maintainability rating grid level range"""
    log.debug(
        "Checking that maintainability rating threshold %.1f%% for '%s' is within recommended range [%.1f%%-%.1f%%]",
        value * 100,
        rating_letter,
        range[0] * 100,
        range[1] * 100,
    )
    if range[0] <= value <= range[1]:
        return []
    rule = get_rule(RuleId.SETTING_MAINT_GRID)
    msg = rule.msg.format(f"{value * 100:.1f}", rating_letter, f"{range[0] * 100:.1f}", f"{range[1] * 100:.1f}")
    return [Problem(get_rule(RuleId.SETTING_MAINT_GRID), url, msg)]


def _audit_maintainability_rating_grid(platform_settings: dict[str, any], audit_settings: types.ConfigSettings, url: str) -> list[Problem]:
    """Audits the maintainability rating grid setting, verifying ranges are meaningful"""
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


def _get_multiple_values(n: int, setting: str, severity: sev.Severity, domain: typ.Type) -> Optional[list[str]]:
    """Returns the multiple elements that define a setting rule from sonar-audit config properties"""
    values = util.csv_to_list(setting)
    if len(values) < (n - 2):
        return None
    if len(values) == (n - 2):
        values.append(severity)
    if len(values) == (n - 1):
        values.append(domain)
    values[n - 2] = sev.to_severity(values[n - 2])
    values[n - 1] = typ.to_type(values[n - 1])
    # TODO(okorach) Handle case of too many values
    return values


def __lta_and_latest() -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Returns the current version of LTA and LATEST, if possible querying the update center,
    using hardcoded values as fallback"""
    global LTA
    global LATEST
    if LTA is None:
        log.debug("Attempting to reach Sonar update center")
        _, tmpfile = tempfile.mkstemp(prefix="sonar-tools", suffix=".txt", text=True)
        try:
            with open(tmpfile, "w", encoding="utf-8") as fp:
                print(requests.get(_UPDATE_CENTER, headers={"user-agent": _SONAR_TOOLS_AGENT}, timeout=10).text, file=fp)
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
            log.info("Sonar update center says LTA (ex-LTS) = %s, LATEST = %s", str(LTA), str(LATEST))
        except (EnvironmentError, HTTPError):
            LTA = _HARDCODED_LTA
            LATEST = _HARDCODED_LATEST
            log.info("Sonar update center read failed, hardcoding LTA (ex-LTS) = %s, LATEST = %s", str(LTA), str(LATEST))
        try:
            os.remove(tmpfile)
        except EnvironmentError:
            pass
    return LTA, LATEST


def lta() -> tuple[int, int, int]:
    """
    :return: the current SonarQube LTA (ex-LTS) version
    """
    return __lta_and_latest()[0]


def latest() -> tuple[int, int, int]:
    """
    :return: the current SonarQube LATEST version
    """
    return __lta_and_latest()[1]


def import_config(endpoint: Platform, config_data: types.ObjectJsonRepr, key_list: types.KeyList = None) -> None:
    """Imports a configuration in SonarQube

    :param Platform endpoint: reference to the SonarQube platform
    :param ObjectJsonRepr config_data: the configuration to import
    :param KeyList key_list: Unused
    :return: Nothing
    """
    endpoint.import_config(config_data)


def _check_for_retry(response: requests.models.Response) -> tuple[bool, str]:
    """Verifies if a response had a 301 Moved permanently and if so provide the new location"""
    if len(response.history) > 0 and response.history[0].status_code == HTTPStatus.MOVED_PERMANENTLY:
        new_url = "/".join(response.history[0].headers["Location"].split("/")[0:3])
        log.debug("Moved permanently to URL %s", new_url)
        return True, new_url
    return False, None


def convert_for_yaml(original_json: types.ObjectJsonRepr) -> types.ObjectJsonRepr:
    """Convert the original JSON defined for JSON export into a JSON format more adapted for YAML export"""
    original_json = util.remove_nones(original_json)
    if "languages" in original_json:
        original_json["languages"] = util.dict_to_list(original_json["languages"], "language")
    if "permissions" in original_json:
        original_json["permissions"] = permissions.convert_for_yaml(original_json["permissions"])
    if "permissionTemplates" in original_json:
        for tpl in original_json["permissionTemplates"].values():
            if "permissions" in tpl:
                tpl["permissions"] = permissions.convert_for_yaml(tpl["permissions"])
        original_json["permissionTemplates"] = util.dict_to_list(original_json["permissionTemplates"], "name")
    if "devopsIntegration" in original_json:
        original_json["devopsIntegration"] = util.dict_to_list(original_json["devopsIntegration"], "name")
    return original_json


def export(endpoint: Platform, export_settings: types.ConfigSettings, **kwargs) -> types.ObjectJsonRepr:
    """Exports all or a list of projects configuration as dict

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings export_settings: Export parameters
    :return: Platform settings
    :rtype: ObjectJsonRepr
    """
    exp = endpoint.export(export_settings)
    write_q = kwargs.get("write_q", None)
    if write_q:
        write_q.put(exp)
        write_q.put(util.WRITE_END)
    return exp


def basics(endpoint: Platform, **kwargs) -> types.ObjectJsonRepr:
    """Returns an endpooint basic info (license, edition, version etc..)"""
    exp = endpoint.basics()
    write_q = kwargs.get("write_q", None)
    if write_q:
        write_q.put(exp)
        write_q.put(util.WRITE_END)
    return exp


def audit(endpoint: Platform, audit_settings: types.ConfigSettings, **kwargs) -> list[Problem]:
    """Audits a platform"""
    if not audit_settings.get("audit.globalSettings", True):
        log.info("Auditing global settings is disabled, audit skipped...")
        return []
    pbs = endpoint.audit(audit_settings)
    if "write_q" in kwargs:
        kwargs["write_q"].put(pbs)
    return pbs
