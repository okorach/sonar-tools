#
# sonar-tools
# Copyright (C) 2022-2025 Olivier Korach
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
Abstraction of the SonarQube setting concept
"""

from __future__ import annotations
import re
import json
from typing import Any, Union, Optional

import sonar.logging as log
import sonar.platform as pf
from sonar.util import types, cache, constants as c
from sonar import sqobject, exceptions
import sonar.utilities as util

DEVOPS_INTEGRATION = "devopsIntegration"
GENERAL_SETTINGS = "generalSettings"
LANGUAGES_SETTINGS = "languages"
AUTH_SETTINGS = "authentication"
LINTER_SETTINGS = "linters"
THIRD_PARTY_SETTINGS = "thirdParty"
ANALYSIS_SCOPE_SETTINGS = "analysisScope"
SAST_CONFIG_SETTINGS = "sastConfig"
TEST_SETTINGS = "tests"

CATEGORIES = (
    GENERAL_SETTINGS,
    ANALYSIS_SCOPE_SETTINGS,
    AUTH_SETTINGS,
    LANGUAGES_SETTINGS,
    TEST_SETTINGS,
    DEVOPS_INTEGRATION,
    SAST_CONFIG_SETTINGS,
    LINTER_SETTINGS,
    THIRD_PARTY_SETTINGS,
)

NEW_CODE_PERIOD = "newCodePeriod"
COMPONENT_VISIBILITY = "visibility"
PROJECT_DEFAULT_VISIBILITY = "projects.default.visibility"
AI_CODE_FIX = "sonar.ai.suggestions.enabled"
MQR_ENABLED = "sonar.multi-quality-mode.enabled"
TOKEN_MAX_LIFETIME = "sonar.auth.token.max.allowed.lifetime"

_GLOBAL_SETTINGS_WITHOUT_DEF = (AI_CODE_FIX, MQR_ENABLED)

_SQ_INTERNAL_SETTINGS = (
    "sonaranalyzer",
    "sonar.updatecenter",
    "sonar.plugins.risk.consent",
    "sonar.core.id",
    "sonar.core.startTime",
    "sonar.plsql.jdbc.driver.class",
)

_SC_INTERNAL_SETTINGS = (
    "sonaranalyzer",
    "sonar.updatecenter",
    "sonar.plugins.risk.consent",
    "sonar.core.id",
    "sonar.core.startTime",
    "sonar.plsql.jdbc.driver.class",
    "sonar.dbcleaner",
    "sonar.core.serverBaseURL",
    "email.",
    "sonar.builtIn",
    "sonar.issues.defaultAssigneeLogin",
    "sonar.filesize.limit",
    "sonar.kubernetes.activate",
    "sonar.lf",
    "sonar.notifications",
    "sonar.plugins.loadAll",
    "sonar.qualityProfiles.allowDisableInheritedRules",
    "sonar.scm.disabled",
    "sonar.technicalDebt",
    "sonar.issue.",
    "sonar.global",
    "sonar.forceAuthentication",
)

_INLINE_SETTINGS = (
    r"^.*\.file\.suffixes$",
    r"^.*\.reportPaths$",
    r"^sonar(\.[a-z]+)?\.(in|ex)clusions$",
    r"^sonar\.javascript\.(globals|environments)$",
    r"^sonar\.dbcleaner\.branchesToKeepWhenInactive$",
    r"^sonar\.rpg\.suffixes$",
    r"^sonar\.cs\.roslyn\.(bug|codeSmell|vulnerability)Categories$",
    r"^sonar\.governance\.report\.view\.recipients$",
    r"^sonar\.portfolios\.recompute\.hours$",
    r"^sonar\.cobol\.copy\.(directories|exclusions)$",
    r"^sonar\.cobol\.sql\.catalog\.defaultSchema$",
    r"^sonar\.docker\.file\.patterns$",
    r"^sonar\.auth\..*\.organizations$",
    r"^sonar\.azureresourcemanager\.file\.identifier$",
    r"^sonar\.java\.jvmframeworkconfig\.file\.patterns$",
    r"^sonar\.auth\.gitlab\.allowedGroups",
)

VALID_SETTINGS = set()


class Setting(sqobject.SqObject):
    """
    Abstraction of the Sonar setting concept
    """

    CACHE = cache.Cache()
    API = {
        c.CREATE: "settings/set",
        c.GET: "settings/values",
        c.LIST: "settings/list_definitions",
        "NEW_CODE_GET": "new_code_periods/show",
        "NEW_CODE_SET": "new_code_periods/set",
        "MQR_MODE": "v2/clean-code-policy/mode",
    }

    def __init__(self, endpoint: pf.Platform, key: str, component: Optional[object] = None, data: Optional[types.ApiPayload] = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.component = component
        self.value: Optional[Any] = None
        self.multi_valued: Optional[bool] = None
        self.inherited: Optional[bool] = None
        self._definition: types.ApiPayload = None
        self._is_global: Optional[bool] = None
        self.reload(data)
        log.debug("Created %s uuid %d value %s", str(self), hash(self), str(self.value))
        Setting.CACHE.put(self)

    @classmethod
    def read(cls, key: str, endpoint: pf.Platform, component: Optional[object] = None) -> Setting:
        """Reads a setting from the platform"""
        log.debug("Reading setting '%s' for %s", key, str(component))
        o = Setting.CACHE.get(key, component, endpoint.local_url)
        if o:
            return o
        data = get_settings_data(endpoint, key, component)
        return Setting.load(key=key, endpoint=endpoint, data=data, component=component)

    @classmethod
    def create(cls, key: str, endpoint: pf.Platform, value: Any = None, component: Optional[object] = None) -> Union[Setting, None]:
        """Creates a setting with a custom value"""
        log.debug("Creating setting '%s' of component '%s' value '%s'", key, str(component), str(value))
        r = endpoint.post(Setting.API[c.CREATE], params={"key": key, "component": component})
        if not r.ok:
            return None
        o = cls.read(key=key, endpoint=endpoint, component=component)
        return o

    @classmethod
    def load(cls, key: str, endpoint: pf.Platform, data: types.ApiPayload, component: Optional[object] = None) -> Setting:
        """Loads a setting with  JSON data"""
        log.debug("Loading setting '%s' of component '%s' with data %s", key, str(component), str(data))
        o = Setting.CACHE.get(key, component, endpoint.local_url)
        if not o:
            o = cls(key=key, endpoint=endpoint, data=data, component=component)
        o.reload(data)
        return o

    def __reload_inheritance(self, data: types.ApiPayload) -> bool:
        """Verifies if a setting is inherited from the data returned by SQ"""
        if "inherited" in data:
            self.inherited = data["inherited"]
        elif self.key == NEW_CODE_PERIOD:
            self.inherited = False
        elif "parentValues" in data or "parentValue" in data or "parentFieldValues" in data:
            self.inherited = False
        elif "category" in data:
            self.inherited = True
        elif self.component is not None:
            self.inherited = False
        else:
            self.inherited = True
        if self.component is None:
            self.inherited = True
        return self.inherited

    def reload(self, data: types.ApiPayload) -> None:
        """Reloads a Setting with JSON returned from Sonar API"""
        if not data:
            return
        self.multi_valued = data.get("multiValues", False)
        if self.key == NEW_CODE_PERIOD:
            self.value = new_code_to_string(data)
        elif self.key == MQR_ENABLED:
            self.value = data.get("mode", "MQR") != "STANDARD_EXPERIENCE"
        elif self.key == COMPONENT_VISIBILITY:
            self.value = data.get("visibility", None)
        elif self.key == "sonar.login.message":
            self.value: Optional[Any] = None
            if "values" in data and isinstance(data["values"], list) and len(data["values"]) > 0:
                self.value = data["values"][0]
        else:
            self.value = next((data[key] for key in ("fieldValues", "values", "value") if key in data), None)
            if not self.value and "defaultValue" in data:
                self.value = util.DEFAULT
        self.__reload_inheritance(data)

    def refresh(self) -> None:
        """Reads the setting value on SonarQube"""
        self.reload(get_settings_data(self.endpoint, self.key, self.component))

    def __hash__(self) -> int:
        """Returns object unique ID"""
        return hash((self.key, self.component.key if self.component else None, self.base_url()))

    def __str__(self) -> str:
        if self.component is None:
            return f"setting '{self.key}'"
        else:
            return f"setting '{self.key}' of {str(self.component)}"

    def set(self, value: Any) -> bool:
        """Sets a setting value, returns if operation succeeded"""
        log.debug("%s set to '%s'", str(self), str(value))
        if not self.is_settable():
            log.error("Setting '%s' does not seem to be a settable setting, trying to set anyway...", str(self))
            return False
        if value is None or value == "" or (self.key == "sonar.autodetect.ai.code" and value is True and self.endpoint.version() < (2025, 2, 0)):
            return self.reset()
        if self.key == MQR_ENABLED:
            if ok := self.patch(Setting.API["MQR_MODE"], params={"mode": "STANDARD_EXPERIENCE" if not value else "MQR"}).ok:
                self.value = value
            return ok
        if self.key in (COMPONENT_VISIBILITY, PROJECT_DEFAULT_VISIBILITY):
            if ok := set_visibility(endpoint=self.endpoint, component=self.component, visibility=value):
                self.value = value
            return ok

        # Hack: Up to 9.4 cobol settings are comma separated mono-valued, in 9.5+ they are multi-valued
        if self.endpoint.version() > (9, 4, 0) or not self.key.startswith("sonar.cobol"):
            value = decode(self.key, value)

        # With SonarQube 10.x you can't set the github URL
        if re.match(r"^sonar\.auth\.(.*)[Uu]rl$", self.key) and self.endpoint.version() >= (10, 0, 0):
            log.warning("GitHub URL (%s) cannot be set, skipping this setting", self.key)
            return False

        log.debug("Setting %s to value '%s'", str(self), str(value))
        params = {"key": self.key, "component": self.component.key if self.component else None} | encode(self, value)
        try:
            if ok := self.post(Setting.API[c.CREATE], params=params).ok:
                self.value = value
        except exceptions.SonarException:
            return False
        else:
            return ok

    def reset(self) -> bool:
        log.info("Resetting %s", str(self))
        params = {"keys": self.key} | {} if not self.component else {"component": self.component.key}
        try:
            ok = self.post("settings/reset", params=params).ok
            self.refresh()
        except exceptions.SonarException:
            return False
        else:
            return ok

    def to_json(self, list_as_csv: bool = True) -> types.ObjectJsonRepr:
        val = self.value
        if self.key == NEW_CODE_PERIOD:
            val = new_code_to_string(self.value)
        elif list_as_csv and isinstance(self.value, list):
            for reg in _INLINE_SETTINGS:
                if re.match(reg, self.key):
                    val = util.list_to_csv(val, separator=", ", check_for_separator=True)
                    break
        if val is None:
            val = ""
        # log.debug("JSON of %s = %s", self, {self.key: val})
        return {self.key: val}

    def definition(self) -> Optional[dict[str, str]]:
        """Returns the setting global definition"""
        if self._definition is None:
            self._definition = next((s for s in self.endpoint.global_settings_definitions() if s["key"] == self.key), None)
        return self._definition

    def is_global(self) -> bool:
        """Returns whether a setting global or specific for one component (project, branch, application, portfolio)"""
        if self.component:
            return False
        if self._is_global is None:
            self._is_global = self.definition() is not None or self.key in _GLOBAL_SETTINGS_WITHOUT_DEF
        return self._is_global

    def is_internal(self) -> bool:
        """Returns whether a setting is internal to the platform and is useless to expose externally"""
        internal_settings = _SQ_INTERNAL_SETTINGS
        if self.endpoint.is_sonarcloud():
            internal_settings = _SC_INTERNAL_SETTINGS
            if self.is_global():
                (categ, _) = self.category()
                if categ in ("languages", "analysisScope", "tests", "authentication"):
                    return True

        return any(self.key.startswith(prefix) for prefix in internal_settings)

    def is_settable(self) -> bool:
        """Returns whether a setting can be set"""
        if len(VALID_SETTINGS) == 0:
            get_bulk(endpoint=self.endpoint, include_not_set=True)
        if self.key not in VALID_SETTINGS:
            return False
        return not self.is_internal()

    def category(self) -> tuple[str, str]:
        """Returns the 2 levels classification of a setting"""
        m = re.match(
            r"^sonar\.(cpd\.)?(abap|androidLint|ansible|apex|azureresourcemanager|cloudformation|c|cpp|cfamily|cobol|cs|css|dart|docker|"
            r"eslint|flex|go|html|java|javascript|jcl|json|jsp|kotlin|objc|php|pli|plsql|python|ipynb|rpg|ruby|scala|swift|"
            r"terraform|text|tsql|typescript|vb|vbnet|xml|yaml|rust|jasmin)\.",
            self.key,
        )
        if m:
            lang = m.group(2)
            if lang in ("c", "cpp", "objc", "cfamily"):
                lang = "cfamily"
            elif lang in ("androidLint"):
                lang = "kotlin"
            elif lang in ("eslint", "jasmin"):
                lang = "javascript"
            return (LANGUAGES_SETTINGS, lang)
        if re.match(
            r"^.*([lL]int|govet|flake8|checkstyle|pmd|spotbugs|findbugs|phpstan|psalm|detekt|bandit|rubocop|scalastyle|scapegoat).*$",
            self.key,
        ):
            return (LINTER_SETTINGS, None)
        if re.match(r"^sonar\.security\.config\..+$", self.key):
            return (SAST_CONFIG_SETTINGS, None)
        if re.match(r"^.*\.(exclusions$|inclusions$|issue\..+)$", self.key):
            return (ANALYSIS_SCOPE_SETTINGS, None)

        if re.match(r"^.*(\.reports?Paths?$|unit\..*$|cov.*$)", self.key):
            return (TEST_SETTINGS, None)
        m = re.match(r"^sonar\.(auth\.|authenticator\.downcase).*$", self.key)
        if m:
            return (AUTH_SETTINGS, None)
        m = re.match(r"^sonar\.forceAuthentication$", self.key)
        if m:
            return (AUTH_SETTINGS, None)
        if re.match(r"^sonar\.dependencyCheck\..*$", self.key):
            return ("thirdParty", None)
        if self.key in (NEW_CODE_PERIOD, PROJECT_DEFAULT_VISIBILITY, MQR_ENABLED, COMPONENT_VISIBILITY) or re.match(
            r"^(sonar\.|email\.|provisioning\.git).*$",
            self.key,
        ):
            return (GENERAL_SETTINGS, None)
        return ("thirdParty", None)


def get_object(endpoint: pf.Platform, key: str, component: Optional[object] = None) -> Setting:
    """Returns a Setting object from its key and, optionally, component"""
    o = Setting.CACHE.get(key, component, endpoint.local_url)
    if not o:
        get_all(endpoint, component)
    return Setting.CACHE.get(key, component, endpoint.local_url)


def __get_settings(endpoint: pf.Platform, data: types.ApiPayload, component: Optional[object] = None) -> dict[str, Setting]:
    """Returns settings of the global platform or a specific component object (Project, Branch, App, Portfolio)"""
    settings = {}
    settings_type_list = ["settings"]
    # Hack: Sonar API also return setSecureSettings for projects although it's irrelevant
    if component is None:
        settings_type_list += ["setSecuredSettings"]

    for setting_type in settings_type_list:
        log.debug("Looking at %s", setting_type)
        for s in data.get(setting_type, {}):
            (key, sdata) = (s, {}) if isinstance(s, str) else (s["key"], s)
            o = Setting(endpoint=endpoint, key=key, component=component, data=None)
            if o.is_internal():
                log.debug("Skipping internal setting %s", s["key"])
                continue
            o = Setting.load(key=key, endpoint=endpoint, component=component, data=sdata)
            settings[o.key] = o
    return settings


def get_bulk(
    endpoint: pf.Platform, settings_list: Optional[types.KeyList] = None, component: Optional[object] = None, include_not_set: bool = False
) -> dict[str, Setting]:
    """Gets several settings as bulk (returns a dict)"""
    settings_dict = {}
    params = get_component_params(component)

    if include_not_set:
        data = json.loads(endpoint.get(Setting.API[c.LIST], params=params, with_organization=(component is None)).text)
        for s in data["definitions"]:
            if s["key"].endswith("coverage.reportPath") or s["key"] == "languageSpecificParameters":
                continue
            o = Setting.load(key=s["key"], endpoint=endpoint, data=s, component=component)
            settings_dict[o.key] = o

    if settings_list is not None:
        params["keys"] = util.list_to_csv(settings_list)

    data = json.loads(endpoint.get(Setting.API[c.GET], params=params, with_organization=(component is None)).text)
    settings_dict |= __get_settings(endpoint, data, component)

    # Hack since projects.default.visibility is not returned by settings/list_definitions
    try:
        o = get_visibility(endpoint, component)
        settings_dict[o.key] = o
    except exceptions.UnsupportedOperation as e:
        log.warning("%s", e.message)

    if not endpoint.is_sonarcloud():
        o = get_new_code_period(endpoint, component)
        settings_dict[o.key] = o
    VALID_SETTINGS.update(set(settings_dict.keys()))
    VALID_SETTINGS.update({"sonar.scm.provider", MQR_ENABLED})
    return settings_dict


def get_all(endpoint: pf.Platform, project: Optional[object] = None) -> dict[str, Setting]:
    """Returns all settings, global ones or component settings"""
    return get_bulk(endpoint, component=project, include_not_set=True)


def new_code_to_string(data: Union[int, str, dict[str, str]]) -> Union[int, str, None]:
    """Converts a new code period from anything to int str"""
    if isinstance(data, (int, str)):
        return data
    if data.get("inherited", False):
        return None
    if data["type"] == "PREVIOUS_VERSION":
        return data["type"]
    elif data["type"] == "SPECIFIC_ANALYSIS":
        return f"{data['type']} = {data['effectiveValue']}"
    else:
        return f"{data['type']} = {data['value']}"


def string_to_new_code(value: str) -> list[str]:
    """Converts a new code period from str to list"""
    return re.split(r"\s*=\s*", value)


def get_new_code_period(endpoint: pf.Platform, project_or_branch: object) -> Setting:
    """returns the new code period, either the default global setting, or specific to a project/branch"""
    return Setting.read(key=NEW_CODE_PERIOD, endpoint=endpoint, component=project_or_branch)


def set_new_code_period(endpoint: pf.Platform, nc_type: str, nc_value: str, project_key: Optional[str] = None, branch: Optional[str] = None) -> bool:
    """Sets the new code period at global level or for a project"""
    log.debug("Setting new code period for project '%s' branch '%s' to value '%s = %s'", str(project_key), str(branch), str(nc_type), str(nc_value))
    if endpoint.is_sonarcloud():
        ok = endpoint.post(Setting.API[c.CREATE], params={"key": "sonar.leak.period.type", "value": nc_type, "project": project_key}).ok
        ok = ok and endpoint.post(Setting.API[c.CREATE], params={"key": "sonar.leak.period", "value": nc_value, "project": project_key}).ok
    else:
        ok = endpoint.post(Setting.API["NEW_CODE_SET"], params={"type": nc_type, "value": nc_value, "project": project_key, "branch": branch}).ok
    return ok


def get_visibility(endpoint: pf.Platform, component: object) -> str:
    """Returns the platform global or component visibility"""
    key = COMPONENT_VISIBILITY if component else PROJECT_DEFAULT_VISIBILITY
    o = Setting.CACHE.get(key, component, endpoint.local_url)
    if o:
        return o
    if component:
        data = json.loads(endpoint.get("components/show", params={"component": component.key}).text)
        return Setting.load(key=COMPONENT_VISIBILITY, endpoint=endpoint, component=component, data=data["component"])
    else:
        if endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation("Project default visibility does not exist in SonarQube Cloud")
        data = json.loads(endpoint.get(Setting.API[c.GET], params={"keys": PROJECT_DEFAULT_VISIBILITY}).text)
        return Setting.load(key=PROJECT_DEFAULT_VISIBILITY, endpoint=endpoint, component=None, data=data["settings"][0])


def set_visibility(endpoint: pf.Platform, visibility: str, component: Optional[object] = None) -> bool:
    """Sets the platform global default visibility or component visibility"""
    if component:
        log.debug("Setting setting '%s' of %s to value '%s'", COMPONENT_VISIBILITY, str(component), visibility)
        return endpoint.post("projects/update_visibility", params={"project": component.key, "visibility": visibility}).ok
    else:
        log.debug("Setting setting '%s' to value '%s'", PROJECT_DEFAULT_VISIBILITY, str(visibility))
        return endpoint.post("projects/update_default_visibility", params={"projectVisibility": visibility}).ok


def set_setting(endpoint: pf.Platform, key: str, value: Any, component: Optional[object] = None) -> bool:
    """Sets a setting to a particular value"""
    try:
        log.debug("Setting %s with value %s (for component %s)", key, value, component)
        s = get_object(endpoint=endpoint, key=key, component=component)
        if not s:
            log.warning("Setting '%s' does not exist on target platform, it cannot be set", key)
            return False
        s.set(value)
    except exceptions.SonarException as e:
        log.error("Setting '%s' cannot be set: %s", key, e.message)
        return False
    else:
        return True


def decode(setting_key: str, setting_value: Any) -> Any:
    """Decodes a setting"""
    if setting_key == NEW_CODE_PERIOD:
        if isinstance(setting_value, int):
            return ("NUMBER_OF_DAYS", setting_value)
        elif setting_value == "PREVIOUS_VERSION":
            return (setting_value, "")
        return string_to_new_code(setting_value)
    if not isinstance(setting_value, str):
        return setting_value
    # TODO(okorach): Handle all comma separated settings
    for reg in _INLINE_SETTINGS:
        if re.match(reg, setting_key):
            setting_value = util.csv_to_list(setting_value)
            break
    return setting_value


def encode(setting: Setting, setting_value: Any) -> dict[str, Any]:
    """Encodes the params to pass to api/settings/set according to setting value type"""
    if isinstance(setting_value, list):
        return {"values": setting_value} if isinstance(setting_value[0], str) else {"fieldValues": [json.dumps(v) for v in setting_value]}
    if isinstance(setting_value, bool):
        return {"value": str(setting_value).lower()}
    return {"values" if setting.multi_valued else "value": setting_value}


def reset_setting(endpoint: pf.Platform, setting_key: str, project: Optional[object] = None) -> bool:
    """Resets a setting to its default"""
    return get_object(endpoint=endpoint, key=setting_key, component=project).reset()


def get_component_params(component: object, name: str = "component") -> types.ApiParamss:
    """Gets the parameters to read or write settings"""
    if not component:
        return {}
    elif type(component).__name__ == "Branch":
        return {name: component.project.key, "branch": component.key}
    else:
        return {name: component.key}


def get_settings_data(endpoint: pf.Platform, key: str, component: Optional[object]) -> types.ApiPayload:
    """Reads a setting data with different API depending on setting key

    :param Platform endpoint: The SonarQube Platform object
    :param str key: The setting key
    :param object component: The component (Project) concerned, optional
    :return: The returned API data
    """
    if key == NEW_CODE_PERIOD and not endpoint.is_sonarcloud():
        params = get_component_params(component, name="project")
        data = json.loads(endpoint.get(Setting.API["NEW_CODE_GET"], params=params).text)
    elif key == MQR_ENABLED:
        data = json.loads(endpoint.get(Setting.API["MQR_MODE"]).text)
    else:
        if key == NEW_CODE_PERIOD:
            key = "sonar.leak.period.type"
        params = get_component_params(component)
        params.update({"keys": key})
        data = json.loads(endpoint.get(Setting.API[c.GET], params=params, with_organization=(component is None)).text)["settings"]
        if not endpoint.is_sonarcloud() and len(data) > 0:
            data = data[0]
        else:
            data = {"inherited": True}
    return data
