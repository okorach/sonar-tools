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

from typing import Optional
import json
from collections.abc import Generator
from http import HTTPStatus
import concurrent.futures
import requests
from requests import RequestException

import sonar.logging as log
from sonar.util import types, cache
from sonar.util import constants as c
from sonar import utilities, exceptions


class SqObject(object):
    """Abstraction of Sonar objects"""

    CACHE = cache.Cache
    API = {c.SEARCH: None}

    def __init__(self, endpoint: object, key: str) -> None:
        self.key = key  #: Object unique key (unique in its class)
        self.endpoint = endpoint  #: Reference to the SonarQube platform
        self.concerned_object = None
        self._tags = None
        self.sq_json = {}

    def __hash__(self) -> int:
        """Default UUID for SQ objects"""
        return hash((self.key, self.base_url()))

    def __eq__(self, another: object) -> bool:
        if type(self) is type(another):
            return hash(self) == hash(another)
        return NotImplemented

    @classmethod
    def api_for(cls, op: str, endpoint: object) -> Optional[str]:
        """Returns the API to use for a particular operation.
        This function must be overloaded for classes that need specific treatment. e.g. API V1 or V2
        depending on SonarQube version, different API for SonarQube Cloud

        :param op: The desired API operation
        :param endpoint: The SQS or SQC to invoke the API
        :return: The API to use for the operation, or None if not defined
        """
        return cls.API[op] if op in cls.API else cls.API[c.LIST]

    @classmethod
    def clear_cache(cls, endpoint: Optional[object] = None) -> None:
        """Clears the cache of a given class

        :param endpoint: Optional, clears only the cache fo rthis platfiorm if specified, clear all if not
        """
        log.info("Emptying cache of %s", str(cls))
        try:
            if not endpoint:
                cls.CACHE.clear()
            else:
                _ = [cls.CACHE.pop(o) for o in cls.CACHE.values().copy() if o.base_url() != endpoint.local_url]
        except AttributeError:
            pass

    def reload(self, data: types.ObjectJsonRepr) -> None:
        """Reload a Sonar object with its JSON representation"""
        if self.sq_json is None:
            self.sq_json = data
        else:
            self.sq_json.update(data)

    def base_url(self, local: bool = True) -> str:
        """Returns the platform base URL"""
        return self.endpoint.local_url if local or self.endpoint.external_url in (None, "") else self.endpoint.external_url

    def get(
        self,
        api: str,
        params: types.ApiParams = None,
        data: str = None,
        mute: tuple[HTTPStatus] = (),
        **kwargs,
    ) -> requests.Response:
        """Executes and HTTP GET against the SonarQube platform

        :param api: API to invoke (eg api/issues/search)
        :param params: List of parameters to pass to the API
        :param mute: Tuple of HTTP Error codes to mute (ie not write an error log for), defaults to None.
                     Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :return: The request response
        """
        return self.endpoint.get(api=api, params=params, data=data, mute=mute, **kwargs)

    def post(
        self,
        api: str,
        params: types.ApiParams = None,
        mute: tuple[HTTPStatus] = (),
        **kwargs,
    ) -> requests.Response:
        """Executes and HTTP POST against the SonarQube platform

        :param str api: API to invoke (eg api/issues/search)
        :param ApiParams params: List of parameters to pass to the API
        :param mute: Tuple of HTTP Error codes to mute (ie not write an error log for), defaults to None.
                     Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :type mute: tuple, optional
        :return: The request response
        """
        return self.endpoint.post(api=api, params=params, mute=mute, **kwargs)

    def patch(
        self,
        api: str,
        params: types.ApiParams = None,
        mute: tuple[HTTPStatus] = (),
        **kwargs,
    ) -> requests.Response:
        """Executes and HTTP PATCH against the SonarQube platform

        :param str api: API to invoke (eg api/issues/search)
        :param ApiParams params: List of parameters to pass to the API
        :param mute: Tuple of HTTP Error codes to mute (ie not write an error log for), defaults to None.
                     Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :type mute: tuple, optional
        :return: The request response
        """
        return self.endpoint.patch(api=api, params=params, mute=mute, **kwargs)

    def delete(self) -> bool:
        """Deletes an object, returns whether the operation succeeded"""
        log.info("Deleting %s", str(self))
        try:
            ok = self.post(api=self.__class__.API[c.DELETE], params=self.api_params(c.DELETE)).ok
            if ok:
                log.info("Removing from %s cache", str(self.__class__.__name__))
                self.__class__.CACHE.pop(self)
        except (ConnectionError, RequestException) as e:
            utilities.handle_error(e, f"deleting {str(self)}", catch_http_statuses=(HTTPStatus.NOT_FOUND,))
            raise exceptions.ObjectNotFound(self.key, f"{str(self)} not found")
        except (AttributeError, KeyError):
            raise exceptions.UnsupportedOperation(f"Can't delete {self.__class__.__name__.lower()}s")
        return ok

    def set_tags(self, tags: list[str]) -> bool:
        """Sets object tags
        :raises exceptions.UnsupportedOperation: if can't set tags on such objects
        :return: Whether the operation was successful
        """
        if tags is None:
            return False
        my_tags = utilities.list_to_csv(tags) if isinstance(tags, list) else utilities.csv_normalize(tags)
        try:
            r = self.post(self.__class__.API[c.SET_TAGS], params={**self.api_params(c.SET_TAGS), "tags": my_tags})
            if r.ok:
                self._tags = sorted(utilities.csv_to_list(my_tags))
        except (ConnectionError, RequestException) as e:
            utilities.handle_error(e, f"setting tags of {str(self)}", catch_http_statuses=(HTTPStatus.BAD_REQUEST,))
            return False
        except (AttributeError, KeyError):
            raise exceptions.UnsupportedOperation(f"Can't set tags on {self.__class__.__name__.lower()}s")
        return r.ok

    def get_tags(self, **kwargs) -> list[str]:
        """Returns object tags"""
        try:
            api = self.__class__.API[c.GET_TAGS]
        except (AttributeError, KeyError):
            raise exceptions.UnsupportedOperation(f"{self.__class__.__name__.lower()}s have no tags")
        if self._tags is None:
            self._tags = self.sq_json.get("tags", None)
        if not kwargs.get(c.USE_CACHE, True) or self._tags is None:
            try:
                data = json.loads(self.get(api, params=self.get_tags_params()).text)
                self.sq_json.update(data["component"])
                self._tags = self.sq_json["tags"]
            except (ConnectionError, RequestException):
                self._tags = []
        return self._tags


