#
# sonar-tools
# Copyright (C) 2019-2024 Olivier Korach
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
from http import HTTPStatus
from queue import Queue
from threading import Thread
import requests
from requests import RequestException

import sonar.logging as log
from sonar.util import types, cache
from sonar import utilities, exceptions


class SqObject(object):
    """Abstraction of Sonar objects"""

    SEARCH_API = None
    CACHE = cache.Cache

    def __init__(self, endpoint: object, key: str) -> None:
        self.key = key  #: Object unique key (unique in its class)
        self.endpoint = endpoint  #: Reference to the SonarQube platform
        self.sq_json = None

    def __hash__(self) -> int:
        """Default UUID for SQ objects"""
        return hash((self.key, self.endpoint.url))

    def __eq__(self, another: object) -> bool:
        if type(self) == type(another):
            return hash(self) == hash(another)
        return NotImplemented

    @classmethod
    def get_search_api(cls, endpoint: object) -> Optional[str]:
        api = cls.SEARCH_API
        if endpoint.is_sonarcloud():
            try:
                api = cls.SEARCH_API_SC
            except AttributeError:
                api = cls.SEARCH_API
        return api

    @classmethod
    def clear_cache(cls, endpoint: Optional[object] = None) -> None:
        """
        Clear the cache of a given class
        :param endpoint Platform: Optional, clears only the cache fo rthis platfiorm if specified, clear all if not
        """
        log.info("Emptying cache of %s", str(cls))
        try:
            if not endpoint:
                cls.CACHE.clear()
            else:
                _ = [cls.CACHE.pop(o) for o in cls.CACHE.values().copy() if o.endpoint.url != endpoint.url]
        except AttributeError:
            pass

    def reload(self, data: types.ObjectJsonRepr) -> None:
        """Reload a Sonar object with its JSON representation"""
        if self.sq_json is None:
            self.sq_json = data
        else:
            self.sq_json.update(data)

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
        data: str = None,
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
        return self.endpoint.post(api=api, params=params, data=data, mute=mute, **kwargs)

    def patch(
        self,
        api: str,
        params: types.ApiParams = None,
        data: str = None,
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
        return self.endpoint.patch(api=api, params=params, data=data, mute=mute, **kwargs)


def __search_thread(queue: Queue) -> None:
    """Performs a search for a given object"""
    while not queue.empty():
        (endpoint, api, objects, key_field, returned_field, object_class, params, page) = queue.get()
        page_params = params.copy()
        page_params["p"] = page
        log.debug("Threaded search: API = %s params = %s", api, str(params))
        try:
            data = json.loads(endpoint.get(api, params=page_params).text)
            for obj in data[returned_field]:
                if object_class.__name__ in ("QualityProfile", "QualityGate", "Groups", "Portfolio", "Project"):
                    objects[obj[key_field]] = object_class.load(endpoint=endpoint, data=obj)
                else:
                    objects[obj[key_field]] = object_class(endpoint, obj[key_field], data=obj)
        except (ConnectionError, RequestException) as e:
            utilities.handle_error(e, f"searching {object_class.__name__}", catch_all=True)
        queue.task_done()


def search_objects(endpoint: object, object_class: any, params: types.ApiParams, threads: int = 8) -> dict[str, SqObject]:
    """Runs a multi-threaded object search for searchable Sonar Objects"""
    api = object_class.get_search_api(endpoint)
    key_field = object_class.SEARCH_KEY_FIELD
    returned_field = object_class.SEARCH_RETURN_FIELD

    new_params = {} if params is None else params.copy()
    if "ps" not in new_params:
        new_params["ps"] = 500
    new_params["p"] = 1
    objects_list = {}
    data = json.loads(endpoint.get(api, params=new_params).text)
    nb_pages = utilities.nbr_pages(data)
    nb_objects = max(len(data[returned_field]), utilities.nbr_total_elements(data))
    log.debug("Loading %d %ss... from %s", nb_objects, object_class.__name__, data)
    for obj in data[returned_field]:
        if object_class.__name__ in ("Portfolio", "Group", "QualityProfile", "User", "Application", "Project", "Organization"):
            objects_list[obj[key_field]] = object_class.load(endpoint=endpoint, data=obj)
        else:
            objects_list[obj[key_field]] = object_class(endpoint, obj[key_field], data=obj)
    if nb_pages == 1:
        # If everything is returned on the 1st page, no multi-threading needed
        return objects_list
    q = Queue(maxsize=0)
    for page in range(2, nb_pages + 1):
        q.put((endpoint, api, objects_list, key_field, returned_field, object_class, new_params, page))
    for i in range(threads):
        log.debug("Starting %s search thread %d", object_class.__name__, i)
        worker = Thread(target=__search_thread, args=[q])
        worker.setDaemon(True)
        worker.setName(f"Search{i}")
        worker.start()
    q.join()
    return objects_list


def delete_object(object: SqObject, api: str, params: types.ApiParams, class_cache: object) -> bool:
    """Deletes a Sonar object"""
    try:
        log.info("Deleting %s", str(object))
        r = object.post(api, params=params, mute=(HTTPStatus.NOT_FOUND,))
        class_cache.pop(object)
        log.info("Successfully deleted %s", str(object))
        return r.ok
    except (ConnectionError, RequestException) as e:
        utilities.handle_error(e, f"deleting {str(object)}", catch_http_errors=(HTTPStatus.NOT_FOUND,))
        class_cache.pop(object)
        raise exceptions.ObjectNotFound(object.key, f"{str(object)} not found for delete")
