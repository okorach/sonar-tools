#
# sonar-tools
# Copyright (C) 2022-2023 Olivier Korach
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

import re
import json
from sonar import sqobject
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

DEFAULT_SETTING = "__default__"

_OBJECTS = {}

_PRIVATE_SETTINGS = (
    "sonaranalyzer",
    "sonar.updatecenter",
    "sonar.plugins.risk.consent",
    "sonar.core.id",
    "sonar.core.startTime",
    "sonar.plsql.jdbc.driver.class",
)

_INLINE_SETTINGS = (
    r"^.*\.file\.suffixes$",
    r"^.*\.reportPaths$",
    r"^sonar(\.[a-z]+)?\.exclusions$",
    r"^sonar\.javascript\.(globals|environments)$",
    r"^sonar\.dbcleaner\.branchesToKeepWhenInactive$",
    r"^sonar\.rpg\.suffixes$",
    r"^sonar\.cs\.roslyn\.(bug|codeSmell|vulnerability)Categories$",
    r"^sonar\.governance\.report\.view\.recipients$",
    r"^sonar\.portfolios\.recompute\.hours$",
    r"^sonar\.cobol\.copy\.(directories|exclusions)$",
    r"^sonar\.cobol\.sql\.catalog\.defaultSchema$",
)

_API_SET = "settings/set"
_CREATE_API = "settings/set"
_API_GET = "settings/values"
_API_LIST = "settings/list_definitions"
API_NEW_CODE_GET = "new_code_periods/show"
_API_NEW_CODE_SET = "new_code_periods/set"

VALID_SETTINGS = set()


class Setting(sqobject.SqObject):
    @classmethod
    def read(cls, key, endpoint, component=None):
        util.logger.debug("Reading setting '%s' for %s", key, str(component))
        uu = _uuid_p(key, component)
        if uu in _OBJECTS:
            return _OBJECTS[uu]
        if key == NEW_CODE_PERIOD:
            params = get_component_params(component, name="project")
            data = json.loads(endpoint.get(API_NEW_CODE_GET, params=params).text)
        else:
            params = get_component_params(component)
            params.update({"keys": key})
            data = json.loads(endpoint.get(_API_GET, params=params).text)["settings"][0]
        return Setting.load(key=key, endpoint=endpoint, data=data, component=component)

    @classmethod
    def create(cls, key, endpoint, value=None, component=None):
        util.logger.debug("Creating setting '%s' of component '%s' value '%s'", key, str(component), str(value))
        r = endpoint.post(_CREATE_API, params={"key": key, "component": component})
        if not r.ok:
            return None
        o = cls.read(key=key, endpoint=endpoint, component=component)
        return o

    @classmethod
    def load(cls, key, endpoint, data, component=None):
        util.logger.debug("Loading setting '%s' of component '%s' with data %s", key, str(component), str(data))
        uu = _uuid_p(key, component)
        o = _OBJECTS[uu] if uu in _OBJECTS else cls(key=key, endpoint=endpoint, data=data, component=component)
        o.reload(data)
        return o

    def __init__(self, key, endpoint, component=None, data=None):
        super().__init__(key, endpoint)
        self.component = component
        self.value = None
        self.inherited = None
        self.reload(data)
        util.logger.debug("Created %s uuid %s value %s", str(self), self.uuid(), str(self.value))
        _OBJECTS[self.uuid()] = self

    def reload(self, data):
        if not data:
            return
        if self.key == NEW_CODE_PERIOD:
            self.value = new_code_to_string(data)
        elif self.key == COMPONENT_VISIBILITY:
            self.value = data["visibility"]
        elif self.key.startswith("sonar.issue."):
            self.value = data.get("fieldValues", None)
        else:
            self.value = util.convert_string(data.get("value", data.get("values", data.get("defaultValue", ""))))

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

    def uuid(self):
        return _uuid_p(self.key, self.component)

    def __str__(self):
        if self.component is None:
            return f"setting '{self.key}'"
        else:
            return f"setting '{self.key}' of {str(self.component)}"

    def set(self, value):
        util.logger.debug("%s set to '%s'", str(self), str(value))
        if not is_valid(self.key, self.endpoint):
            util.logger.error("Setting '%s' does not seem to be a valid setting, trying to set anyway...", str(self))
        if value is None or value == "":
            # TODO: return endpoint.reset_setting(key)
            return True
        if self.key in (COMPONENT_VISIBILITY, PROJECT_DEFAULT_VISIBILITY):
            return set_visibility(endpoint=self.endpoint, component=self.component, visibility=value)

        # Hack: Up to 9.4 cobol settings are comma separated mono-valued, in 9.5+ they are multi-valued
        if self.endpoint.version() > (9, 4, 0) or not __is_cobol_setting(self.key):
            value = decode(self.key, value)

        util.logger.debug("Setting %s to value '%s'", str(self), str(value))
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

    def to_json(self):
        return {self.key: encode(self.key, self.value)}

    def category(self):
        m = re.match(
            r"^sonar\.(cpd\.)?(abap|apex|cloudformation|c|cpp|cfamily|cobol|cs|css|flex|go|html|java|"
            r"javascript|json|jsp|kotlin|objc|php|pli|plsql|python|rpg|ruby|scala|swift|terraform|tsql|"
            r"typescript|vb|vbnet|xml|yaml)\.",
            self.key,
        )
        if m:
            lang = m.group(2)
            if lang in ("c", "cpp", "objc", "cfamily"):
                lang = "cfamily"
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
            r"sonar\.portfolios|sonar\.qualitygate|sonar\.scm\.disabled|sonar\.scm\.provider|sonar\.technicalDebt|sonar\.validateWebhooks).*$",
            self.key,
        ):
            return ("thirdParty", None)
        return (GENERAL_SETTINGS, None)


