#
# sonar-tools
# Copyright (C) 2019-2021 Olivier Korach
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
import jprops
import sonarqube.utilities as util

CONFIG_SETTINGS = None


def load(config_file=None):
    import pathlib
    global CONFIG_SETTINGS
    file_to_load = config_file
    if file_to_load is None:
        file_to_load = pathlib.Path(__file__).parent / 'sonar-tools.properties'

    try:
        util.logger.info("Trying to load audit config %s", file_to_load)
        fp = open(file_to_load)
    except FileNotFoundError:
        if config_file is None:
            file_to_load = pathlib.Path(__file__).parent / 'sonar-tools.properties'
        else:
            file_to_load = pathlib.Path(__file__).parent / config_file
        util.logger.info("Loading default audit config %s", config_file)
        fp = open(file_to_load)
    CONFIG_SETTINGS = jprops.load_properties(fp)
    fp.close()
    for key, value in CONFIG_SETTINGS.items():
        value = value.lower()
        if value == 'yes' or value == 'true' or value == 'on':
            CONFIG_SETTINGS[key] = True
            continue
        if value == 'no' or value == 'false' or value == 'off':
            CONFIG_SETTINGS[key] = False
            continue
        try:
            intval = int(value)
            CONFIG_SETTINGS[key] = intval
        except ValueError:
            pass

    return CONFIG_SETTINGS


def get_property(name, settings=None):
    if settings is None:
        global CONFIG_SETTINGS
        settings = CONFIG_SETTINGS
    return settings.get(name, '')
