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

"""portfolio reference tests"""

import utilities as tutil
from sonar import portfolios as pf
from sonar import portfolio_reference as pfr
import sonar.util.constants as c

EXISTING_PORTFOLIO = "CORP-INSURANCE"
REF_PORTFOLIO = "CORP-INSURANCE-HEALTH"

SUPPORTED_EDITIONS = (c.EE, c.DCE)


def test_get_object_from_root() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    if not tutil.verify_support(SUPPORTED_EDITIONS, pfr.PortfolioReference.create, endpoint=tutil.SQ, key=tutil.TEMP_KEY, name=tutil.TEMP_KEY):
        return
    root_pf = pf.Portfolio.get_object(endpoint=tutil.SQ, key=EXISTING_PORTFOLIO)
    ref_pf = root_pf.sub_portfolios()[REF_PORTFOLIO]
    assert isinstance(ref_pf, pfr.PortfolioReference)
    assert ref_pf.reference.key == REF_PORTFOLIO
    assert str(ref_pf) == f"Portfolio reference '{EXISTING_PORTFOLIO}:{REF_PORTFOLIO}'"


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""

    ref_pf = pfr.PortfolioReference.get_object(endpoint=tutil.SQ, key=REF_PORTFOLIO, parent_key=EXISTING_PORTFOLIO)
    assert ref_pf.key == f"{EXISTING_PORTFOLIO}:{REF_PORTFOLIO}"
    assert str(ref_pf) == f"Portfolio reference '{EXISTING_PORTFOLIO}:{REF_PORTFOLIO}'"
