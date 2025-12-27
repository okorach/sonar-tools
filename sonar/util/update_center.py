#
# sonar-tools
# Copyright (C) 2024-2025 Olivier Korach
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

"""Update center utilities"""

import os
from typing import Optional
import datetime
import requests
import tempfile
import jprops
import sonar.logging as log
import sonar.util.misc as util
from sonar import version

_UPDATE_CENTER_URL = "https://downloads.sonarsource.com/sonarqube/update/update-center-all-versions.properties"
_HARDCODED_LTA = (2025, 1, 1)
_HARDCODED_LATEST = (2025, 2, 0)

_HARDCODED_LTA_STR = ".".join([str(i) for i in _HARDCODED_LTA])
_HARDCODED_LATEST_STR = ".".join([str(i) for i in _HARDCODED_LATEST])

_UPDATE_CENTER_PROPERTIES = None


def get_update_center_properties() -> Optional[dict[str, str]]:
    """
    Gets Sonar update center properties
    :returns: All properties as dict or None if update center is unreachable
    """
    global _UPDATE_CENTER_PROPERTIES
    _SONAR_TOOLS_AGENT = f"sonar-tools {version.PACKAGE_VERSION}"

    if _UPDATE_CENTER_PROPERTIES is not None:
        return _UPDATE_CENTER_PROPERTIES
    try:
        log.debug("Attempting to reach Sonar update center")
        _, tmpfile = tempfile.mkstemp(prefix="sonar-tools", suffix=".txt", text=True)
        with open(tmpfile, "w", encoding="utf-8") as fp:
            print(requests.get(_UPDATE_CENTER_URL, headers={"user-agent": _SONAR_TOOLS_AGENT}, timeout=10).text, file=fp)
        with open(tmpfile, "r", encoding="utf-8") as fp:
            _UPDATE_CENTER_PROPERTIES = jprops.load_properties(fp)
        os.remove(tmpfile)
    except OSError as e:
        log.warning("Sonar update center error %s, hardcoding LTA (ex-LTS) = %s, LATEST = %s", str(e), _HARDCODED_LTA_STR, _HARDCODED_LATEST_STR)
        _UPDATE_CENTER_PROPERTIES = {}

    log.debug("Sonar update center properties loaded dict: %s", _UPDATE_CENTER_PROPERTIES)
    return _UPDATE_CENTER_PROPERTIES


def get_release_date(version: tuple[int, ...]) -> Optional[datetime.date]:
    """Get the release date from a SonarQube Server or Community Build release
    :returns: The release date or None if not found"""
    digits = 2 if len(version) == 3 and version[2] == 0 else min(len(version), 3)
    formatted_release = ".".join(str(i) for i in version[:digits])
    str_date = get_update_center_properties().get(f"{formatted_release}.date", "")
    if str_date == "":
        log.info("Release date for SonarQube version %s not found in update center properties", formatted_release)
        return None
    else:
        log.info("Release date for SonarQube version %s was found in update center properties: %s", formatted_release, str_date)
        return util.to_date(str_date)


def get_lta() -> tuple[int, ...]:
    """
    :returns: the current SonarQube LTA (ex-LTS) version
    """
    return tuple(int(s) for s in get_update_center_properties().get("ltaVersion", _HARDCODED_LTA_STR).split("."))


def get_latest() -> tuple[int, ...]:
    """
    :returns: the current SonarQube LATEST version
    """
    sqs = get_update_center_properties().get("sqs", "").split(",")[-1].strip()
    if sqs == "":
        return _HARDCODED_LATEST
    else:
        return tuple(int(s) for s in sqs.split("."))


def get_registered_plugins() -> list[str]:
    """
    :returns: a list of registered plugin keys in the update center
    """
    plugins = get_update_center_properties().get("plugins", None)
    if not plugins:
        return []
    return [p.strip() for p in plugins.split(",") if p.strip() != ""]