def __get(endpoint: object, api: str, params: types.ApiParams) -> requests.Response:
    """Returns a Sonar object from its key"""
    return json.loads(endpoint.get(api, params=params).text)


def __load(endpoint: object, object_class: any, data: types.ObjectJsonRepr) -> dict[str, object]:
    key_field = object_class.SEARCH_KEY_FIELD
    if object_class.__name__ in ("Portfolio", "Group", "QualityProfile", "User", "Application", "Project", "Organization"):
        return {obj[key_field]: object_class.load(endpoint=endpoint, data=obj) for obj in data}
    else:
        return {obj[key_field]: object_class(endpoint, obj[key_field], data=obj) for obj in data}


def search_objects(endpoint: object, object_class: any, params: types.ApiParams, threads: int = 8, api_version: int = 1) -> dict[str, SqObject]:
    """Runs a multi-threaded object search for searchable Sonar Objects"""
    api = object_class.api_for(c.SEARCH, endpoint)
    returned_field = object_class.SEARCH_RETURN_FIELD
    new_params = {} if params is None else params.copy()
    p_field = "pageIndex" if api_version == 2 else "p"
    ps_field = "pageSize" if api_version == 2 else "ps"
    if ps_field not in new_params:
        new_params[ps_field] = 500

    objects_list = {}
    cname = object_class.__name__.lower()
    data = __get(endpoint, api, {**new_params, p_field: 1})
    nb_pages = utilities.nbr_pages(data, api_version)
    nb_objects = max(len(data[returned_field]), utilities.nbr_total_elements(data, api_version))
    log.info(
        "Searching %d %ss, %d pages of %d elements, %d pages in parallel...",
        nb_objects,
        cname,
        nb_pages,
        len(data[returned_field]),
        threads,
    )
    if utilities.nbr_total_elements(data) > 0 and len(data[returned_field]) == 0:
        log.fatal(msg := f"Index on {cname} is corrupted, please reindex before using API")
        raise exceptions.SonarException(msg)

    objects_list |= __load(endpoint, object_class, data[returned_field])

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads, thread_name_prefix=f"{cname}Search") as executor:
        futures = [executor.submit(__get, endpoint, api, {**new_params, p_field: page}) for page in range(2, nb_pages + 1)]
        for future in concurrent.futures.as_completed(futures):
            try:
                data = future.result(timeout=60)
                objects_list |= __load(endpoint, object_class, data[returned_field])
            except Exception as e:
                log.error(f"Error {e} while searching {cname}.")
    return objects_list
