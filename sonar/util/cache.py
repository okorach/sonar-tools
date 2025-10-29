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

"""Cache manager"""

from typing import Optional
from sonar import logging as log


class Cache(object):
    """Abstract cache implementation"""

    def __init__(self) -> None:
        """Constructor"""
        self.objects = {}
        self.object_class: Optional[type] = None

    def __len__(self) -> int:
        """Returns size of cache"""
        return len(self.objects)

    def __str__(self) -> str:
        """string repr of Cache"""
        return "'undefined class' cache" if not self.object_class else f"'{self.object_class.__name__}' cache"

    def set_class(self, object_class: object) -> None:
        """Defines the class the cache is for"""
        self.object_class = object_class

    def contents(self) -> str:
        """Returns the cache contents as a string"""
        return ", ".join([str(o) for o in self.objects.values()])

    def put(self, obj: object) -> object:
        """Add an object in cache if not already present"""
        h = hash(obj)
        if h not in self.objects:
            self.objects[h] = obj
        else:
            log.debug("%s already in cache, can't be added again", obj)
        # log.debug("PUT %s: %s", self, self.contents())
        return self.objects[h]

    def get(self, *args) -> Optional[object]:
        # log.debug("GET %s: %s", self, self.contents())
        return self.objects.get(hash(args), None)

    def pop(self, obj: object) -> Optional[object]:
        o = self.objects.pop(hash(obj), None)
        log.debug("POP %s: %s", self, self.contents())
        return o

    def values(self) -> list[object]:
        return list(self.objects.values())

    def keys(self) -> list[int]:
        return list(self.objects.keys())

    def items(self) -> dict[int, object]:
        return self.objects.items()

    def clear(self) -> None:
        """Clears a cache"""
        # log.info("Clearing %s", self)
        self.objects = {}