def get_object(key, component=None):
    return _OBJECTS.get(_uuid_p(key, component), None)


def get_bulk(endpoint, settings_list=None, component=None, include_not_set=False):
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
    if settings_list is None:
        pass
    elif isinstance(settings_list, list):
        params["keys"] = util.list_to_csv(settings_list)
    else:
        params["keys"] = util.csv_normalize(settings_list)
    data = json.loads(endpoint.get(_API_GET, params=params).text)
    settings_type_list = ["settings"]
    # Hack: Sonar API also return setSecureSettings for projects although it's irrelevant
    if component is None:
        settings_type_list = ["setSecuredSettings"]
    settings_type_list += ["settings"]
    for setting_type in settings_type_list:
        util.logger.debug("Looking at %s", setting_type)
        for s in data.get(setting_type, {}):
            (key, sdata) = (s, {}) if isinstance(s, str) else (s["key"], s)
            if is_private(key) > 0:
                util.logger.debug("Skipping private setting %s", s["key"])
                continue
            o = Setting.load(key=key, endpoint=endpoint, component=component, data=sdata)
            settings_dict[o.key] = o

    # Hack since projects.default.visibility is not returned by settings/list_definitions
    o = get_visibility(endpoint, component)
    settings_dict[o.key] = o

    o = get_new_code_period(endpoint, component)
    settings_dict[o.key] = o
    VALID_SETTINGS.update(set(settings_dict.keys()))
    VALID_SETTINGS.update({"sonar.scm.provider"})
    return settings_dict


def get_all(endpoint, project=None):
    return get_bulk(endpoint, component=project, include_not_set=True)


def uuid(key, project_key=None):
    """Computes uuid for a setting"""
    if project_key is None:
        return key
    else:
        return f"{key}#{project_key}"


def _uuid_p(key, component):
    """Computes uuid for a setting"""
    pk = None if component is None else component.key
    return uuid(key, pk)


def new_code_to_string(data):
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


def get_new_code_period(endpoint, project_or_branch):
    return Setting.read(key=NEW_CODE_PERIOD, endpoint=endpoint, component=project_or_branch)


def string_to_new_code(value):
    return re.split(r"\s*=\s*", value)


def set_new_code_period(endpoint, nc_type, nc_value, project_key=None, branch=None):
    util.logger.debug(
        "Setting new code period for project '%s' branch '%s' to value '%s = %s'", str(project_key), str(branch), str(nc_type), str(nc_value)
    )
    return endpoint.post(_API_NEW_CODE_SET, params={"type": nc_type, "value": nc_value, "project": project_key, "branch": branch})


def get_visibility(endpoint, component):
    uu = uuid(COMPONENT_VISIBILITY, component.key) if component else uuid(PROJECT_DEFAULT_VISIBILITY)
    if uu in _OBJECTS:
        return _OBJECTS[uu]
    if component:
        data = json.loads(endpoint.get("components/show", params={"component": component.key}).text)
        return Setting.load(key=COMPONENT_VISIBILITY, endpoint=endpoint, component=component, data=data["component"])
    else:
        data = json.loads(endpoint.get(_API_GET, params={"keys": PROJECT_DEFAULT_VISIBILITY}).text)
        return Setting.load(key=PROJECT_DEFAULT_VISIBILITY, endpoint=endpoint, component=None, data=data["settings"][0])


def set_visibility(endpoint, visibility, component=None):
    if component:
        util.logger.debug("Setting setting '%s' of %s to value '%s'", COMPONENT_VISIBILITY, str(component), visibility)
        return endpoint.post("projects/update_visibility", params={"project": component.key, "visibility": visibility})
    else:
        util.logger.debug("Setting setting '%s' to value '%s'", PROJECT_DEFAULT_VISIBILITY, str(visibility))
        r = endpoint.post("projects/update_default_visibility", params={"projectVisibility": visibility})
        return r


def __is_cobol_setting(key):
    return re.match(r"^sonar\.cobol\..*$", key)


def set_setting(endpoint, key, value, component=None):
    return Setting.load(key, endpoint=endpoint, component=component, data=None).set(value)


def encode(setting_key, setting_value):
    if setting_value is None:
        return ""
    if setting_key == NEW_CODE_PERIOD:
        return new_code_to_string(setting_value)
    if isinstance(setting_value, str):
        return setting_value
    if not isinstance(setting_value, list):
        return setting_value
    val = setting_value.copy()
    for reg in _INLINE_SETTINGS:
        if re.match(reg, setting_key):
            val = util.list_to_csv(val, ", ", True)
            break
    if val is None:
        val = ""
    return val


def decode(setting_key, setting_value):
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


def reset_setting(endpoint, setting_key, project_key=None):
    util.logger.info("Resetting setting '%s", setting_key)
    return endpoint.post("settings/reset", params={"key": setting_key, "component": project_key})


def get_component_params(component, name="component"):
    if not component:
        return {}
    elif type(component).__name__ == "Branch":
        return {name: component.project.key, "branch": component.key}
    else:
        return {name: component.key}


def is_valid(setting_key, endpoint):
    if len(VALID_SETTINGS) == 0:
        get_bulk(endpoint=endpoint, include_not_set=True)
    if setting_key not in VALID_SETTINGS:
        return False
    return not is_private(setting_key)


def is_private(setting_key):
    for prefix in _PRIVATE_SETTINGS:
        if setting_key.startswith(prefix):
            return True
    return False
