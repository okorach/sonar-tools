#
# sonar-tools
# Copyright (C) 2019-2026 Olivier Korach
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
"""Abstraction of the SonarQube platform or instance concept"""

from __future__ import annotations
from typing import Any, Union, Optional, Callable, TYPE_CHECKING

from http import HTTPStatus
import sys
import os
import re
import time
import datetime
import json
import requests
from requests import HTTPError, RequestException

import sonar.logging as log
import sonar.util.misc as util
import sonar.utilities as sutil
from sonar.util import update_center
import sonar.util.constants as c
import sonar.util.platform_helper as pfhelp

from sonar import errcodes, settings, devops, version, sif, exceptions, organizations
from sonar.permissions import permissions, global_permissions, permission_templates
from sonar.audit.rules import get_rule, RuleId
import sonar.audit.severities as sev
import sonar.audit.types as typ
from sonar.audit.problem import Problem
from sonar import webhooks
from sonar.api.manager import ApiOperation as Oper
from sonar.api.manager import ApiManager as Api

if TYPE_CHECKING:
    from sonar.util.types import ApiParams, ApiPayload, ConfigSettings, KeyList, ObjectJsonRepr

WRONG_CONFIG_MSG = "Audit config property %s has wrong value %s, skipping audit"

_NON_EXISTING_SETTING_SKIPPED = "Setting %s does not exist, skipping..."

_SONAR_TOOLS_AGENT = f"sonar-tools {version.PACKAGE_VERSION}"

_APP_JSON = "application/json"

_SERVER_ID_KEY = "Server ID"


