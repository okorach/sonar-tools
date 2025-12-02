#!/usr/bin/env python3
#
# sonar-tools tests
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

"""DevOps platforms tests"""

import pytest
import utilities as tutil
from sonar import devops, exceptions
import sonar.util.constants as c

GH_KEY = "GitHub okorach"
ADO_KEY = "ADO"
GL_KEY = "gitlab.com"
BBS_KEY = "Bitbucket Server 1"
BBC_KEY = "Bitbucket Cloud 1"


def test_get_list() -> None:
    """test_get_list"""
    if tutil.SQ.is_sonarcloud():
        with pytest.raises(exceptions.UnsupportedOperation):
            devops.get_list(endpoint=tutil.SQ)
        return
    plt_list = devops.get_list(endpoint=tutil.SQ)
    assert len(plt_list) >= 3
    for k in GH_KEY, ADO_KEY, GL_KEY:
        assert k in plt_list


def test_get_object_gh() -> None:
    """test_get_object_gh"""
    plt = devops.get_object(endpoint=tutil.SQ, key=GH_KEY)
    assert plt.url == "https://api.github.com"
    if tutil.SQ.version() >= (10, 0, 0):
        assert plt._specific["appId"] == "946159"
    else:
        assert plt._specific["appId"] == "1096234"
    assert str(plt) == f"devops platform '{GH_KEY}'"


def test_get_object_gh_refresh() -> None:
    """test_get_object_gh"""
    plt = devops.get_object(endpoint=tutil.SQ, key=GH_KEY)
    assert plt.refresh()


def test_get_object_ado() -> None:
    """test_get_object_ado"""
    plt = devops.get_object(endpoint=tutil.SQ, key=ADO_KEY)
    assert plt.url == "https://dev.azure.com/olivierkorach"
    assert str(plt) == f"devops platform '{ADO_KEY}'"


def test_get_object_gl() -> None:
    """test_get_object_gl"""
    plt = devops.get_object(endpoint=tutil.SQ, key=GL_KEY)
    assert plt.url == "https://gitlab.com/api/v4"
    assert str(plt) == f"devops platform '{GL_KEY}'"


def test_count() -> None:
    """Verify count works"""
    assert devops.count(tutil.SQ, "azure") == 1
    assert devops.count(tutil.SQ, "gitlab") == 1
    assert devops.count(tutil.SQ, "bitbucket") == 1
    assert devops.count(tutil.SQ, "bitbucketcloud") == 1
    # TODO: Find out if normal than multiple devops platforms allowed on CE
    nb_gh = 2 if tutil.SQ.edition() in (c.EE, c.DCE) else 1
    assert devops.count(tutil.SQ, "github") == nb_gh
    assert devops.count(tutil.SQ) == nb_gh + 4


def test_exists() -> None:
    """test_exists"""
    for k in GH_KEY, GL_KEY, ADO_KEY:
        assert devops.exists(endpoint=tutil.SQ, key=k)
    for k in "foo", "bar":
        assert not devops.exists(endpoint=tutil.SQ, key=k)


def test_devops_type() -> None:
    """test_devops_type"""
    assert devops.devops_type(endpoint=tutil.SQ, key=GH_KEY) == "github"
    assert devops.devops_type(endpoint=tutil.SQ, key=GL_KEY) == "gitlab"
    assert devops.devops_type(endpoint=tutil.SQ, key=ADO_KEY) == "azure"
    with pytest.raises(exceptions.ObjectNotFound):
        devops.devops_type(endpoint=tutil.SQ, key="foobar")


def test_import_config_1() -> None:
    """test_import_config_1"""
    assert devops.import_config(endpoint=tutil.SQ, config_data={}) == 0


def test_import_config_2() -> None:
    """test_import_config_2"""
    dop = {
        "devopsIntegration": [
            {"key": "ADO2", "type": "azure", "url": "https://dev.azure.com/olivierkorach"},
            {"key": "GH2", "type": "github", "url": "https://api.github.com", "clientId": "Iv23ligl0iLhGRRvwFGO", "appId": 946159},
            {"key": "GL2", "type": "gitlab", "url": "https://gitlab.com/api/v4"},
        ]
    }
    if tutil.SQ.is_sonarcloud():
        with pytest.raises(exceptions.UnsupportedOperation):
            devops.import_config(endpoint=tutil.SQ, config_data=dop)
        return
    assert devops.import_config(endpoint=tutil.SQ, config_data=dop) == 3
    assert devops.exists(endpoint=tutil.SQ, key="ADO2")
    assert devops.exists(endpoint=tutil.SQ, key="GH2")
    assert devops.exists(endpoint=tutil.SQ, key="GL2")
    for key in "ADO2", "GH2", "GL2":
        obj = devops.get_object(endpoint=tutil.SQ, key=key)
        obj.delete()
        assert devops.exists(endpoint=tutil.SQ, key=key) is False
