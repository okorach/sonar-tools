#
# sonar-tools
# Copyright (C) 2022-2024 Olivier Korach
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
from typing import Union

import sonar.logging as log
import sonar.platform as pf

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
UNIVERSAL_SEPARATOR = ":"

CATEGORIES = (
    GENERAL_SETTINGS,
    LANGUAGES_SETTINGS,
    ANALYSIS_SCOPE_SETTINGS,
    TEST_SETTINGS,
    LINTER_SETTINGS,
    AUTH_SETTINGS,
    SAST_CONFIG_SETTINGS,
    THIRD_PARTY_SETTINGS,
)

NEW_CODE_PERIOD = "newCodePeriod"
COMPONENT_VISIBILITY = "visibility"
PROJECT_DEFAULT_VISIBILITY = "projects.default.visibility"

DEFAULT_BRANCH = "-DEFAULT_BRANCH-"

_OBJECTS = {}

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
)

_API_SET = "settings/set"
_CREATE_API = "settings/set"
_API_GET = "settings/values"
_API_LIST = "settings/list_definitions"
API_NEW_CODE_GET = "new_code_periods/show"
_API_NEW_CODE_SET = "new_code_periods/set"

VALID_SETTINGS = set()


class Setting(sqobject.SqObject):
    """
    Abstraction of the Sonar setting concept
    """

    def __init__(self, endpoint: pf.Platform, key: str, component: object = None, data: dict[str, str] = None) -> None:
        """Constructor"""
        super().__init__(endpoint=endpoint, key=key)
        self.component = component
        self.value = None
        self.inherited = None
        self.reload(data)
        log.debug("Created %s uuid %s value %s", str(self), self.uuid(), str(self.value))
        _OBJECTS[self.uuid()] = self

    @classmethod
    def read(cls, key: str, endpoint: pf.Platform, component: object = None) -> Setting:
        """Reads a setting from the platform"""
        log.debug("Reading setting '%s' for %s", key, str(component))
        uid = uuid(key, component, endpoint.url)
        if uid in _OBJECTS:
            return _OBJECTS[uid]
        if key == NEW_CODE_PERIOD and not endpoint.is_sonarcloud():
            params = get_component_params(component, name="project")
            data = json.loads(endpoint.get(API_NEW_CODE_GET, params=params).text)
        else:
            if key == NEW_CODE_PERIOD:
                key = "sonar.leak.period.type"
            params = get_component_params(component)
            params.update({"keys": key})
            data = json.loads(endpoint.get(_API_GET, params=params).text)["settings"]
            if not endpoint.is_sonarcloud() and len(data) > 0:
                data = data[0]
            else:
                data = {"inherited": True}
        return Setting.load(key=key, endpoint=endpoint, data=data, component=component)

    @classmethod
    def create(cls, key: str, endpoint: pf.Platform, value: any = None, component: object = None) -> Union[Setting, None]:
        """Creates a setting with a custom value"""
        log.debug("Creating setting '%s' of component '%s' value '%s'", key, str(component), str(value))
        r = endpoint.post(_CREATE_API, params={"key": key, "component": component})
        if not r.ok:
            return None
        o = cls.read(key=key, endpoint=endpoint, component=component)
        return o

    @classmethod
    def load(cls, key: str, endpoint: pf.Platform, data: dict[str, str], component: object = None) -> Setting:
        """Loads a setting with  JSON data"""
        log.debug("Loading setting '%s' of component '%s' with data %s", key, str(component), str(data))
        uid = uuid(key, component, endpoint.url)
        o = _OBJECTS[uid] if uid in _OBJECTS else cls(key=key, endpoint=endpoint, data=data, component=component)
        o.reload(data)
        return o

    def reload(self, data: dict[str, str]) -> None:
        """Reloads a Setting with JSON returned from Sonar API"""
        if not data:
            return
        if self.key == NEW_CODE_PERIOD:
            self.value = new_code_to_string(data)
        elif self.key == COMPONENT_VISIBILITY:
            self.value = data.get("visibility", None)
        else:
            self.value = None
            for key in "value", "values", "fieldValues":
                if key in data:
                    self.value = util.convert_string(data[key])
            if not self.value and "defaultValue" in data:
                self.value = util.DEFAULT

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

    def uuid(self) -> str:
        """Returns object unique ID"""
        return uuid(self.key, self.component, self.endpoint.url)

    def __str__(self) -> str:
        if self.component is None:
            return f"setting '{self.key}'"
        else:
            return f"setting '{self.key}' of {str(self.component)}"

    def set(self, value: any) -> bool:
        """Sets a setting value, returns if operation succeeded"""
        log.debug("%s set to '%s'", str(self), str(value))
        if not self.is_settable():
            log.error("Setting '%s' does not seem to be a settable setting, trying to set anyway...", str(self))
        if value is None or value == "":
            # TODO: return endpoint.reset_setting(key)
            return True
        if self.key in (COMPONENT_VISIBILITY, PROJECT_DEFAULT_VISIBILITY):
            return set_visibility(endpoint=self.endpoint, component=self.component, visibility=value)

        # Hack: Up to 9.4 cobol settings are comma separated mono-valued, in 9.5+ they are multi-valued
        if self.endpoint.version() > (9, 4, 0) or not self.key.startswith("sonar.cobol"):
            value = decode(self.key, value)

        log.debug("Setting %s to value '%s'", str(self), str(value))
        params = {"key": self.key, "component": self.component.key if self.component else None}
        if isinstance(value, list):
            if isinstance(value[0], str):
                params["values"] = value
            else:
                params["fieldValues"] = [util.json.dumps(v) for v in value]
        else:
            if isinstance(value, bool):
                value = "true" if value else "false"
            params["value"] = value
        return self.post(_API_SET, params=params).ok

    def to_json(self, list_as_csv: bool = True) -> dict[str, str]:
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
        log.debug("to_json(%s: %s) = %s", self.key, str(self.value), str(val))
        return {self.key: val}

    def is_global(self) -> bool:
        """Returns whether a setting global or specific for one component (project, branch, application, portfolio)"""
        return self.component is None

    def is_internal(self) -> bool:
        """Returns whether a setting is internal to the platform and is useless to expose externally"""
        internal_settings = _SQ_INTERNAL_SETTINGS
        if self.endpoint.is_sonarcloud():
            internal_settings = _SC_INTERNAL_SETTINGS
            if self.is_global():
                (categ, _) = self.category()
                if categ in ("languages", "analysisScope", "tests", "authentication"):
                    return True

        for prefix in internal_settings:
            if self.key.startswith(prefix):
                return True
        return False

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
            r"^sonar\.(cpd\.)?(abap|androidLint|apex|azureresourcemanager|cloudformation|c|cpp|cfamily|cobol|cs|css|docker|"
            r"eslint|flex|go|html|java|javascript|jcl|json|jsp|kotlin|objc|php|pli|plsql|python|rpg|ruby|scala|swift|"
            r"terraform|text|tsql|typescript|vb|vbnet|xml|yaml)\.",
            self.key,
        )
        if m:
            lang = m.group(2)
            if lang in ("c", "cpp", "objc", "cfamily"):
                lang = "cfamily"
            elif lang in ("androidLint"):
                lang = "kotlin"
            elif lang in ("eslint"):
                lang = "javascript"
            return (LANGUAGES_SETTINGS, lang)
        if re.match(
            r"^.*([lL]int|govet|flake8|checkstyle|pmd|spotbugs|phpstan|psalm|detekt|bandit|rubocop|scalastyle|scapegoat).*$",
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
        if self.key not in (NEW_CODE_PERIOD, PROJECT_DEFAULT_VISIBILITY, COMPONENT_VISIBILITY) and not re.match(
            r"^(email|sonar\.core|sonar\.allowPermission|sonar\.builtInQualityProfiles|sonar\.core|"
            r"sonar\.cpd|sonar\.dbcleaner|sonar\.developerAggregatedInfo|sonar\.governance|sonar\.issues|sonar\.lf|sonar\.notifications|"
            r"sonar\.portfolios|sonar\.qualitygate|sonar\.scm\.disabled|sonar\.scm\.provider|sonar\.technicalDebt|sonar\.validateWebhooks|"
            r"sonar\.docker|sonar\.login|sonar\.kubernetes|sonar\.plugins|sonar\.documentation|sonar\.projectCreation|"
            r"sonar\.qualityProfiles|sonar\.announcement|provisioning\.git|sonar\.ce|sonar\.azureresourcemanager|sonar\.filesize\.limit).*$",
            self.key,
        ):
            return ("thirdParty", None)
        return (GENERAL_SETTINGS, None)


def get_object(endpoint: pf.Platform, key: str, component: object = None) -> Setting:
    """Returns a Setting object from its key and, optionally, component"""
    return _OBJECTS.get(uuid(key, component, endpoint.url), None)


def __get_settings(endpoint: pf.Platform, data: dict[str, str], component: object = None) -> dict[str, Setting]:
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


def get_bulk(endpoint: pf.Platform, settings_list: list[str] = None, component: object = None, include_not_set: bool = False) -> dict[str, Setting]:
    """Gets several settings as bulk (returns a dict)"""
    settings_dict = {}
    params = get_component_params(component)
    if include_not_set:
        data = json.loads(endpoint.get(_API_LIST, params=params).text)
        for s in data["definitions"]:
            if s["key"].endswith("coverage.reportPath") or s["key"] == "languageSpecificParameters":
                continue
            o = Setting.load(key=s["key"], endpoint=endpoint, data=s, component=component)
            settings_dict[o.key] = o

    if settings_list is not None:
        params["keys"] = util.list_to_csv(settings_list)

    data = json.loads(endpoint.get(_API_GET, params=params).text)
    settings_dict |= __get_settings(endpoint, data, component)

    # Hack since projects.default.visibility is not returned by settings/list_definitions
    try:
        o = get_visibility(endpoint, component)
        settings_dict[o.key] = o
    except exceptions.UnsupportedOperation as e:
        log.info("%s", str(e))

    if not endpoint.is_sonarcloud():
        o = get_new_code_period(endpoint, component)
        settings_dict[o.key] = o
    VALID_SETTINGS.update(set(settings_dict.keys()))
    VALID_SETTINGS.update({"sonar.scm.provider"})
    return settings_dict


def get_all(endpoint: pf.Platform, project: object = None) -> dict[str, Setting]:
    """Returns all settings, global ones or component settings"""
    return get_bulk(endpoint, component=project, include_not_set=True)


def uuid(key: str, component: object, url: str) -> str:
    """Computes uuid for a setting"""
    if not component:
        return f"{key}@{url}"
    else:
        return f"{key}#{component.key}@{url}"


def new_code_to_string(data: any) -> Union[int, str, None]:
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


def set_new_code_period(endpoint: pf.Platform, nc_type: str, nc_value: str, project_key: str = None, branch: str = None) -> bool:
    """Sets the new code period at global level or for a project"""
    log.debug("Setting new code period for project '%s' branch '%s' to value '%s = %s'", str(project_key), str(branch), str(nc_type), str(nc_value))
    return endpoint.post(_API_NEW_CODE_SET, params={"type": nc_type, "value": nc_value, "project": project_key, "branch": branch}).ok


def get_visibility(endpoint: pf.Platform, component: object) -> str:
    """Returns the platform global or component visibility"""
    key = COMPONENT_VISIBILITY if component else PROJECT_DEFAULT_VISIBILITY
    uid = uuid(key, component, endpoint.url)
    if uid in _OBJECTS:
        return _OBJECTS[uid]
    if component:
        data = json.loads(endpoint.get("components/show", params={"component": component.key}).text)
        return Setting.load(key=COMPONENT_VISIBILITY, endpoint=endpoint, component=component, data=data["component"])
    else:
        if endpoint.is_sonarcloud():
            raise exceptions.UnsupportedOperation("Project default visibility does not exist in SonarCloud")
        data = json.loads(endpoint.get(_API_GET, params={"keys": PROJECT_DEFAULT_VISIBILITY}).text)
        return Setting.load(key=PROJECT_DEFAULT_VISIBILITY, endpoint=endpoint, component=None, data=data["settings"][0])


def set_visibility(endpoint: pf.Platform, visibility: str, component: object = None) -> bool:
    """Sets the platform global default visibility or component visibility"""
    if component:
        log.debug("Setting setting '%s' of %s to value '%s'", COMPONENT_VISIBILITY, str(component), visibility)
        return endpoint.post("projects/update_visibility", params={"project": component.key, "visibility": visibility}).ok
    else:
        log.debug("Setting setting '%s' to value '%s'", PROJECT_DEFAULT_VISIBILITY, str(visibility))
        return endpoint.post("projects/update_default_visibility", params={"projectVisibility": visibility}).ok


def set_setting(endpoint: pf.Platform, key: str, value: any, component: object = None) -> None:
    """Sets a setting to a particular value"""
    get_object(endpoint=endpoint, key=key, component=component).set(value)


def decode(setting_key: str, setting_value: any) -> any:
    """Decodes a setting"""
    if setting_key == NEW_CODE_PERIOD:
        if isinstance(setting_value, int):
            return ("NUMBER_OF_DAYS", setting_value)
        elif setting_value == "PREVIOUS_VERSION":
            return (setting_value, "")
        return string_to_new_code(setting_value)
    if not isinstance(setting_value, str):
        return setting_value
    # TODO: Handle all comma separated settings
    for reg in _INLINE_SETTINGS:
        if re.match(reg, setting_key):
            setting_value = util.csv_to_list(setting_value)
            break
    return setting_value


def reset_setting(endpoint: pf.Platform, setting_key: str, project_key: str = None) -> bool:
    """Resets a setting to its default"""
    log.info("Resetting setting '%s", setting_key)
    return endpoint.post("settings/reset", params={"key": setting_key, "component": project_key}).ok


def get_component_params(component: object, name: str = "component") -> dict[str, str]:
    """Gets the parameters to read or write settings"""
    if not component:
        return {}
    elif type(component).__name__ == "Branch":
        return {name: component.project.key, "branch": component.key}
    else:
        return {name: component.key}