class Platform(object):
    """Abstraction of the SonarQube "platform" concept"""

    def __init__(
        self, url: str, token: str, org: Optional[str] = None, cert_file: Optional[str] = None, http_timeout: int = 10, **kwargs: str
    ) -> None:
        """Creates a SonarQube platform object

        :param str url: base URL of the SonarQube platform
        :param str token: token to connect to the platform
        :param str cert_file: Client certificate, if any needed, defaults to None
        :return: the SonarQube object
        :rtype: Platform
        """
        self.local_url = url.rstrip("/").lower()  #: SonarQube URL
        self.external_url = self.local_url
        self.__token = token
        self.__cert_file = cert_file
        self.__user_data: ApiPayload = None
        self._version: Optional[tuple[int, ...]] = None
        self._sys_info: Optional[dict[str, Any]] = None
        self.__global_nav: ApiPayload = None
        self._server_id: Optional[str] = None
        self._permissions: Optional[object] = None
        self.http_timeout = int(http_timeout)
        self.organization: str = org or ""
        self._user_agent = _SONAR_TOOLS_AGENT
        self._global_settings_definitions: dict[str, dict[str, str]] = None
        self.api: Api = Api(self)

    def __str__(self) -> str:
        """
        Returns the string representation of the SonarQube connection,
        with the token recognizable but largely redacted
        """
        return f"{sutil.redacted_token(self.__token)}@{self.local_url}"

    def __credentials(self) -> tuple[str, str]:
        return self.__token, ""

    def verify_connection(self) -> None:
        """Verifies the connection to the SonarQube platform

        :raises: ConnectionError if the connection cannot be established"""
        try:
            log.info("Connecting to %s", self.local_url)
            self.get("server/version")
            if self.is_sonarcloud():
                if not organizations.Organization.exists(self, key=self.organization):
                    raise exceptions.ObjectNotFound(
                        self.organization, f"Organization '{self.organization}' does not exist or user is not member of it"
                    )
            else:
                s = self.get_setting(key="sonar.core.serverBaseURL")
                if s not in (None, ""):
                    self.external_url = s
        except (ConnectionError, RequestException) as e:
            sutil.handle_error(e, "verifying connection", catch_all=True)
            raise exceptions.ConnectionError(f"{str(e)} while connecting to {self.local_url}")

    def url(self) -> str:
        """Returns the SonarQube URL"""
        return self.external_url

    def version(self) -> tuple[int, int, int]:
        """Returns the SonarQube platform version or None for SonarQube Cloud"""
        if self.is_sonarcloud():
            return None
        if self._version is None:
            self._version = tuple(int(n) for n in self.get("/api/server/version").text.split("."))
            log.debug("Version = %s", str(self._version))
        return self._version[0:3]

    def release_date(self) -> Optional[datetime.date]:
        """Returns the SonarQube Server platform release date if found in update center or None if SonarQube Cloud or if the date cannot be found"""
        if self.is_sonarcloud():
            return None
        return update_center.get_release_date(self.version())

    def edition(self) -> str:
        """Returns the SonarQube edition: 'community', 'developer', 'enterprise', 'datacenter' or 'sonarcloud'"""
        if self.is_sonarcloud():
            return c.SC
        return sutil.edition_normalize(self.global_nav().get("edition") or self.sys_info()["Statistics"]["edition"])

    def user(self) -> str:
        """Returns the user corresponding to the provided token"""
        return self.user_data()["login"]

    def user_data(self) -> ApiPayload:
        """Returns the user data corresponding to the provided token"""
        self.__user_data = self.__user_data or json.loads(self.get("api/users/current").text)
        return self.__user_data

    def set_user_agent(self, user_agent: str) -> None:
        """Sets the user agent for HTTP requests"""
        self._user_agent = user_agent

    def server_id(self) -> str:
        """Returns the SonarQube instance server id"""
        if self._server_id is not None:
            return self._server_id
        if self._sys_info is not None and _SERVER_ID_KEY in self._sys_info["System"]:
            self._server_id = self._sys_info["System"][_SERVER_ID_KEY]
        else:
            self._server_id = json.loads(self.get("system/status").text)["id"]
        return self._server_id

    def is_sonarcloud(self) -> bool:
        """Returns whether the target platform is SonarQube Cloud"""
        return sutil.is_sonarcloud_url(self.local_url)

    def basics(self) -> dict[str, Any]:
        """Returns the platform basic info as JSON

        :return: the basic information of the platform: ServerId, Edition, Version and Plugins
        :rtype: dict{"serverId": <id>, "edition": <edition>, "version": <version>, "plugins": <dict>}
        """
        if (url := self.get_setting(key="sonar.core.serverBaseURL")) in (None, ""):
            url = self.local_url
        data = {"edition": self.edition(), "url": url}
        if self.is_sonarcloud():
            return {**data, "organization": self.organization}

        return {
            **data,
            "version": sutil.version_to_string(self.version()[:3]),
            "edition": self.edition(),
            "serverId": self.server_id(),
            "plugins": util.dict_to_list(self.plugins(), "key"),
        }

    def default_user_group(self) -> str:
        """Returns the built-in default group name on that platform"""
        return c.SQC_USERS if self.is_sonarcloud() else c.SQS_USERS

    def is_default_user_group(self, group_name: str) -> bool:
        """Returns whether a group name is the default user group (sonar-user on SQS Members on SQC)

        :param str group_name: group name to check
        :return: whether the group is a built-in default group
        """
        return group_name == self.default_user_group()

    def get(self, api: str, params: Optional[ApiParams] = None, **kwargs) -> requests.Response:
        """Makes an HTTP GET request to SonarQube

        :param api: API to invoke (without the platform base URL)
        :param params: params to pass in the HTTP request, defaults to None
        :return: the HTTP response
        """
        return self.__run_request(requests.get, api, params, **kwargs)

    def post(self, api: str, params: Optional[ApiParams] = None, **kwargs) -> requests.Response:
        """Makes an HTTP POST request to SonarQube

        :param api: API to invoke (without the platform base URL)
        :param params: params to pass in the HTTP request, defaults to None
        :return: the HTTP response
        """
        if sutil.is_api_v2(api):
            kwargs["headers"] = kwargs.get("headers", {}) | {"content-type": _APP_JSON}
            return self.__run_request(requests.post, api, data=json.dumps(params), **kwargs)
        else:
            return self.__run_request(requests.post, api, params, **kwargs)

    def patch(self, api: str, params: Optional[ApiParams] = None, **kwargs) -> requests.Response:
        """Makes an HTTP PATCH request to SonarQube

        :param api: API to invoke (without the platform base URL)
        :param params: params to pass in the HTTP request, defaults to None
        :return: the HTTP response
        """
        kwargs["headers"] = kwargs.get("headers", {}) | {"content-type": "application/merge-patch+json"}
        return self.__run_request(requests.patch, api=api, data=json.dumps(params), **kwargs)

    def delete(self, api: str, params: Optional[ApiParams] = None, **kwargs) -> requests.Response:
        """Makes an HTTP DELETE request to SonarQube

        :param api: API to invoke (without the platform base URL)
        :param params: params to pass in the HTTP request, defaults to None
        :return: the HTTP response
        """
        return self.__run_request(requests.delete, api, params, **kwargs)

    def __run_request(self, request: Callable, api: str, params: Optional[Union[ApiParams, str]] = None, **kwargs) -> requests.Response:
        """Makes an HTTP request to SonarQube"""
        mute = kwargs.pop("mute", ())
        api = pfhelp.normalize_api(api)
        headers = {"user-agent": self._user_agent, "accept": _APP_JSON} | kwargs.get("headers", {})
        params = params or {}
        if isinstance(params, dict):
            params = {k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()}
        elif isinstance(params, (list, tuple)):
            params = [(v[0], str(v[1]).lower() if isinstance(v[1], bool) else v[1]) for v in params]
        with_org = kwargs.pop("with_organization", True)
        if self.is_sonarcloud():
            headers["Authorization"] = f"Bearer {self.__token}"
            if with_org:
                if isinstance(params, dict):
                    params["organization"] = self.organization
                elif isinstance(params, (list, tuple)):
                    params.append(("organization", self.organization))
                elif isinstance(params, str):
                    params += f"&organization={self.organization}"
        req_type, url = getattr(request, "__name__", repr(request)).upper(), ""
        if log.get_level() <= log.DEBUG:
            url = self.__urlstring(api, params, kwargs.get("data", {}))
            log.debug("%s: %s", req_type, url)
        kwargs["headers"] = headers
        try:
            retry = True
            while retry:
                start = time.perf_counter_ns()
                r = request(
                    url=self.local_url + api,
                    auth=self.__credentials(),
                    verify=self.__cert_file,
                    params=params,
                    timeout=self.http_timeout,
                    **kwargs,
                )
                (retry, new_url) = Platform.__check_for_retry(r)
                log.debug("%s: %s took %d ms", req_type, url, (time.perf_counter_ns() - start) // 1000000)
                if retry:
                    self.local_url = new_url
            r.raise_for_status()
        except HTTPError as e:
            code = r.status_code
            lvl = log.DEBUG if code in mute else log.ERROR
            log.log(lvl, "%s (%s request)", sutil.error_msg(e), req_type)
            if code == HTTPStatus.UNAUTHORIZED:
                raise exceptions.SonarException(sutil.error_msg(e), errcodes.SONAR_API_AUTHENTICATION) from e
            if code == HTTPStatus.FORBIDDEN:
                raise exceptions.NoPermissions(sutil.error_msg(e)) from e
            err_msg = sutil.sonar_error(e.response)
            err_msg_lower = err_msg.lower()
            key = next((params[k] for k in ("key", "project", "component", "componentKey") if k in params), "Unknown")
            if any(
                msg in err_msg_lower for msg in ("not found", "no quality gate has been found", "does not exist", "could not find")
            ):  # code == HTTPStatus.NOT_FOUND:
                raise exceptions.ObjectNotFound(key, err_msg) from e
            if any(msg in err_msg_lower for msg in ("already exists", "already been taken")):
                raise exceptions.ObjectAlreadyExists(key, err_msg) from e
            if re.match(r"(Value of parameter .+ must be one of|No enum constant)", err_msg):
                raise exceptions.UnsupportedOperation(err_msg) from e
            if re.match(r"Unknown url", err_msg):
                err_msg = err_msg.replace("Unknown url : /", "") + " API not available in this SonarQube version/edition"
                raise exceptions.UnsupportedOperation(err_msg) from e
            if any(msg in err_msg_lower for msg in ("insufficient privileges", "insufficient permissions")):
                raise exceptions.SonarException(err_msg, errcodes.SONAR_API_AUTHORIZATION) from e
            if "unknown url" in err_msg_lower:
                raise exceptions.UnsupportedOperation(err_msg) from e
            raise exceptions.SonarException(err_msg, errcodes.SONAR_API) from e
        except ConnectionError as e:
            sutil.handle_error(e, "")
        return r

    def get_paginated(self, api: str, return_field: str, **kwargs: str) -> ObjectJsonRepr:
        """Returns all pages of a paginated API"""
        params = {"ps": 500} | kwargs
        data = json.loads(self.get(api, params=params | {"p": 1}).text)
        if (nb_pages := sutil.nbr_pages(data)) == 1:
            return data
        for page in range(2, nb_pages + 1):
            data[return_field].update(json.loads(self.get(api, params=params | {"p": page}).text)[return_field])
        return data

    def global_permissions(self) -> global_permissions.GlobalPermissions:
        """Returns the SonarQube platform global permissions

        :return: dict{"users": {<login>: <permissions comma separated>, ...}, "groups"; {<name>: <permissions comma separated>, ...}}}
        """
        if self._permissions is None:
            self._permissions = global_permissions.GlobalPermissions(self)
        return self._permissions

    def global_settings_definitions(self) -> dict[str, dict[str, str]]:
        """Returns the platform global settings definitions"""
        if not self._global_settings_definitions:
            try:
                api, _, params, ret = self.api.get_details(settings.Setting, Oper.LIST_DEFINITIONS)
                data = json.loads(self.get(api, params=params).text)
                self._global_settings_definitions = {s["key"]: s for s in data[ret]}
            except (ConnectionError, RequestException):
                return {}
        return self._global_settings_definitions

    def sys_info(self) -> dict[str, Any]:
        """Returns the SonarQube platform system info JSON"""
        MAX_RETRIES = 10
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
                    if isinstance(e, HTTPError) and e.response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR and counter < MAX_RETRIES:
                        log.error("HTTP Error 500 for api/system/info, retrying...")
                        time.sleep(0.5)
                        counter += 1
                    else:
                        log.error("%s while getting system info", sutil.error_msg(e))
                        raise e
            self._sys_info = json.loads(resp.text)
            success = True
        return self._sys_info

    def global_nav(self) -> dict[str, Any]:
        """
        :return: the SonarQube platform global navigation data
        """
        if self.__global_nav is None:
            resp = self.get("navigation/global", mute=(HTTPStatus.INTERNAL_SERVER_ERROR,))
            self.__global_nav = json.loads(resp.text)
        return self.__global_nav

    def database(self) -> str:
        """Returns the SonarQube platform backend database"""
        if self.is_sonarcloud():
            return "postgresql"
        return self.sys_info()["Database"]["Database"]

    def plugins(self) -> dict[str, dict[str, str]]:
        """Returns the SonarQube platform plugins data"""
        if self.is_sonarcloud():
            return {}
        sysinfo = self.sys_info()
        if "Application Nodes" in sysinfo:
            sysinfo = sysinfo["Application Nodes"][0]
        return sif.Sif(sysinfo).plugins()

    def get_settings(self, settings_list: Optional[list[str]] = None) -> dict[str, dict[str, Any]]:
        """Returns a list of (or all) platform global settings dict representation from their key"""
        if settings_list is None:
            settings_dict = settings.get_bulk(endpoint=self)
        else:
            settings_dict = {k: settings.get_object(endpoint=self, key=k) for k in settings_list}
        platform_settings = {}
        for v in settings_dict.values():
            platform_settings |= v.to_json()
        return platform_settings

    def __settings(self, settings_list: KeyList = None, include_not_set: bool = False) -> dict[str, settings.Setting]:
        log.info("Getting global settings")
        settings_dict = settings.get_bulk(endpoint=self, settings_list=settings_list, include_not_set=include_not_set)
        if ai_code_fix := settings.Setting.read(endpoint=self, key=settings.AI_CODE_FIX):
            settings_dict[ai_code_fix.key] = ai_code_fix
        return settings_dict

    def get_setting(self, key: str) -> Any:
        """Returns a platform global setting value from its key

        :param key: Setting key
        :return: the setting value
        """
        return settings.get_object(endpoint=self, key=key).to_json()[key].get("value")

    def reset_setting(self, key: str) -> bool:
        """Resets a platform global setting to the SonarQube internal default value

        :param key: Setting key
        :return: Whether the reset was successful or not
        """
        return settings.reset_setting(self, key)

    def set_setting(self, key: str, value: Any) -> bool:
        """Sets a platform global setting

        :param key: Setting key
        :param value: Setting value
        :return: Whether setting the value was successful or not
        """
        return settings.set_setting(self, key, value)

    def __urlstring(self, api: str, params: Optional[ApiParams] = None, data: Optional[str] = None) -> str:
        """Returns a string corresponding to the URL and parameters"""
        url = f"{str(self)}{api}"
        params_string = ""
        if isinstance(params, str):
            params_string = params
        elif params:
            if isinstance(params, dict):
                good_params = {k: v for k, v in params.items() if v is not None}
            elif isinstance(params, (list, tuple)):
                good_params = {t[0]: [t[1]] for t in params if t[1] is not None}
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

    def webhooks(self) -> dict[str, webhooks.WebHook]:
        """Returns the list of global webhooks"""
        return webhooks.WebHook.get_list(self)

    def export(self, export_settings: ConfigSettings, full: bool = False) -> ObjectJsonRepr:
        """Exports the global platform properties as JSON

        :param full: Whether to also export properties that cannot be set, defaults to False
        :return: dict of all properties with their values
        """
        log.info("Exporting platform global settings")
        json_data = {}
        settings_list = list(self.__settings(include_not_set=True).values())
        settings_list = [s for s in settings_list if s.is_global() and not s.is_internal()]
        settings_list.append(settings.Setting.read(settings.NEW_CODE_PERIOD, self))
        for s in settings_list:
            (categ, subcateg) = s.category()
            if self.is_sonarcloud() and categ == settings.THIRD_PARTY_SETTINGS:
                # What is reported as 3rd part are SonarQube Cloud internal settings
                continue
            setting_json = s.to_json()
            if setting_json[s.key]["defaultValue"] == setting_json[s.key]["value"]:
                setting_json[s.key].pop("value")
            sutil.update_json(json_data, categ, subcateg, setting_json)

        hooks = {}
        for wb in self.webhooks().values():
            j = util.remove_nones(wb.to_json(full))
            j.pop("name", None)
            hooks[wb.name] = j
        if len(hooks) > 0:
            json_data["webhooks"] = hooks
        json_data["permissions"] = self.global_permissions().export(export_settings=export_settings)
        json_data["permissionTemplates"] = permission_templates.export(self, export_settings=export_settings)
        if not self.is_sonarcloud():
            json_data[settings.DEVOPS_INTEGRATION] = devops.export(self, export_settings=export_settings)

        return pfhelp.convert_global_settings_json(json_data)

    def set_webhooks(self, webhooks_data: ObjectJsonRepr) -> bool:
        """Sets global webhooks with a list of webhooks represented as JSON

        :param webhooks_data: The list of webhooks JSON representation
        :return: The number of webhooks configured
        """
        log.debug("%s setting webhooks %s", str(self), str(webhooks_data))
        if webhooks_data is None:
            return False
        webhooks.import_config(self, webhooks_data)
        return True

    def import_config(self, config_data: ObjectJsonRepr) -> int:
        """Imports a whole SonarQube platform global configuration represented as JSON

        :param config_data: the sonar-config configuration representation of the platform
        :return: Number of imported settings
        """
        if not (config_data := config_data.get("globalSettings", None)):
            log.info("No global settings to import")
            return 0
        count = 0
        settings_to_import = {k: v for k, v in config_data.items() if k not in ("devopsIntegration", "permissionTemplates", "webhooks")}
        flat_settings = sutil.flatten(settings_to_import)
        count += sum(1 if self.set_setting(k, v) else 0 for k, v in flat_settings.items())

        try:
            self.set_webhooks(config_data["webhooks"])
            count += len(config_data["webhooks"])
        except KeyError:
            pass

        if settings.NEW_CODE_PERIOD in config_data[settings.GENERAL_SETTINGS]:
            (nc_type, nc_val) = settings.decode(settings.NEW_CODE_PERIOD, config_data[settings.GENERAL_SETTINGS][settings.NEW_CODE_PERIOD])
            try:
                settings.set_new_code_period(self, nc_type, nc_val)
                count += 1
            except exceptions.UnsupportedOperation as e:
                log.error(e.message)
        count += permission_templates.import_config(self, config_data)
        count += global_permissions.import_config(self, config_data)
        try:
            count += devops.import_config(self, config_data)
        except exceptions.UnsupportedOperation as e:
            log.warning(e.message)
        log.debug("Imported and set %d settings", count)
        return count

    def audit(self, audit_settings: ConfigSettings) -> list[Problem]:
        """Audits a global platform configuration and returns the list of problems found

        :param audit_settings: Audit options and thresholds to raise problems
        :return: List of problems found, or empty list
        """
        log.info("--- Auditing global settings ---")
        problems = []
        platform_settings = {k: v["value"] for k, v in self.get_settings().items()}
        settings_url = f"{self.local_url}/admin/settings"
        for key in audit_settings:
            if key.startswith("audit.globalSettings.range"):
                problems += _audit_setting_in_range(key, platform_settings, audit_settings, self.version(), settings_url)
            elif key.startswith("audit.globalSettings.value"):
                problems += _audit_setting_value(key, platform_settings, audit_settings, settings_url)
            elif key.startswith("audit.globalSettings.isSet"):
                problems += _audit_setting_set(
                    key, check_is_set=True, platform_settings=platform_settings, audit_settings=audit_settings, url=settings_url
                )
            elif key.startswith("audit.globalSettings.isNotSet"):
                problems += _audit_setting_set(
                    key, check_is_set=False, platform_settings=platform_settings, audit_settings=audit_settings, url=settings_url
                )

        problems += (
            self._audit_project_default_visibility(audit_settings)
            + self._audit_global_permissions()
            + self.audit_logs(audit_settings)
            + permission_templates.audit(self, audit_settings)
        )
        for wh in self.webhooks().values():
            problems += wh.audit()

        if self.is_sonarcloud():
            return problems

        pf_sif = self.sys_info() | {"edition": self.edition()}
        problems += (
            _audit_maintainability_rating_grid(platform_settings, audit_settings, settings_url)
            + self._audit_admin_password()
            + self.audit_lta_latest()
            + self._audit_token_max_lifetime(audit_settings)
            + sif.Sif(pf_sif, self).audit(audit_settings)
        )
        return problems

    def _audit_logfile(self, logtype: str, logfile: str) -> list[Problem]:
        """Audits a log file for errors and warnings"""
        problems = []
        try:
            logs = self.get("system/logs", params={"name": logtype}).text
        except (ConnectionError, RequestException) as e:
            sutil.handle_error(e, f"retrieving {logtype} logs", catch_all=True)
            return []
        i = 0
        error_rule, warn_rule = None, None
        for line in logs.splitlines():
            if i % 1000 == 0:
                log.debug("Inspecting log line (%d) %s", i, line)
            i += 1
            if " ERROR " in line:
                log.warning("Error found in %s: %s", logfile, line)
                if error_rule is None:
                    error_rule = get_rule(RuleId.ERROR_IN_LOGS)
                    problems.append(Problem(error_rule, f"{self.local_url}/admin/system", logfile, line))
            elif " WARN " in line:
                log.warning("Warning found in %s: %s", logfile, line)
                if warn_rule is None:
                    warn_rule = get_rule(RuleId.WARNING_IN_LOGS)
                    problems.append(Problem(warn_rule, f"{self.local_url}/admin/system", logfile, line))
        return problems

    def _audit_deprecation_logs(self) -> list[Problem]:
        """Audits that there are no deprecation warnings in logs"""
        logs = self.get("system/logs", params={"name": "deprecation"}).text
        if (nb_deprecation := len(logs.splitlines())) > 0:
            rule = get_rule(RuleId.DEPRECATION_WARNINGS)
            return [Problem(rule, f"{self.local_url}/admin/system", nb_deprecation)]
        return []

    def audit_logs(self, audit_settings: ConfigSettings) -> list[Problem]:
        """Audits that there are no anomalies in logs (errors, warnings, deprecation warnings)"""
        if not audit_settings.get("audit.logs", True):
            log.info("Logs audit is disabled, skipping logs audit...")
            return []
        if self.is_sonarcloud():
            log.info("Logs audit not available with SonarQube Cloud, skipping logs audit...")
            return []
        log_map = {"app": "sonar.log", "ce": "ce.log", "web": "web.log", "es": "es.log"}
        if self.edition() == c.DCE:
            log_map.pop("es")
        problems = []
        for logtype, logfile in log_map.items():
            problems += self._audit_logfile(logtype, logfile)
        problems += self._audit_deprecation_logs()
        return problems

    def _audit_project_default_visibility(self, audit_settings: ConfigSettings) -> list[Problem]:
        """Audits whether project default visibility is public"""
        log.info("Auditing project default visibility")
        problems = []
        api, _, params, _ = self.api.get_details(settings.Setting, Oper.GET, keys="projects.default.visibility")
        resp = self.get(api, params=params)
        visi = json.loads(resp.text)["settings"][0]["value"]
        log.info("Project default visibility is '%s'", visi)
        if audit_settings.get("audit.globalSettings.defaultProjectVisibility", "private") != visi:
            rule = get_rule(RuleId.SETTING_PROJ_DEFAULT_VISIBILITY)
            problems.append(Problem(rule, f"{self.local_url}/admin/projects_management", visi))
        return problems

    def _audit_admin_password(self) -> list[Problem]:
        log.info("Auditing admin password")
        problems = []
        try:
            r = requests.get(url=self.local_url + "/api/authentication/validate", auth=("admin", "admin"), timeout=self.http_timeout)
            data = json.loads(r.text)
            if data.get("valid", False):
                problems.append(Problem(get_rule(RuleId.DEFAULT_ADMIN_PASSWORD), self.local_url))
            else:
                log.info("User 'admin' default password has been changed")
        except requests.RequestException as e:
            raise exceptions.SonarException(str(e), errcodes.SONAR_API) from e
        return problems

    def __audit_group_permissions(self) -> list[Problem]:
        log.info("Auditing group global permissions")
        problems = []
        perms_url = f"{self.local_url}/admin/permissions"
        groups = self.global_permissions().groups()
        if len(groups) > 10:
            problems.append(Problem(get_rule(rule_id=RuleId.RISKY_GLOBAL_PERMISSIONS), perms_url, len(groups)))

        for gr_name, gr_perms in groups.items():
            if gr_name == "Anyone":
                problems.append(Problem(get_rule(RuleId.ANYONE_WITH_GLOBAL_PERMS), perms_url))
            if self.is_default_user_group(gr_name) and (
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
        perms_url = f"{self.local_url}/admin/permissions"
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

    def audit_lta_latest(self) -> list[Problem]:
        """Audits that a SonarQube server version is LTA or LATEST"""
        if self.is_sonarcloud():
            return []
        sq_vers, v = self.version(), None
        if sq_vers < update_center.get_lta()[:2]:
            rule = get_rule(RuleId.BELOW_LTA)
            v = update_center.get_lta()
        elif sq_vers < update_center.get_lta():
            rule = get_rule(RuleId.LTA_PATCH_MISSING)
            v = update_center.get_lta()
        elif sq_vers[:2] > update_center.get_lta()[:2] and sq_vers < update_center.get_latest()[:2]:
            rule = get_rule(RuleId.BELOW_LATEST)
            v = update_center.get_latest()
        if not v:
            return []
        # pylint: disable-next=E0606
        return [Problem(rule, self.external_url, ".".join([str(n) for n in sq_vers]), ".".join([str(n) for n in v]))]

    def _audit_token_max_lifetime(self, audit_settings: ConfigSettings) -> list[Problem]:
        """Audits the maximum lifetime of a token"""
        log.info("Auditing maximum token lifetime global setting")
        lifetime_setting = settings.get_object(self, settings.TOKEN_MAX_LIFETIME)
        if lifetime_setting is None:
            log.info("Token maximum lifetime setting not found, skipping audit")
            return []
        max_lifetime = sutil.to_days(self.get_setting(settings.TOKEN_MAX_LIFETIME))
        if max_lifetime is None:
            return [Problem(get_rule(RuleId.TOKEN_LIFETIME_UNLIMITED), self.external_url)]
        if max_lifetime > audit_settings.get("audit.tokens.maxAge", 90):
            return [Problem(get_rule(RuleId.TOKEN_LIFETIME_TOO_HIGH), self.external_url, max_lifetime, audit_settings.get("audit.tokens.maxAge", 90))]
        return []

    def is_mqr_mode(self) -> bool:
        """Returns whether the platform is in MQR mode"""
        if self.is_sonarcloud():
            return True
        if self.version() >= (10, 8, 0):
            return self.get_setting(settings.MQR_ENABLED)
        return self.version() >= c.MQR_INTRO_VERSION

    def set_mqr_mode(self, enable: bool = True) -> bool:
        """Enables or disables MQR mode on the platform"""
        if self.is_sonarcloud():
            log.error("Cannot change MQR mode on SonarQube Cloud")
            return False
        if self.version() < c.MQR_INTRO_VERSION:
            log.error("MQR mode not available before SonarQube %s", sutil.version_to_string(c.MQR_INTRO_VERSION))
            return False
        if self.version() >= (10, 8, 0):
            return self.set_setting(settings.MQR_ENABLED, enable)
        return False

    def set_standard_experience(self) -> bool:
        """Sets the platform to standard experience mode (disables MQR if available)"""
        return self.set_mqr_mode(False)

    @staticmethod
    def __check_for_retry(response: requests.models.Response) -> tuple[bool, str]:
        """Verifies if a response had a 301 Moved permanently and if so provide the new location"""
        if len(response.history) > 0 and response.history[0].status_code == HTTPStatus.MOVED_PERMANENTLY:
            new_url = "/".join(response.history[0].headers["Location"].split("/")[0:3])
            log.debug("Moved permanently to URL %s", new_url)
            return True, new_url
        return False, None


# --------------------- Static methods -----------------
# this is a pointer to the module object instance itself.
this = sys.modules[__name__]
this.context = Platform(os.getenv("SONAR_HOST_URL", "http://localhost:9000"), os.getenv("SONAR_TOKEN", ""))


def _audit_setting_value(key: str, platform_settings: dict[str, Any], audit_settings: ConfigSettings, url: str) -> list[Problem]:
    """Audits a particular platform setting is set to expected value"""
    if (v := _get_multiple_values(4, audit_settings[key], "MEDIUM", "CONFIGURATION")) is None:
        log.error(WRONG_CONFIG_MSG, key, audit_settings[key])
        return []
    if v[0] not in platform_settings:
        log.warning(_NON_EXISTING_SETTING_SKIPPED, v[0])
        return []
    log.info("Auditing that setting %s has common/recommended value '%s'", v[0], v[1])
    s = platform_settings.get(v[0], "")
    if isinstance(s, bool):
        v[1] = util.convert_string(v[1])
    if s == v[1]:
        return []
    msg = f"Setting {v[0]} has potentially incorrect or unsafe value '{s}'"
    return [Problem(get_rule(RuleId.DUBIOUS_GLOBAL_SETTING), url, msg)]


def _audit_setting_in_range(
    key: str, platform_settings: dict[str, Any], audit_settings: ConfigSettings, sq_version: tuple[int, int, int], url: str
) -> list[Problem]:
    """Audits a particular platform setting is within expected range of values"""
    if (v := _get_multiple_values(5, audit_settings[key], "MEDIUM", "CONFIGURATION")) is None:
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


def _audit_setting_set(key: str, check_is_set: bool, platform_settings: dict[str, Any], audit_settings: ConfigSettings, url: str) -> list[Problem]:
    """Audits that a setting is set or not set"""
    if (v := _get_multiple_values(3, audit_settings[key], "MEDIUM", "CONFIGURATION")) is None:
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


def _audit_maintainability_rating_grid(platform_settings: dict[str, Any], audit_settings: ConfigSettings, url: str) -> list[Problem]:
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


def import_config(endpoint: Platform, config_data: ObjectJsonRepr, key_list: KeyList = None) -> int:
    """Imports a configuration in SonarQube

    :param Platform endpoint: reference to the SonarQube platform
    :param ObjectJsonRepr config_data: the configuration to import
    :param KeyList key_list: Unused
    """
    return endpoint.import_config(config_data)


def export(endpoint: Platform, export_settings: ConfigSettings, **kwargs: Any) -> ObjectJsonRepr:
    """Exports all or a list of projects configuration as dict

    :param Platform endpoint: reference to the SonarQube platform
    :param ConfigSettings export_settings: Export parameters
    :return: Platform settings
    """
    exp = endpoint.export(export_settings)
    if write_q := kwargs.get("write_q", None):
        write_q.put(exp)
        write_q.put(sutil.WRITE_END)
    return exp


def basics(endpoint: Platform, **kwargs: Any) -> ObjectJsonRepr:
    """Returns an endpooint basic info (license, edition, version etc..)"""
    exp = endpoint.basics()
    if write_q := kwargs.get("write_q", None):
        write_q.put(exp)
        write_q.put(sutil.WRITE_END)
    return exp


def audit(endpoint: Platform, audit_settings: ConfigSettings, **kwargs: Any) -> list[Problem]:
    """Audits a platform"""
    if not audit_settings.get("audit.globalSettings", True):
        log.info("Auditing global settings is disabled, audit skipped...")
        return []
    pbs = endpoint.audit(audit_settings)
    "write_q" in kwargs and kwargs["write_q"].put(pbs)
    return pbs
