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

TYPE_VULN = "VULNERABILITY"
TYPE_BUG = "BUG"
TYPE_CODE_SMELL = "CODE_SMELL"
TYPE_HOTSPOT = "SECURITY_HOTSPOT"
TYPE_NONE = "NONE"

QUALITY_SECURITY = "SECURITY"
QUALITY_RELIABILITY = "RELIABILITY"
QUALITY_MAINTAINABILITY = "MAINTAINABILITY"
QUALITY_NONE = "NONE"

STD_SEVERITY_BLOCKER = "BLOCKER"
STD_SEVERITY_CRITICAL = "CRITICAL"
STD_SEVERITY_MAJOR = "MAJOR"
STD_SEVERITY_MINOR = "MINOR"
STD_SEVERITY_INFO = "INFO"

MQR_SEVERITY_BLOCKER = "BLOCKER"
MQR_SEVERITY_HIGH = "HIGH"
MQR_SEVERITY_MEDIUM = "MEDIUM"
MQR_SEVERITY_LOW = "LOW"
MQR_SEVERITY_INFO = "INFO"

SEVERITY_NONE = "NONE"

STD_TYPES = (TYPE_VULN, TYPE_BUG, TYPE_CODE_SMELL)
ALL_TYPES = (TYPE_VULN, TYPE_BUG, TYPE_CODE_SMELL, TYPE_HOTSPOT)

MQR_QUALITIES = (QUALITY_SECURITY, QUALITY_RELIABILITY, QUALITY_MAINTAINABILITY)
STD_SEVERITIES = (STD_SEVERITY_BLOCKER, STD_SEVERITY_CRITICAL, STD_SEVERITY_MAJOR, STD_SEVERITY_MINOR, STD_SEVERITY_INFO)
MQR_SEVERITIES = (MQR_SEVERITY_BLOCKER, MQR_SEVERITY_HIGH, MQR_SEVERITY_MEDIUM, MQR_SEVERITY_LOW, MQR_SEVERITY_INFO)


# Mapping between old issues type and new software qualities
TYPE_QUALITY_MAPPING = {
    TYPE_CODE_SMELL: QUALITY_MAINTAINABILITY,
    TYPE_BUG: QUALITY_RELIABILITY,
    TYPE_VULN: QUALITY_SECURITY,
    TYPE_HOTSPOT: QUALITY_SECURITY,
    TYPE_NONE: QUALITY_NONE,
}

STATUSES = ("OPEN", "CONFIRMED", "REOPENED", "RESOLVED", "CLOSED", "ACCEPTED", "FALSE_POSITIVE")
RESOLUTIONS = ("FALSE-POSITIVE", "WONTFIX", "FIXED", "REMOVED", "ACCEPTED")


# Mapping between old and new severities
SEVERITY_MAPPING = {
    STD_SEVERITY_BLOCKER: MQR_SEVERITY_BLOCKER,
    STD_SEVERITY_CRITICAL: MQR_SEVERITY_HIGH,
    STD_SEVERITY_MAJOR: MQR_SEVERITY_MEDIUM,
    STD_SEVERITY_MINOR: MQR_SEVERITY_LOW,
    STD_SEVERITY_INFO: MQR_SEVERITY_INFO,
    SEVERITY_NONE: SEVERITY_NONE,
}


def std_to_mqr_severity(std_severity: str) -> str:
    """Converts standard severity to MQR severity"""
    return SEVERITY_MAPPING.get(std_severity, SEVERITY_NONE)


def mqr_to_std_severity(mqr_severity: str) -> str:
    """Converts MQR severity to standard severity"""
    return next((sev for sev, mqr_sev in SEVERITY_MAPPING.items() if mqr_sev == mqr_severity), SEVERITY_NONE)


def type_to_mqr_quality(issue_type: str) -> str:
    """Converts issue type to MQR software quality"""
    return TYPE_QUALITY_MAPPING.get(issue_type, QUALITY_NONE)


def mqr_quality_to_type(sw_quality: str) -> str:
    """Converts MQR software quality to issue type"""
    return next((issue_type for issue_type, quality in TYPE_QUALITY_MAPPING.items() if quality == sw_quality), TYPE_NONE)
