#
# sonar-tools
# Copyright (C) 2022-2026 Olivier Korach
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

Exceptions raised but the sonar python APIs

"""

from sonar import errcodes


class SonarException(Exception):
    """sonar-tools exceptions"""

    def __init__(self, message: str, code: int) -> None:
        """Constructor"""
        super().__init__()
        self.message = message
        self.errcode = code

    def __str__(self) -> str:
        """String representation of the exception"""
        return f"ERROR {self.errcode}: {self.message}"


class ObjectNotFound(SonarException):
    """Object not found during a SonarQube search"""

    def __init__(self, key: str, message: str) -> None:
        """Constructor"""
        super().__init__(message, errcodes.NO_SUCH_KEY)
        self.key = key


class ObjectAlreadyExists(SonarException):
    """Object already exists when trying to create it"""

    def __init__(self, key: str, message: str) -> None:
        """Constructor"""
        super().__init__(message, errcodes.OBJECT_ALREADY_EXISTS)
        self.key = key


class UnsupportedOperation(SonarException):
    """Unsupported operation (most often due to edition not allowing it)"""

    def __init__(self, message: str) -> None:
        """Constructor"""
        super().__init__(message, errcodes.UNSUPPORTED_OPERATION)


class ConnectionError(SonarException):
    """ConnectionError error"""

    def __init__(self, message: str) -> None:
        """Constructor"""
        super().__init__(message, errcodes.CONNECTION_ERROR)


class NoPermissions(SonarException):
    """NoPermissions error"""

    def __init__(self, message: str) -> None:
        """Constructor"""
        super().__init__(message, errcodes.SONAR_API_AUTHORIZATION)
