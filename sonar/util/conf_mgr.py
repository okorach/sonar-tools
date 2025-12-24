#
# sonar-tools
# Copyright (C) 2025 Olivier Korach
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
"""Utility to manage configuration files"""

import os
from pathlib import Path
import json
import jprops

from typing import Optional, Any, Union
import sonar.logging as log
from sonar.util import misc


def _load_properties_file(file: Union[str, Path]) -> dict[str, Any]:
    """Loads a properties file"""
    with open(file, encoding="utf-8") as fp:
        log.info("Loading properties config file %s", file)
        return jprops.load_properties(fp) or {}


def _load_json_file(file: Union[str, Path]) -> dict[str, Any]:
    """Loads a JSON file"""
    with open(file, encoding="utf-8") as fp:
        log.info("Loading JSON config file %s", file)
        return json.loads(fp.read()) or {}


def load(filename: str, base_file: str) -> dict[str, Any]:
    """Loads a particular configuration file"""
    config_type = filename.split(".")[-1].lower()
    if config_type not in ("properties", "json"):
        raise ValueError(f"Invalid config type: {config_type}")

    files = (Path(base_file).parent / filename, f"{os.path.expanduser('~')}{os.sep}.{filename}", f"{os.getcwd()}{os.sep}.{filename}")
    settings = {}
    for file in files:
        try:
            if config_type == "properties":
                settings |= _load_properties_file(file)
            else:
                settings |= _load_json_file(file)
        except FileNotFoundError:
            pass
        except PermissionError:
            log.warning("Insufficient permissions to open file %s, configuration will be skipped", file)
    return misc.convert_types(settings)


def configure(config_name: str, config_type: Optional[str] = "properties") -> None:
    """Configures a default config file"""
    template_file = Path(__file__).parent / f"{config_name}.{config_type}"
    with open(template_file, "r", encoding="utf-8") as fh:
        text = fh.read()

    config_file = f"{os.path.expanduser('~')}{os.sep}.{config_name}.{config_type}"
    if os.path.isfile(config_file):
        log.info("Config file '%s' already exists, sending configuration to stdout", config_file)
        print(text)
    else:
        log.info("Creating file '%s'", config_file)
        with open(config_file, "w", encoding="utf-8") as fh:
            print(text, file=fh)
