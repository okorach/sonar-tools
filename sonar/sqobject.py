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
from requests.exceptions import HTTPError

import sonar.logging as log
from sonar.util import types
from sonar import utilities, exceptions


class SqObject:
    """Abstraction of Sonar objects"""

    SEARCH_API = None

    def __init__(self, endpoint: object, key: str) -> None:
        self.key = key  #: Object unique key (unique in its class)
        self.endpoint = endpoint  #: Reference to the SonarQube platform
        self._json = None

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
    def empty_cache(cls) -> None:
        """Empties the cache of objects of the given class"""
        log.info("Emptying cache of %s", str(cls))
        try:
            cls._OBJECTS = {}
        except AttributeError:
            pass

    def uuid(self) -> str:
        """Returns object unique ID in its class"""
        return uuid(self.key, self.endpoint.url)

    def reload(self, data: types.ObjectJsonRepr) -> None:
        """Reload a Sonar object with its JSON representation"""
        if self._json is None:
            self._json = data
        else:
            self._json.update(data)

    def get(self, api: str, params: types.ApiParams = None, exit_on_error: bool = False, mute: tuple[HTTPStatus] = ()) -> requests.Response:
        """Executes and HTTP GET against the SonarQube platform

        :param api: API to invoke (eg api/issues/search)
        :param params: List of parameters to pass to the API
        :param exit_on_error: When to fail fast and exit if the HTTP status code is not 2XX, defaults to True
        :param mute: Tuple of HTTP Error codes to mute (ie not write an error log for), defaults to None.
                     Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :return: The request response
        """
        return self.endpoint.get(api=api, params=params, exit_on_error=exit_on_error, mute=mute)

    def post(self, api: str, params: types.ApiParams = None, exit_on_error: bool = False, mute: tuple[HTTPStatus] = ()) -> requests.Response:
        """Executes and HTTP POST against the SonarQube platform

        :param str api: API to invoke (eg api/issues/search)
        :param ApiParams params: List of parameters to pass to the API
        :param bool exit_on_error: When to fail fast and exit if the HTTP status code is not 2XX, defaults to True
        :param mute: Tuple of HTTP Error codes to mute (ie not write an error log for), defaults to None.
                     Typically, Error 404 Not found may be expected sometimes so this can avoid logging an error for 404
        :type mute: tuple, optional
        :return: The request response
        """
        return self.endpoint.post(api=api, params=params, exit_on_error=exit_on_error, mute=mute)


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
        except HTTPError as e:
            log.critical("HTTP error while searching %s, search skipped: %s", object_class.__name__, str(e))
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
    for obj in data[returned_field]:
        if object_class.__name__ in ("Portfolio", "Group", "QualityProfile", "User", "Application", "Project"):
            objects_list[obj[key_field]] = object_class.load(endpoint=endpoint, data=obj)
        else:
            objects_list[obj[key_field]] = object_class(endpoint, obj[key_field], data=obj)
    nb_pages = utilities.nbr_pages(data)
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


def delete_object(object: SqObject, api: str, params: types.ApiParams, map: dict[str, SqObject]) -> bool:
    """Deletes a Sonar object"""
    try:
        log.info("Deleting %s", str(object))
        r = object.post(api, params=params, mute=(HTTPStatus.NOT_FOUND,))
        map.pop(object.uuid(), None)
        log.info("Successfully deleted %s", str(object))
        return r.ok
    except HTTPError as e:
        if e.response.status_code == HTTPStatus.NOT_FOUND:
            map.pop(object.uuid(), None)
            raise exceptions.ObjectNotFound(object.key, f"{str(object)} not found for delete")
        raise


def uuid(key: str, url: str) -> str:
    """Returns a SonarQube object uuid"""
    return f"{key}@{url}"
