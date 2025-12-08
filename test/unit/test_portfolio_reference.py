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

import pytest
import utilities as tutil
from sonar import portfolios as pf
from sonar import portfolio_reference as pfr
from sonar import exceptions
import sonar.util.constants as c

EXISTING_PORTFOLIO = "CORP-INSURANCE"
REF_PORTFOLIO = "CORP-INSURANCE-HEALTH"


def test_get_object_from_root() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""
    if tutil.SQ.edition() not in c.EDITIONS_SUPPORTING_PORTFOLIOS:
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = pf.Portfolio.get_object(endpoint=tutil.SQ, key=EXISTING_PORTFOLIO)
        return
    root_pf = pf.Portfolio.get_object(endpoint=tutil.SQ, key=EXISTING_PORTFOLIO)
    ref_pf = root_pf.sub_portfolios()[REF_PORTFOLIO]
    assert isinstance(ref_pf, pfr.PortfolioReference)
    assert ref_pf.reference.key == REF_PORTFOLIO
    assert str(ref_pf) == f"Portfolio reference '{EXISTING_PORTFOLIO}:{REF_PORTFOLIO}'"


def test_get_object() -> None:
    """Test get_object method"""

    if tutil.SQ.edition() not in c.EDITIONS_SUPPORTING_PORTFOLIOS:
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = pfr.PortfolioReference.get_object(endpoint=tutil.SQ, key=REF_PORTFOLIO, parent_key=EXISTING_PORTFOLIO)
        return
    ref_pf = pfr.PortfolioReference.get_object(endpoint=tutil.SQ, key=REF_PORTFOLIO, parent_key=EXISTING_PORTFOLIO)
    assert ref_pf.key == f"{EXISTING_PORTFOLIO}:{REF_PORTFOLIO}"
    assert str(ref_pf) == f"Portfolio reference '{EXISTING_PORTFOLIO}:{REF_PORTFOLIO}'"


def test_get_object_not_found() -> None:
    """Test exception raised when providing non existing portfolio reference key"""

    if tutil.SQ.edition() not in c.EDITIONS_SUPPORTING_PORTFOLIOS:
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = pfr.PortfolioReference.get_object(endpoint=tutil.SQ, key=REF_PORTFOLIO, parent_key=EXISTING_PORTFOLIO)
        return
    with pytest.raises(exceptions.ObjectNotFound):
        pfr.PortfolioReference.get_object(endpoint=tutil.SQ, key="non-existing", parent_key=EXISTING_PORTFOLIO)
    with pytest.raises(exceptions.ObjectNotFound):
        pfr.PortfolioReference.get_object(endpoint=tutil.SQ, key=REF_PORTFOLIO, parent_key="non-existing")
