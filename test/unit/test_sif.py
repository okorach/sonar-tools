#!/usr/bin/env python3
#
# sonar-tools tests
# Copyright (C) 2025 Olivier Korach
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

"""Tests for Sif class and subclasses"""

import json
import datetime
import pytest
from unittest.mock import Mock, patch

import utilities as tutil
from sonar import sif
from sonar.dce import app_nodes, search_nodes, nodes
import sonar.util.constants as c
from sonar.audit.problem import Problem


class TestSifBasic:
    """Test basic Sif class functionality"""

    def test_sif_creation_with_valid_json(self):
        """Test Sif creation with valid JSON"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        sif_obj = sif.Sif(json_sif)
        assert sif_obj.json == json_sif
        assert sif_obj.concerned_object is None
        assert sif_obj._url is None

    def test_sif_creation_with_concerned_object(self):
        """Test Sif creation with concerned object"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        mock_object = Mock()
        mock_object.external_url = "https://test.sonarqube.com"
        
        sif_obj = sif.Sif(json_sif, concerned_object=mock_object)
        assert sif_obj.concerned_object == mock_object

    def test_sif_creation_with_invalid_json(self):
        """Test Sif creation with invalid JSON raises exception"""
        invalid_json = {"not": "a", "sif": "file"}
        
        with pytest.raises(sif.NotSystemInfo) as exc_info:
            sif.Sif(invalid_json)
        
        assert "JSON is not a system info nor a support info" in str(exc_info.value)

    def test_sif_str_representation(self):
        """Test Sif string representation"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        sif_obj = sif.Sif(json_sif)
        assert str(sif_obj) == "None"
        
        mock_object = Mock()
        mock_object.external_url = "https://test.sonarqube.com"
        sif_obj = sif.Sif(json_sif, concerned_object=mock_object)
        assert str(sif_obj) == str(mock_object)

    def test_sif_url_with_concerned_object(self):
        """Test Sif url() method with concerned object"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        mock_object = Mock()
        mock_object.external_url = "https://test.sonarqube.com"
        
        sif_obj = sif.Sif(json_sif, concerned_object=mock_object)
        assert sif_obj.url() == "https://test.sonarqube.com"

    def test_sif_url_without_concerned_object(self):
        """Test Sif url() method without concerned object"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        sif_obj = sif.Sif(json_sif)
        # Should return empty string as no serverBaseURL in settings
        assert sif_obj.url() == ""

    def test_sif_url_with_server_base_url(self):
        """Test Sif url() method with serverBaseURL in settings"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Add serverBaseURL to settings
        json_sif["Settings"]["sonar.core.serverBaseURL"] = "https://custom.sonarqube.com"
        
        sif_obj = sif.Sif(json_sif)
        assert sif_obj.url() == "https://custom.sonarqube.com"


class TestSifEdition:
    """Test Sif edition detection"""

    def test_sif_edition_from_stats(self):
        """Test Sif edition detection from Statistics section"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        sif_obj = sif.Sif(json_sif)
        assert sif_obj.edition() == c.EE

    def test_sif_edition_from_system(self):
        """Test Sif edition detection from System section"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Remove from Statistics, add to System
        json_sif["Statistics"].pop("Edition")
        json_sif["System"]["Edition"] = "Enterprise Edition"
        
        sif_obj = sif.Sif(json_sif)
        assert sif_obj.edition() == c.EE

    def test_sif_edition_from_license(self):
        """Test Sif edition detection from License section"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Remove from other sections, add to License
        json_sif["Statistics"].pop("Edition")
        json_sif["System"].pop("Edition")
        json_sif["License"]["edition"] = "Enterprise Edition"
        
        sif_obj = sif.Sif(json_sif)
        assert sif_obj.edition() == c.EE

    def test_sif_edition_dce_detection(self):
        """Test Sif DCE edition detection from Application Nodes presence"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        sif_obj = sif.Sif(json_sif)
        assert sif_obj.edition() == c.DCE

    def test_sif_edition_unknown(self):
        """Test Sif edition detection when no edition found"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Remove all edition information
        json_sif["Statistics"].pop("Edition")
        json_sif["System"].pop("Edition")
        json_sif["License"].pop("edition")
        
        sif_obj = sif.Sif(json_sif)
        assert sif_obj.edition() is None

    def test_sif_edition_normalization(self):
        """Test Sif edition normalization for old SIFs"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Test with old format
        json_sif["Statistics"]["Edition"] = "Enterprise Edition"
        
        sif_obj = sif.Sif(json_sif)
        assert sif_obj.edition() == c.EE


