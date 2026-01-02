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
from typing import Any, Union, Optional, TYPE_CHECKING

import re
import json

import sonar.logging as log
from sonar.util import cache, constants as c
from sonar import sqobject, exceptions
import sonar.util.misc as util
from sonar.api.manager import ApiOperation as op
from sonar.api.manager import ApiManager as Api

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ObjectJsonRepr, KeyList

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

_GLOBAL_SETTINGS_WITHOUT_DEF = (AI_CODE_FIX, MQR_ENABLED, "sonar.cfamily.ignoreHeaderComments")

_SQ_INTERNAL_SETTINGS = (
    "sonaranalyzer",
    "sonar.updatecenter",
    "sonar.plugins.risk.consent",
    "sonar.core.id",
    "sonar.core.startTime",
    "sonar.plsql.jdbc.driver.class",
    "sonar.documentation.baseUrl",
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

VALID_SETTINGS: set[str] = set()


class Setting(sqobject.SqObject):
    """Abstraction of the Sonar setting concept"""

    CACHE = cache.Cache()

    def __init__(self, endpoint: Platform, key: str, component: Optional[object] = None, data: Optional[ApiPayload] = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.component = component
        self.default_value: Optional[Any] = None
        self.value: Optional[Any] = None
        self.multi_valued: Optional[bool] = None
        self.inherited: Optional[bool] = None
        self._definition: ApiPayload = None
        self._is_global: Optional[bool] = None
        self.reload(data)
        log.debug("Constructed %s uuid %d value %s", str(self), hash(self), str(self.value))
        Setting.CACHE.put(self)

    @classmethod
    def read(cls, key: str, endpoint: Platform, component: Optional[object] = None) -> Setting:
        """Reads a setting from the platform"""
        log.debug("Reading setting '%s' for %s", key, str(component))
        if o := Setting.CACHE.get(key, component, endpoint.local_url):
            return o
        data = get_settings_data(endpoint, key, component)
        return Setting.load(key=key, endpoint=endpoint, data=data, component=component)

    @classmethod
    def create(cls, key: str, endpoint: Platform, value: Any = None, component: Optional[object] = None) -> Union[Setting, None]:
        """Creates a setting with a custom value"""
        log.debug("Creating setting '%s' of component '%s' value '%s'", key, str(component), str(value))
        api, _, params, _ = Api(Setting, op.CREATE, endpoint).get_all(key=key, component=component)
        r = endpoint.post(api, params=params)
        if not r.ok:
            return None
        o = cls.read(key=key, endpoint=endpoint, component=component)
        return o

    @classmethod
    def load(cls, key: str, endpoint: Platform, data: ApiPayload, component: Optional[object] = None) -> Setting:
        """Loads a setting with  JSON data"""
        log.debug("Loading setting '%s' of component '%s' with data %s", key, str(component), str(data))
        o = Setting.CACHE.get(key, component, endpoint.local_url)
        if not o:
            o = cls(key=key, endpoint=endpoint, data=data, component=component)
        o.reload(data)
        return o

    @classmethod
    def load_from_definition(cls, key: str, endpoint: Platform, def_data: ApiPayload) -> Setting:
        """Loads a setting with  JSON data"""
        log.debug("Loading setting '%s' from definition %s", key, def_data)
        if not (o := Setting.CACHE.get(key, None, endpoint.local_url)):
            o = cls(key=key, endpoint=endpoint, data=None, component=None)
        o._definition = def_data
        o.multi_valued = def_data.get("multiValues")
        default_val = def_data.get("defaultValue", "" if o.multi_valued else None)
        o.default_value = sorted(util.csv_to_list(default_val)) if o.multi_valued else util.convert_to_type(default_val)
        if o.value is None:
            o.value = o.default_value
        return o

    def __reload_inheritance(self, data: ApiPayload) -> bool:
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

    def reload(self, data: Optional[ApiPayload] = None) -> None:
        """Reloads a Setting with JSON returned from Sonar API"""
        log.debug("Reloading setting %s data: %s", self.key, data)
        if not data:
            return
        if self.key == NEW_CODE_PERIOD:
            self.value = new_code_to_string(data)
        elif self.key == MQR_ENABLED:
            self.value = data.get("mode", "MQR") != "STANDARD_EXPERIENCE"
        elif self.key == COMPONENT_VISIBILITY:
            self.value = data.get("visibility", None)
        elif self.key in ("sonar.login.message", "sonar.announcement.message"):
            self.value = None
            if "values" in data and isinstance(data["values"], list) and len(data["values"]) > 0:
                self.value = data["values"][0]
        else:
            self.value = util.convert_to_type(next((data[key] for key in ("fieldValues", "values", "value") if key in data), None))
            if self.value is None:
                self.value = self.default_value
            if isinstance(self.value, list) and all(isinstance(v, str) for v in self.value):
                self.value = sorted(self.value)
            def_value = util.convert_to_type(next((data[key] for key in ("parentFieldValues", "parentValues", "parentValue") if key in data), None))
            if def_value is not None:
                self.default_value = def_value
            if isinstance(self.default_value, list) and all(isinstance(v, str) for v in self.default_value):
                self.default_value = sorted(self.default_value)
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
            api, _, params, _ = Api(self, op.SET_MQR_MODE).get_all(mode="STANDARD_EXPERIENCE" if not value else "MQR")
            if ok := self.patch(api, params=params).ok:
                self.value = value
            return ok
        if self.key in (COMPONENT_VISIBILITY, PROJECT_DEFAULT_VISIBILITY):
            if ok := set_visibility(endpoint=self.endpoint, component=self.component, visibility=value):
                self.value = value
            return ok

        # With SonarQube 10.x you can't set the github URL
        if re.match(r"^sonar\.auth\.(.*)[Uu]rl$", self.key) and self.endpoint.version() >= (10, 0, 0):
            log.warning("GitHub URL (%s) cannot be set, skipping this setting", self.key)
            return False

        if self.multi_valued and isinstance(value, str):
            value = util.csv_to_list(value)
        if not self.multi_valued and isinstance(value, list):
            value = util.list_to_csv(value)
        log.debug("Setting %s to value '%s'", str(self), str(value))
        params = {"key": self.key, "component": self.component.key if self.component else None} | encode(self, value)
        try:
            api, _, api_params, _ = Api(self, op.CREATE).get_all(**params)
            if ok := self.post(api, params=api_params).ok:
                self.value = value
        except exceptions.SonarException:
            return False
        else:
            return ok

    def reset(self) -> bool:
        log.info("Resetting %s", str(self))
        params = {"keys": self.key} | {} if not self.component else {"component": self.component.key}
        try:
            api, _, api_params, _ = Api(self, op.RESET).get_all(**params)
            ok = self.post(api, params=api_params).ok
            self.refresh()
        except exceptions.SonarException:
            return False
        else:
            return ok

    def to_json(self) -> ObjectJsonRepr:
        val = self.value
        def_val = self.default_value
        if self.key == NEW_CODE_PERIOD:
            val = new_code_to_string(self.value)
            def_val = None if self.default_value is None else new_code_to_string(self.default_value)
        if val is None:
            val = ""
        return {self.key: {"key": self.key, "value": val, "defaultValue": def_val}}

    def definition(self) -> Optional[dict[str, str]]:
        """Returns the setting global definition"""
        return self.endpoint.global_settings_definitions().get(self.key)

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

    def is_default_value(self) -> bool:
        """Returns whether a setting is at its default value"""
        return self.value == self.default_value

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
            r"^sonar\.(cpd\.|dre\.)?(abap|androidLint|ansible|apex|azureresourcemanager|cloudformation|c|cpp|cfamily|cobol|cs|css|dart|docker|"
            r"eslint|flex|go|html|java|javascript|jcl|json|jsp|kotlin|objc|php|pli|plsql|python|ipynb|rpg|ruby|scala|shell|swift|"
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


def get_object(endpoint: Platform, key: str, component: Optional[object] = None) -> Setting:
    """Returns a Setting object from its key and, optionally, component"""
    o = Setting.CACHE.get(key, component.key if component else None, endpoint.local_url)
    if not o:
        get_all(endpoint, component)
    return Setting.CACHE.get(key, component.key if component else None, endpoint.local_url)


def __get_settings(endpoint: Platform, data: ApiPayload, component: Optional[sqobject.SqObject] = None) -> dict[str, Setting]:
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
            o: Optional[Setting] = Setting.CACHE.get(key, component.key if component else None, endpoint.local_url)
            if not o:
                o = Setting(endpoint=endpoint, key=key, component=component, data=sdata)
            else:
                o.reload(sdata)
            if o.is_internal():
                log.debug("Skipping internal setting %s", key)
                continue
            settings[o.key] = o
    return settings


def get_bulk(
    endpoint: Platform, settings_list: Optional[KeyList] = None, component: Optional[object] = None, include_not_set: bool = False
) -> dict[str, Setting]:
    """Gets several settings as bulk (returns a dict)"""
    global VALID_SETTINGS
    settings_dict = {}

    if include_not_set:
        for key, data in endpoint.global_settings_definitions().items():
            if key.endswith("coverage.reportPath") or key == "languageSpecificParameters":
                continue
            settings_dict[key] = Setting.load_from_definition(key=key, endpoint=endpoint, def_data=data)

    params = get_component_params(component)
    if settings_list is not None:
        params["keys"] = util.list_to_csv(settings_list)

    api, _, api_params, _ = Api(Setting, op.LIST, endpoint).get_all(**params)
    data = json.loads(endpoint.get(api, params=api_params, with_organization=(component is None)).text)
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
    VALID_SETTINGS |= set(settings_dict.keys()) | {"sonar.scm.provider", MQR_ENABLED, "sonar.cfamily.ignoreHeaderComments"}
    return settings_dict


def get_all(endpoint: Platform, project: Optional[object] = None) -> dict[str, Setting]:
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


def get_new_code_period(endpoint: Platform, project_or_branch: object) -> Setting:
    """returns the new code period, either the default global setting, or specific to a project/branch"""
    return Setting.read(key=NEW_CODE_PERIOD, endpoint=endpoint, component=project_or_branch)


def set_new_code_period(endpoint: Platform, nc_type: str, nc_value: str, project_key: Optional[str] = None, branch: Optional[str] = None) -> bool:
    """Sets the new code period at global level or for a project"""
    log.debug("Setting new code period for project '%s' branch '%s' to value '%s = %s'", str(project_key), str(branch), str(nc_type), str(nc_value))
    if endpoint.is_sonarcloud():
        api, _, params1, _ = Api(Setting, op.CREATE, endpoint).get_all(key="sonar.leak.period.type", value=nc_type, project=project_key)
        ok = endpoint.post(api, params=params1).ok
        api, _, params2, _ = Api(Setting, op.CREATE, endpoint).get_all(key="sonar.leak.period", value=nc_value, project=project_key)
        ok = ok and endpoint.post(api, params=params2).ok
    else:
        api, _, params, _ = Api(Setting, op.SET_NEW_CODE_PERIOD, endpoint).get_all(type=nc_type, value=nc_value, project=project_key, branch=branch)
        ok = endpoint.post(api, params=params).ok
    return ok


def get_visibility(endpoint: Platform, component: object) -> Setting:
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
        api, _, params, _ = Api(Setting, op.READ, endpoint).get_all(keys=PROJECT_DEFAULT_VISIBILITY)
        data = json.loads(endpoint.get(api, params=params).text)
        return Setting.load(key=PROJECT_DEFAULT_VISIBILITY, endpoint=endpoint, component=None, data=data["settings"][0])


def set_visibility(endpoint: Platform, visibility: str, component: Optional[object] = None) -> bool:
    """Sets the platform global default visibility or component visibility"""
    if component:
        log.debug("Setting setting '%s' of %s to value '%s'", COMPONENT_VISIBILITY, str(component), visibility)
        return endpoint.post("projects/update_visibility", params={"project": component.key, "visibility": visibility}).ok
    else:
        log.debug("Setting setting '%s' to value '%s'", PROJECT_DEFAULT_VISIBILITY, str(visibility))
        return endpoint.post("projects/update_default_visibility", params={"projectVisibility": visibility}).ok


def set_setting(endpoint: Platform, key: str, value: Any, component: Optional[object] = None) -> bool:
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


def reset_setting(endpoint: Platform, setting_key: str, project: Optional[object] = None) -> bool:
    """Resets a setting to its default"""
    return get_object(endpoint=endpoint, key=setting_key, component=project).reset()


def get_component_params(component: object, name: str = "component") -> ApiParams:
    """Gets the parameters to read or write settings"""
    if not component:
        return {}
    elif type(component).__name__ == "Branch":
        return {name: component.project.key, "branch": component.key}
    else:
        return {name: component.key}


def get_settings_data(endpoint: Platform, key: str, component: Optional[object]) -> ApiPayload:
    """Reads a setting data with different API depending on setting key

    :param endpoint: The SonarQube Platform object
    :param key: The setting key
    :param component: The component (Project) concerned, optional
    :return: The returned API data
    """
    if key == NEW_CODE_PERIOD and not endpoint.is_sonarcloud():
        params = get_component_params(component, name="project")
        api, _, api_params, _ = Api(Setting, op.GET_NEW_CODE_PERIOD, endpoint).get_all(**params)
        data = json.loads(endpoint.get(api, params=api_params).text)
    elif key == MQR_ENABLED:
        api, _, params, _ = Api(Setting, op.GET_MQR_MODE, endpoint).get_all()
        data = json.loads(endpoint.get(api, params=params).text)
    else:
        if key == NEW_CODE_PERIOD:
            key = "sonar.leak.period.type"
        params = get_component_params(component)
        params.update({"keys": key})
        api, _, api_params, _ = Api(Setting, op.READ, endpoint).get_all(**params)
        data = json.loads(endpoint.get(api, params=api_params, with_organization=(component is None)).text)["settings"]
        if not endpoint.is_sonarcloud() and len(data) > 0:
            data = data[0]
        else:
            data = {"inherited": True}
    return data
