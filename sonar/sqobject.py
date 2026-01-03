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
"""

Abstraction of the SonarQube general object concept

"""

from __future__ import annotations
from typing import Any, Optional, TYPE_CHECKING

import json
from http import HTTPStatus
import concurrent.futures
import requests

from sonar.api.manager import ApiManager as Api, ApiOperation as op
import sonar.logging as log
from sonar.util import cache
from sonar.util import constants as c
from sonar import exceptions, errcodes
import sonar.util.misc as util
import sonar.utilities as sutil

if TYPE_CHECKING:
    from sonar.platform import Platform
    from sonar.util.types import ApiParams, ApiPayload, ObjectJsonRepr


class SqObject(object):
    """Abstraction of Sonar objects"""

    CACHE = cache.Cache()
    API: dict[str, str] = {}  # Will be defined in the subclass

    def __init__(self, endpoint: Platform, key: str) -> None:
        if not self.__class__.CACHE:
            self.__class__.CACHE.set_class(self.__class__)
        self.key: str = key  #: Object unique key (unique in its class)
        self.endpoint: Platform = endpoint  #: Reference to the SonarQube platform
        self.concerned_object: Optional[object] = None
        self._tags: Optional[list[str]] = None
        self.sq_json: Optional[ApiPayload] = None

    def __hash__(self) -> int:
        """Default UUID for SQ objects"""
        return hash((self.key, self.base_url()))

    def __eq__(self, another: object) -> bool:
        if type(self) is type(another):
            return hash(self) == hash(another)
        return NotImplemented

    @classmethod
    def api_for(cls, operation: op, endpoint: Platform) -> str:
        """Returns the API to use for a particular operation for a particular object class.
        This function must be overloaded for classes that need specific treatment. e.g. API V1 or V2
        depending on SonarQube version, different API for SonarQube Cloud

        :param op: The desired API operation
        :param endpoint: The SQS or SQC to invoke the API
        :return: The API to use for the operation, or None if not defined
        """
        return cls.API[operation] if operation in cls.API else cls.API[op.SEARCH]

    @classmethod
    def clear_cache(cls, endpoint: Optional[Platform] = None) -> None:
        """Clears the cache of a given class

        :param endpoint: Optional, clears only the cache fo rthis platfiorm if specified, clear all if not
        """
        log.info("Emptying cache of %s", str(cls))
        try:
            if not endpoint:
                cls.CACHE.clear()
            else:
                for o in cls.CACHE.values().copy():
                    if o.base_url() != endpoint.local_url:
                        cls.CACHE.pop(o)
        except AttributeError:
            pass

    @classmethod
    def exists(cls, endpoint: Platform, **kwargs: Any) -> bool:
        """Tells whether an object with a given key exists"""
        try:
            log.debug("Checking if %s exists with kwargs %s", cls.__name__, kwargs)
            return cls.get_object(endpoint, **kwargs) is not None
        except exceptions.NoPermissions:
            return True
        except AttributeError as e:
            raise exceptions.UnsupportedOperation(f"Can't check existence of {cls.__name__.lower()}s") from e
        except exceptions.ObjectNotFound:
            return False

    @classmethod
    def has_access(cls, endpoint: Platform, obj_key: str) -> bool:
        """Returns whether the current user has access to a project"""
        if cls.__name__ not in ("Project", "Portfolio", "Application"):
            raise exceptions.UnsupportedOperation(f"Can't check access on {cls.__name__.lower()}s")
        try:
            cls.get_object(endpoint, key=obj_key)
        except AttributeError as e:
            raise exceptions.UnsupportedOperation(f"Can't check access on {cls.__name__.lower()}s") from e
        except (exceptions.NoPermissions, exceptions.ObjectNotFound):
            return False
        return True

    @classmethod
    def restore_access(cls, endpoint: Platform, obj_key: str, user: Optional[str] = None) -> bool:
        """Restores access to a project, portfolio or application for the given user"""
        if cls.__name__ not in ("Project", "Portfolio", "Application"):
            raise exceptions.UnsupportedOperation(f"Can't restore access of {cls.__name__.lower()}s")
        log.info("Restoring access to %s '%s' for user '%s'", cls.__name__, obj_key, user or endpoint.user())
        obj = cls.get_object(endpoint, key=obj_key)
        return obj.set_permissions([{"user": user or endpoint.user(), "permissions": ["admin", "user"]}])

    @classmethod
    def search_objects(cls, endpoint: Platform, params: ApiParams, threads: int = 8, api_version: int = 1) -> dict[str, SqObject]:
        """Runs a multi-threaded object search for searchable Sonar Objects"""
        api = cls.api_for(op.SEARCH, endpoint)
        returned_field = cls.SEARCH_RETURN_FIELD
        new_params: dict[str, Any] = (params or {}).copy()
        p_field = "pageIndex" if api_version == 2 else "p"
        ps_field = "pageSize" if api_version == 2 else "ps"
        if ps_field not in new_params:
            new_params[ps_field] = 500

        objects_list: dict[str, Any] = {}
        cname = cls.__name__.lower()
        data = json.loads(endpoint.get(api, {**new_params, p_field: 1}).text)
        nb_pages = sutil.nbr_pages(data)
        nb_objects = max(len(data[returned_field]), sutil.nbr_total_elements(data))
        msg = "Searching %d %ss, %d pages of %d elements, %d pages in parallel..."
        log.info(msg, nb_objects, cname, nb_pages, len(data[returned_field]), threads)
        if sutil.nbr_total_elements(data) > 0 and len(data[returned_field]) == 0:
            log.fatal(msg := f"Index on {cname} is corrupted, please reindex before using API")
            raise exceptions.SonarException(msg, errcodes.SONAR_INTERNAL_ERROR)

        objects_list |= _load(endpoint, cls, data[returned_field])

        with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix=f"{cname}Search") as executor:
            futures = [executor.submit(_get, endpoint, api, {**new_params, p_field: page}) for page in range(2, nb_pages + 1)]
            for future in concurrent.futures.as_completed(futures):
                try:
                    data = future.result(timeout=60)
                    objects_list |= _load(endpoint, cls, data[returned_field])
                except Exception as e:
                    log.error(f"Error {e} while searching {cname}.")
        return objects_list

    @classmethod
    def get_paginated(cls, endpoint: Platform, params: Optional[ApiParams] = None, threads: int = 8) -> dict[str, SqObject]:
        """Returns all pages of a paginated API"""
        cname = cls.__name__.lower()
        api_def = Api(cls, op.LIST, endpoint)
        page_field = api_def.page_field()
        max_ps = api_def.max_page_size()
        new_params = {"ps": max_ps, "pageSize": max_ps} | (params or {})
        api, _, new_params, returned_field = api_def.get_all(**new_params)

        objects_list: dict[str, cls] = {}
        data = json.loads(endpoint.get(api, new_params).text)
        nb_pages = sutil.nbr_pages(data)
        nb_objects = max(len(data[returned_field]), sutil.nbr_total_elements(data))
        msg = "Searching %d %ss, %d pages of %d elements, %d pages in parallel..."
        log.info(msg, nb_objects, cname, nb_pages, len(data[returned_field]), threads)
        if sutil.nbr_total_elements(data) > 0 and len(data[returned_field]) == 0:
            log.fatal(msg := f"Index on {cname} is corrupted, please reindex before using API")
            raise exceptions.SonarException(msg, errcodes.SONAR_INTERNAL_ERROR)

        objects_list |= _new_load(endpoint, cls, data[returned_field])

        with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix=f"{cname}Search") as executor:
            futures = [executor.submit(_get, endpoint, api, {**new_params, page_field: page}) for page in range(2, nb_pages + 1)]
            for future in concurrent.futures.as_completed(futures):
                try:
                    data = future.result(timeout=60)
                    objects_list |= _new_load(endpoint, cls, data[returned_field])
                except Exception as e:
                    log.error(f"Error {e} while searching {cname}.")
        return objects_list

    def reload(self, data: ApiPayload) -> object:
        """Loads a SonarQube API JSON payload in a SonarObject"""
        log.debug("%s: Reloading with %s", str(self), util.json_dump(data))
        self.sq_json = (self.sq_json or {}) | data
        return self

    def base_url(self, local: bool = True) -> str:
        """Returns the platform base URL"""
        return self.endpoint.local_url if local or self.endpoint.external_url in (None, "") else self.endpoint.external_url

    def get(
        self,
        api: str,
        params: Optional[ApiParams] = None,
        data: Optional[str] = None,
        mute: tuple[HTTPStatus, ...] = (),
        **kwargs: Any,
    ) -> requests.Response:
        """Executes and HTTP GET against the SonarQube platform

        :param api: API to invoke (eg api/issues/search)
        :param params: List of parameters to pass to the API
        :param mute: Tuple of HTTP Error codes to mute (ie not write an error log for), defaults to None.
                     Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :return: The request response
        """
        try:
            return self.endpoint.get(api=api, params=params, data=data, mute=mute, **kwargs)
        except exceptions.ObjectNotFound:
            self.__class__.CACHE.clear()
            raise

    def post(
        self,
        api: str,
        params: Optional[ApiParams] = None,
        mute: tuple[HTTPStatus, ...] = (),
        **kwargs: Any,
    ) -> requests.Response:
        """Executes and HTTP POST against the SonarQube platform

        :param str api: API to invoke (eg api/issues/search)
        :param ApiParams params: List of parameters to pass to the API
        :param mute: Tuple of HTTP Error codes to mute (ie not write an error log for), defaults to None.
                     Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :type mute: tuple, optional
        :return: The request response
        """
        try:
            return self.endpoint.post(api=api, params=params, mute=mute, **kwargs)
        except exceptions.ObjectNotFound:
            self.__class__.CACHE.clear()
            raise

    def patch(
        self,
        api: str,
        params: Optional[ApiParams] = None,
        mute: tuple[HTTPStatus, ...] = (),
        **kwargs: Any,
    ) -> requests.Response:
        """Executes and HTTP PATCH against the SonarQube platform

        :param str api: API to invoke (eg api/issues/search)
        :param ApiParams params: List of parameters to pass to the API
        :param mute: Tuple of HTTP Error codes to mute (ie not write an error log for), defaults to None.
                     Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :type mute: tuple, optional
        :return: The request response
        """
        try:
            return self.endpoint.patch(api=api, params=params, mute=mute, **kwargs)
        except exceptions.ObjectNotFound:
            self.__class__.CACHE.clear()
            raise

    def delete_object(self, **kwargs: Any) -> bool:
        """Deletes an object, returns whether the operation succeeded"""
        log.info("Deleting %s", str(self))
        try:
            api, method, params, _ = Api(self, op.DELETE).get_all(**kwargs)
            if method == "DELETE":
                ok = self.endpoint.delete(api=api, params=params).ok
            else:
                ok = self.endpoint.post(api=api, params=params).ok
            if ok:
                log.info("Removing from %s cache", str(self.__class__.__name__))
                self.__class__.CACHE.pop(self)
        except exceptions.ObjectNotFound:
            self.__class__.CACHE.clear()
            raise
        return ok

    def delete(self) -> bool:
        """Deletes an object, returns whether the operation succeeded"""
        log.info("Deleting %s (old method)", str(self))
        try:
            ok = self.post(api=self.__class__.API[op.DELETE], params=self.api_params(op.DELETE)).ok
            if ok:
                log.info("Removing from %s cache", str(self.__class__.__name__))
                self.__class__.CACHE.pop(self)
        except (AttributeError, KeyError) as e:
            raise exceptions.UnsupportedOperation(f"Can't delete {self.__class__.__name__.lower()}s") from e
        return ok

    def set_tags(self, tags: list[str]) -> bool:
        """Sets object tags
        :raises UnsupportedOperation: if can't set tags on such objects
        :return: Whether the operation was successful
        """
        if tags is None:
            return False
        log.info("Settings tags %s to %s", tags, str(self))
        try:
            api, _, params, _ = Api(self, op.SET_TAGS).get_all(project=self.key, issue=self.key, application=self.key, tags=util.list_to_csv(tags))
            if ok := self.post(api, params=params).ok:
                self._tags = sorted(tags)
        except (ValueError, AttributeError, KeyError) as e:
            raise exceptions.UnsupportedOperation(f"Can't set tags on {self.__class__.__name__.lower()}s") from e
        except exceptions.SonarException:
            return False
        else:
            return ok

    def get_tags(self, **kwargs: Any) -> list[str]:
        """Returns object tags"""
        try:
            api, _, params, ret = Api(self, op.GET_TAGS).get_all(component=self.key)
        except ValueError as e:
            raise exceptions.UnsupportedOperation(f"{self.__class__.__name__.lower()}s have no tags") from e
        if self._tags is None:
            self._tags = self.sq_json.get("tags", None)
        if not kwargs.get(c.USE_CACHE, True) or self._tags is None:
            try:
                self.reload(json.loads(self.get(api, params=params).text)[ret])
                self._tags = self.sq_json["tags"]
            except exceptions.SonarException:
                self._tags = []
        return self._tags


def _get(endpoint: Platform, api: str, params: ApiParams) -> requests.Response:
    """Returns a Sonar object from its key"""
    return json.loads(endpoint.get(api, params=params).text)


def _load(endpoint: Platform, object_class: Any, data: ObjectJsonRepr) -> dict[str, object]:
    """Loads any SonarQube object with the contents of an API payload"""
    key_field = object_class.SEARCH_KEY_FIELD
    if object_class.__name__ in ("Portfolio", "Group", "QualityProfile", "User", "Application", "Project", "Organization", "WebHook", "Rule"):
        return {obj[key_field]: object_class.load(endpoint=endpoint, data=obj) for obj in data}
    return {obj[key_field]: object_class(endpoint, obj[key_field], data=obj) for obj in data}


def _new_load(endpoint: Platform, object_class: Any, dataset: ObjectJsonRepr) -> dict[str, object]:
    """Loads any SonarQube object with the contents of an API payload"""
    try:
        load_method = object_class.load
    except AttributeError as e:
        raise exceptions.UnsupportedOperation(f"Can't load {object_class.__name__.lower()}s") from e
    obj_list = [load_method(endpoint=endpoint, data=data) for data in dataset]
    return {obj.key: obj for obj in obj_list}