class TestSifDatabase:
    """Test Sif database detection"""

    def test_sif_database_old_version(self):
        """Test Sif database detection for old versions"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Mock version to be old
        with patch.object(sif.Sif, 'version', return_value=(9, 6, 0)):
            sif_obj = sif.Sif(json_sif)
            assert sif_obj.database() == "PostgreSQL"

    def test_sif_database_new_version(self):
        """Test Sif database detection for new versions"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Mock version to be new
        with patch.object(sif.Sif, 'version', return_value=(9, 7, 0)):
            sif_obj = sif.Sif(json_sif)
            assert sif_obj.database() == "PostgreSQL"


class TestSifPlugins:
    """Test Sif plugins functionality"""

    def test_sif_plugins(self):
        """Test Sif plugins retrieval"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        sif_obj = sif.Sif(json_sif)
        plugins = sif_obj.plugins()
        assert isinstance(plugins, dict)
        assert len(plugins) == 0  # No plugins in test SIF


class TestSifAudit:
    """Test Sif audit functionality"""

    def test_sif_audit_ce_edition(self):
        """Test Sif audit for CE edition"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Mock edition to be CE
        with patch.object(sif.Sif, 'edition', return_value=c.CE):
            sif_obj = sif.Sif(json_sif)
            problems = sif_obj.audit({})
            assert isinstance(problems, list)

    def test_sif_audit_dce_edition(self):
        """Test Sif audit for DCE edition"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        sif_obj = sif.Sif(json_sif)
        problems = sif_obj.audit({})
        assert isinstance(problems, list)

    def test_sif_audit_branch_use(self):
        """Test Sif audit for branch usage"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        sif_obj = sif.Sif(json_sif)
        
        # Test with branch usage enabled
        json_sif["Statistics"]["usingBranches"] = True
        problems = sif_obj._Sif__audit_branch_use()
        assert problems == []
        
        # Test with branch usage disabled
        json_sif["Statistics"]["usingBranches"] = False
        problems = sif_obj._Sif__audit_branch_use()
        assert len(problems) == 1
        assert isinstance(problems[0], Problem)

    def test_sif_audit_branch_use_ce(self):
        """Test Sif audit for branch usage on CE edition"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Mock edition to be CE
        with patch.object(sif.Sif, 'edition', return_value=c.CE):
            sif_obj = sif.Sif(json_sif)
            problems = sif_obj._Sif__audit_branch_use()
            assert problems == []

    def test_sif_audit_branch_use_missing_info(self):
        """Test Sif audit for branch usage when info is missing"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Remove branch usage information
        json_sif["Statistics"].pop("usingBranches", None)
        
        sif_obj = sif.Sif(json_sif)
        problems = sif_obj._Sif__audit_branch_use()
        assert problems == []


class TestDceNode:
    """Test DCE Node base class"""

    def test_dce_node_creation(self):
        """Test DCE Node creation"""
        node_data = {"Name": "test-node", "Health": "GREEN"}
        mock_sif = Mock()
        
        node = nodes.DceNode(node_data, mock_sif)
        assert node.json == node_data
        assert node.sif == mock_sif

    def test_dce_node_audit(self):
        """Test DCE Node audit method"""
        node_data = {"Name": "test-node", "Health": "GREEN"}
        mock_sif = Mock()
        
        node = nodes.DceNode(node_data, mock_sif)
        problems = node.audit({})
        assert problems == []


