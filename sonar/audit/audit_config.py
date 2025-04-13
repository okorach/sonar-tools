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

"""sonar-config CLI"""
import os
import pathlib
import jprops
from typing import Optional
import sonar.logging as log
from sonar.util import types
import sonar.utilities as util

_CONFIG_SETTINGS = None


def _load_properties_file(file: str) -> types.ConfigSettings:
    """Loads a properties file"""
    settings = {}
    try:
        with open(file, "r", encoding="utf-8") as fp:
            log.info("Loading config file %s", file)
            settings = jprops.load_properties(fp)
    except FileNotFoundError:
        pass
    except PermissionError:
        log.warning(
            "Insufficient permissions to open file %s, configuration will be skipped",
            file,
        )
    return settings


def load(config_name: Optional[str] = None, settings: types.ConfigSettings = None) -> types.ConfigSettings:
    """Loads a particular configuration file"""
    global _CONFIG_SETTINGS

    if settings is None:
        settings = {}

    _CONFIG_SETTINGS = _load_properties_file(pathlib.Path(__file__).parent / f"{config_name}.properties")
    _CONFIG_SETTINGS.update(_load_properties_file(f"{os.path.expanduser('~')}{os.sep}.{config_name}.properties"))
    _CONFIG_SETTINGS.update(_load_properties_file(f"{os.getcwd()}{os.sep}.{config_name}.properties"))
    _CONFIG_SETTINGS.update(settings)

    _CONFIG_SETTINGS = {k: util.convert_string(v) for k, v in _CONFIG_SETTINGS.items()}
    for item in "globalSettings", "qualityGates", "qualityProfiles", "projects", "applications", "portfolios", "users", "groups", "plugins":
        main_switch = f"audit.{item}"
        if _CONFIG_SETTINGS.get(main_switch, True):
            continue
        for k in _CONFIG_SETTINGS.copy().keys():
            if k != main_switch and k.lower().startswith(main_switch.lower()):
                _CONFIG_SETTINGS.pop(k)

    log.info("Audit settings = %s", util.json_dump(_CONFIG_SETTINGS))
    return _CONFIG_SETTINGS


def configure() -> None:
    """Configures a default sonar-audit.properties"""
    template_file = pathlib.Path(__file__).parent / "sonar-audit.properties"
    with open(template_file, "r", encoding="utf-8") as fh:
        text = fh.read()

    config_file = f"{os.path.expanduser('~')}{os.sep}.sonar-audit.properties"
    if os.path.isfile(config_file):
        log.info("Config file '%s' already exists, sending configuration to stdout", config_file)
        print(text)
    else:
        log.info("Creating file '%s'", config_file)
        with open(config_file, "w", encoding="utf-8") as fh:
            print(text, file=fh)
