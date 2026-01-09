#
# sonar-tools
# Copyright (C) 2026 Olivier Korach
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
import site

from typing import Any, Union
import sonar.logging as log
from sonar.util import misc


def get_install_root() -> Path:
    """Returns the root install dir of the package"""
    return Path(site.getsitepackages()[0]) / "sonar"


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


def load(filename: str) -> dict[str, Any]:
    """Loads a particular configuration file"""
    base_name = filename.split("/")[-1]
    config_type = filename.split(".")[-1].lower()
    if config_type not in ("properties", "json"):
        raise ValueError(f"Invalid config type: {config_type}")

    files = (
        get_install_root() / filename,
        f"{os.path.expanduser('~')}{os.sep}.{base_name}",
        f"{os.getcwd()}{os.sep}.{base_name}",
    )
    settings = {}
    for file in files:
        log.debug(f"Loading config from {file}")
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


def configure(config_file: str, package_location: str) -> None:
    """Configures a default config file"""
    template_file = get_install_root() / package_location / config_file
    with open(template_file, "r", encoding="utf-8") as fh:
        text = fh.read()

    config_file = f"{os.path.expanduser('~')}{os.sep}.{config_file}"
    if os.path.isfile(config_file):
        log.info("Config file '%s' already exists, sending configuration to stdout", config_file)
        print(text)
    else:
        log.info("Creating file '%s'", config_file)
        with open(config_file, "w", encoding="utf-8") as fh:
            print(text, file=fh)


def get_cli_settings(**kwargs: Any) -> dict[str, Any]:
    """Extracts settings from CLI arguments"""
    cli_settings: dict[str, Any] = {}
    for val in kwargs.get("settings", []) or []:
        key, value = val[0].split("=", maxsplit=1)
        cli_settings[key] = misc.convert_string(value)
    kwargs.pop("settings", None)
    return cli_settings