class TestAppNode:
    """Test AppNode class"""

    def test_app_node_creation(self):
        """Test AppNode creation"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        app_node_data = json_sif["Application Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = app_nodes.AppNode(app_node_data, sif_obj)
        assert node.json == app_node_data
        assert node.sif == sif_obj

    def test_app_node_str_representation(self):
        """Test AppNode string representation"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        app_node_data = json_sif["Application Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = app_nodes.AppNode(app_node_data, sif_obj)
        assert str(node).startswith("App Node")

    def test_app_node_plugins(self):
        """Test AppNode plugins retrieval"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        app_node_data = json_sif["Application Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = app_nodes.AppNode(app_node_data, sif_obj)
        plugins = node.plugins()
        assert isinstance(plugins, dict)
        assert len(plugins) == 6

    def test_app_node_health(self):
        """Test AppNode health retrieval"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        app_node_data = json_sif["Application Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = app_nodes.AppNode(app_node_data, sif_obj)
        assert node.health() == "GREEN"

    def test_app_node_health_default(self):
        """Test AppNode health default when not available"""
        app_node_data = {"Name": "test-node"}
        mock_sif = Mock()
        
        node = app_nodes.AppNode(app_node_data, mock_sif)
        assert node.health() == nodes.HEALTH_RED

    def test_app_node_node_type(self):
        """Test AppNode node type"""
        app_node_data = {"Name": "test-node"}
        mock_sif = Mock()
        
        node = app_nodes.AppNode(app_node_data, mock_sif)
        assert node.node_type() == "APPLICATION"

    def test_app_node_start_time(self):
        """Test AppNode start time"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        app_node_data = json_sif["Application Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = app_nodes.AppNode(app_node_data, sif_obj)
        start_time = node.start_time()
        assert isinstance(start_time, datetime.datetime)

    def test_app_node_version(self):
        """Test AppNode version"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        app_node_data = json_sif["Application Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = app_nodes.AppNode(app_node_data, sif_obj)
        version = node.version()
        assert version == (9, 9, 0)

    def test_app_node_version_missing(self):
        """Test AppNode version when missing"""
        app_node_data = {"Name": "test-node"}
        mock_sif = Mock()
        
        node = app_nodes.AppNode(app_node_data, mock_sif)
        version = node.version()
        assert version is None

    def test_app_node_edition(self):
        """Test AppNode edition"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        app_node_data = json_sif["Application Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = app_nodes.AppNode(app_node_data, sif_obj)
        edition = node.edition()
        assert edition == c.DCE

    def test_app_node_name(self):
        """Test AppNode name"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        app_node_data = json_sif["Application Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = app_nodes.AppNode(app_node_data, sif_obj)
        name = node.name()
        assert name.startswith("app-node")

    def test_app_node_audit(self):
        """Test AppNode audit"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        app_node_data = json_sif["Application Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = app_nodes.AppNode(app_node_data, sif_obj)
        problems = node.audit({})
        assert isinstance(problems, list)

    def test_app_node_audit_health_green(self):
        """Test AppNode audit with green health"""
        app_node_data = {"Name": "test-node", "Health": "GREEN"}
        mock_sif = Mock()
        
        node = app_nodes.AppNode(app_node_data, mock_sif)
        problems = node._AppNode__audit_health()
        assert problems == []

    def test_app_node_audit_health_not_green(self):
        """Test AppNode audit with non-green health"""
        app_node_data = {"Name": "test-node", "Health": "RED"}
        mock_sif = Mock()
        
        node = app_nodes.AppNode(app_node_data, mock_sif)
        problems = node._AppNode__audit_health()
        assert len(problems) == 1
        assert isinstance(problems[0], Problem)

    def test_app_node_audit_official_missing(self):
        """Test AppNode audit with missing official distribution info"""
        app_node_data = {"Name": "test-node"}
        mock_sif = Mock()
        
        node = app_nodes.AppNode(app_node_data, mock_sif)
        problems = node._AppNode__audit_official()
        assert problems == []

    def test_app_node_audit_official_true(self):
        """Test AppNode audit with official distribution"""
        app_node_data = {"Name": "test-node", "System": {"Official Distribution": True}}
        mock_sif = Mock()
        
        node = app_nodes.AppNode(app_node_data, mock_sif)
        problems = node._AppNode__audit_official()
        assert problems == []

    def test_app_node_audit_official_false(self):
        """Test AppNode audit with unofficial distribution"""
        app_node_data = {"Name": "test-node", "System": {"Official Distribution": False}}
        mock_sif = Mock()
        
        node = app_nodes.AppNode(app_node_data, mock_sif)
        problems = node._AppNode__audit_official()
        assert len(problems) == 1
        assert isinstance(problems[0], Problem)


class TestSearchNode:
    """Test SearchNode class"""

    def test_search_node_creation(self):
        """Test SearchNode creation"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        search_node_data = json_sif["Search Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = search_nodes.SearchNode(search_node_data, sif_obj)
        assert node.json == search_node_data
        assert node.sif == sif_obj

    def test_search_node_str_representation(self):
        """Test SearchNode string representation"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        search_node_data = json_sif["Search Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = search_nodes.SearchNode(search_node_data, sif_obj)
        assert str(node).startswith("Search Node")

    def test_search_node_store_size(self):
        """Test SearchNode store size"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        search_node_data = json_sif["Search Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = search_nodes.SearchNode(search_node_data, sif_obj)
        store_size = node.store_size()
        assert isinstance(store_size, int)
        assert 20000 < store_size < 25000

    def test_search_node_name(self):
        """Test SearchNode name"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        search_node_data = json_sif["Search Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = search_nodes.SearchNode(search_node_data, sif_obj)
        name = node.name()
        assert name.startswith("search-node")

    def test_search_node_node_type(self):
        """Test SearchNode node type"""
        search_node_data = {"Name": "test-search-node"}
        mock_sif = Mock()
        
        node = search_nodes.SearchNode(search_node_data, mock_sif)
        assert node.node_type() == "SEARCH"

    def test_search_node_audit(self):
        """Test SearchNode audit"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        search_node_data = json_sif["Search Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = search_nodes.SearchNode(search_node_data, sif_obj)
        problems = node.audit({})
        assert isinstance(problems, list)

    def test_search_node_max_heap(self):
        """Test SearchNode max heap"""
        with open(f"{tutil.FILES_ROOT}/sif.dce.1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        search_node_data = json_sif["Search Nodes"][0]
        sif_obj = sif.Sif(json_sif)
        
        node = search_nodes.SearchNode(search_node_data, sif_obj)
        max_heap = node.max_heap()
        assert isinstance(max_heap, int)

    def test_search_node_max_heap_missing(self):
        """Test SearchNode max heap when missing"""
        search_node_data = {"Name": "test-search-node"}
        mock_sif = Mock()
        mock_sif.edition.return_value = c.DCE
        mock_sif.version.return_value = (9, 0, 0)
        
        node = search_nodes.SearchNode(search_node_data, mock_sif)
        max_heap = node.max_heap()
        assert max_heap is None

    def test_search_node_audit_store_size_empty(self):
        """Test SearchNode audit with empty store size"""
        search_node_data = {
            "Name": "test-search-node",
            "Search State": {"Store Size": "0 MB"}
        }
        mock_sif = Mock()
        
        node = search_nodes.SearchNode(search_node_data, mock_sif)
        problems = node._SearchNode__audit_store_size()
        assert len(problems) == 1
        assert isinstance(problems[0], Problem)

    def test_search_node_audit_available_disk(self):
        """Test SearchNode audit available disk"""
        search_node_data = {
            "Name": "test-search-node",
            "Search State": {
                "Store Size": "1000 MB",
                "Disk Available": "5000 MB"
            }
        }
        mock_sif = Mock()
        
        node = search_nodes.SearchNode(search_node_data, mock_sif)
        problems = node._SearchNode__audit_available_disk()
        assert isinstance(problems, list)


class TestAppNodesAudit:
    """Test AppNodes audit functionality"""

    def test_app_nodes_audit_single_node(self):
        """Test AppNodes audit with single node (should trigger HA warning)"""
        app_nodes_data = [{"Name": "single-node", "Health": "GREEN"}]
        mock_sif = Mock()
        
        problems = app_nodes.audit(app_nodes_data, mock_sif, {})
        assert len(problems) == 1
        assert isinstance(problems[0], Problem)

    def test_app_nodes_audit_multiple_nodes(self):
        """Test AppNodes audit with multiple nodes"""
        app_nodes_data = [
            {"Name": "node1", "Health": "GREEN"},
            {"Name": "node2", "Health": "GREEN"}
        ]
        mock_sif = Mock()
        
        problems = app_nodes.audit(app_nodes_data, mock_sif, {})
        assert isinstance(problems, list)

    def test_app_nodes_audit_different_versions(self):
        """Test AppNodes audit with different versions"""
        app_nodes_data = [
            {"Name": "node1", "Health": "GREEN", "System": {"Version": "9.9.0"}},
            {"Name": "node2", "Health": "GREEN", "System": {"Version": "9.8.0"}}
        ]
        mock_sif = Mock()
        
        problems = app_nodes.audit(app_nodes_data, mock_sif, {})
        assert len(problems) >= 1
        assert isinstance(problems[0], Problem)

    def test_app_nodes_audit_different_plugins(self):
        """Test AppNodes audit with different plugins"""
        app_nodes_data = [
            {"Name": "node1", "Health": "GREEN", "Plugins": {"plugin1": "1.0"}},
            {"Name": "node2", "Health": "GREEN", "Plugins": {"plugin2": "1.0"}}
        ]
        mock_sif = Mock()
        
        problems = app_nodes.audit(app_nodes_data, mock_sif, {})
        assert len(problems) >= 1
        assert isinstance(problems[0], Problem)


class TestSearchNodesAudit:
    """Test SearchNodes audit functionality"""

    def test_search_nodes_audit_insufficient_nodes(self):
        """Test SearchNodes audit with insufficient nodes"""
        search_nodes_data = [{"Name": "single-search-node"}]
        mock_sif = Mock()
        
        problems = search_nodes.audit(search_nodes_data, mock_sif, {})
        assert len(problems) == 1
        assert isinstance(problems[0], Problem)

    def test_search_nodes_audit_optimal_nodes(self):
        """Test SearchNodes audit with optimal number of nodes"""
        search_nodes_data = [
            {"Name": "search-node1"},
            {"Name": "search-node2"},
            {"Name": "search-node3"}
        ]
        mock_sif = Mock()
        
        problems = search_nodes.audit(search_nodes_data, mock_sif, {})
        assert isinstance(problems, list)

    def test_search_nodes_audit_even_number_of_nodes(self):
        """Test SearchNodes audit with even number of nodes"""
        search_nodes_data = [
            {"Name": "search-node1"},
            {"Name": "search-node2"},
            {"Name": "search-node3"},
            {"Name": "search-node4"}
        ]
        mock_sif = Mock()
        
        problems = search_nodes.audit(search_nodes_data, mock_sif, {})
        assert len(problems) == 1
        assert isinstance(problems[0], Problem)

    def test_search_nodes_audit_wrong_number_of_nodes(self):
        """Test SearchNodes audit with wrong number of nodes"""
        search_nodes_data = [
            {"Name": "search-node1"},
            {"Name": "search-node2"},
            {"Name": "search-node3"},
            {"Name": "search-node4"},
            {"Name": "search-node5"}
        ]
        mock_sif = Mock()
        
        problems = search_nodes.audit(search_nodes_data, mock_sif, {})
        assert len(problems) == 1
        assert isinstance(problems[0], Problem)


class TestSifEdgeCases:
    """Test Sif edge cases and error conditions"""

    def test_sif_start_time_missing(self):
        """Test Sif start_time when missing"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Remove start time information
        json_sif["System"].pop("StartTime", None)
        
        sif_obj = sif.Sif(json_sif)
        start_time = sif_obj.start_time()
        assert start_time is None

    def test_sif_store_size_missing(self):
        """Test Sif store_size when missing"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Remove store size information
        json_sif.pop("Search State", None)
        json_sif.pop("Elasticsearch", None)
        
        sif_obj = sif.Sif(json_sif)
        store_size = sif_obj.store_size()
        assert store_size is None

    def test_sif_license_type_missing(self):
        """Test Sif license_type when missing"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Remove license information
        json_sif.pop("License", None)
        
        sif_obj = sif.Sif(json_sif)
        license_type = sif_obj.license_type()
        assert license_type is None

    def test_sif_server_id_missing(self):
        """Test Sif server_id when missing"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Remove server id information
        json_sif["System"].pop("ServerId", None)
        
        sif_obj = sif.Sif(json_sif)
        server_id = sif_obj.server_id()
        assert server_id is None

    def test_sif_jvm_cmdlines_missing(self):
        """Test Sif JVM cmdlines when missing"""
        with open(f"{tutil.FILES_ROOT}/sif1.json", "r", encoding="utf-8") as f:
            json_sif = json.loads(f.read())
        
        # Remove JVM cmdlines
        json_sif["System"].pop("Web JVM Cmdline", None)
        json_sif["System"].pop("CE JVM Cmdline", None)
        json_sif["System"].pop("Search JVM Cmdline", None)
        
        sif_obj = sif.Sif(json_sif)
        assert sif_obj.web_jvm_cmdline() is None
        assert sif_obj.ce_jvm_cmdline() is None
        assert sif_obj.search_jvm_cmdline() is None
