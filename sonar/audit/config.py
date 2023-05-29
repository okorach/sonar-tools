#
# sonar-tools
# Copyright (C) 2019-2023 Olivier Korach
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
import os
import pathlib
import jprops
import sonar.utilities as util

_CONFIG_SETTINGS = None


def _load_properties_file(file):
    settings = {}
    try:
        with open(file, "r", encoding="utf-8") as fp:
            util.logger.info("Loading config file %s", file)
            settings = jprops.load_properties(fp)
    except FileNotFoundError:
        pass
    except PermissionError:
        util.logger.warning(
            "Insufficient permissions to open file %s, configuration will be skipped",
            file,
        )
    return settings


def load(config_name=None, settings=None):
    global _CONFIG_SETTINGS

    if settings is None:
        settings = {}

    default_conf = _load_properties_file(pathlib.Path(__file__).parent / f"{config_name}.properties")
    home_conf = _load_properties_file(f"{os.path.expanduser('~')}{os.sep}.{config_name}.properties")
    local_conf = _load_properties_file(f"{os.getcwd()}{os.sep}{config_name}.properties")

    _CONFIG_SETTINGS = {**default_conf, **home_conf, **local_conf, **settings}

    for key, value in _CONFIG_SETTINGS.items():
        _CONFIG_SETTINGS[key] = util.convert_string(value)

    util.logger.debug("Audit settings = %s", util.json_dump(_CONFIG_SETTINGS))
    return _CONFIG_SETTINGS


def get_property(name, settings=None):
    if settings is None:
        settings = _CONFIG_SETTINGS
    return settings.get(name, "")


def configure():
    template_file = pathlib.Path(__file__).parent / "sonar-audit.properties"
    with open(template_file, "r", encoding="utf-8") as fh:
        text = fh.read()

    config_file = f"{os.path.expanduser('~')}{os.sep}.sonar-audit.properties"
    if os.path.isfile(config_file):
        util.logger.info(
            "Config file '%s' already exists, sending configuration to stdout",
            config_file,
        )
        print(text)
    else:
        util.logger.info("Creating file '%s'", config_file)
        with open(config_file, "w", encoding="utf-8") as fh:
            print(text, file=fh)
