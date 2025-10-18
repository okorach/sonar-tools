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

"""applications tests"""

import pytest

import utilities as tutil
from sonar import projects, branches, exceptions
import sonar.util.constants as c

SUPPORTED_EDITIONS = (c.DE, c.EE, c.DCE)


def verify_branch_support(func: callable, **kwargs) -> bool:
    if kwargs["concerned_object"].endpoint.edition() not in SUPPORTED_EDITIONS:
        with pytest.raises(exceptions.UnsupportedOperation):
            _ = func(**kwargs)
        return False
    return True


def test_get_object() -> None:
    """Test get_object and verify that if requested twice the same object is returned"""

    project = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
    if not verify_branch_support(branches.Branch.get_object, concerned_object=project, branch_name="develop"):
        return
    obj = branches.Branch.get_object(concerned_object=project, branch_name="develop")
    assert str(obj) == f"branch 'develop' of project '{project.key}'"
    obj.refresh()


def test_not_found() -> None:
    project = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
    if not verify_branch_support(branches.Branch.get_object, concerned_object=project, branch_name="develop"):
        return
    with pytest.raises(exceptions.ObjectNotFound):
        obj = branches.Branch.get_object(concerned_object=project, branch_name="non-existing")

    obj = branches.Branch.get_object(concerned_object=project, branch_name="develop")
    obj.name = "non-existing2"
    with pytest.raises(exceptions.ObjectNotFound):
        obj.refresh()

    obj.concerned_object.key = "non-existing2"
    with pytest.raises(exceptions.ObjectNotFound):
        obj.new_code()


def test_is_main_is_kept():
    project = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
    if not verify_branch_support(branches.Branch.get_object, concerned_object=project, branch_name="develop"):
        return
    obj = branches.Branch.get_object(concerned_object=project, branch_name="develop")
    obj._keep_when_inactive = None
    obj.refresh()
    assert obj.is_kept_when_inactive() in (True, False)
    obj._is_main = None
    assert obj.is_main() in (True, False)


def test_set_as_main():
    """test_set_as_main"""
    project = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
    if not verify_branch_support(branches.Branch.get_object, concerned_object=project, branch_name="develop"):
        return
    dev_br = branches.Branch.get_object(concerned_object=project, branch_name="develop")
    master_br = branches.Branch.get_object(concerned_object=project, branch_name="master")
    assert master_br.is_main()
    assert not dev_br.is_main()

    assert dev_br.set_as_main()
    assert not master_br.is_main()
    assert dev_br.is_main()

    assert master_br.set_as_main()

    master_br.name = "non-existing"
    with pytest.raises(exceptions.ObjectNotFound):
        master_br.set_as_main()


def test_set_keep_as_inactive():
    """test_set_keep_as_inactive"""
    project = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
    if not verify_branch_support(branches.Branch.get_object, concerned_object=project, branch_name="develop"):
        return
    dev_br = branches.Branch.get_object(concerned_object=project, branch_name="develop")
    master_br = branches.Branch.get_object(concerned_object=project, branch_name="master")
    assert dev_br.is_kept_when_inactive()
    assert master_br.is_kept_when_inactive()

    assert dev_br.set_keep_when_inactive(False)
    assert not dev_br.is_kept_when_inactive()
    assert master_br.is_kept_when_inactive()

    assert dev_br.set_keep_when_inactive(True)

    dev_br.name = "non-existing"
    with pytest.raises(exceptions.ObjectNotFound):
        dev_br.set_keep_when_inactive(True)


def test_rename():
    """test_rename"""
    project = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
    if not verify_branch_support(branches.Branch.get_object, concerned_object=project, branch_name="develop"):
        return
    dev_br = branches.Branch.get_object(concerned_object=project, branch_name="develop")
    main_br_name = project.main_branch_name()
    main_br = branches.Branch.get_object(concerned_object=project, branch_name=main_br_name)
    with pytest.raises(exceptions.UnsupportedOperation):
        dev_br.rename("release")

    new_name = "gold"
    assert main_br.rename(new_name)
    assert not main_br.rename(new_name)

    new_br = branches.Branch.get_object(concerned_object=project, branch_name=new_name)
    assert new_br is main_br
    assert main_br.rename(main_br_name)
    assert new_br.name == main_br_name


def test_get_findings():
    """test_get_findings"""
    project = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
    if not verify_branch_support(branches.Branch.get_object, concerned_object=project, branch_name="develop"):
        return
    dev_br = branches.Branch.get_object(concerned_object=project, branch_name="develop")
    assert len(dev_br.get_findings()) > 0

    dev_br.name = "non-existing"
    with pytest.raises(exceptions.ObjectNotFound):
        dev_br.get_findings()


def test_audit():
    """test_audit_off"""
    project = projects.Project.get_object(tutil.SQ, tutil.LIVE_PROJECT)
    if not verify_branch_support(branches.Branch.get_object, concerned_object=project, branch_name="develop"):
        return
    dev_br = branches.Branch.get_object(concerned_object=project, branch_name="develop")
    assert len(dev_br.audit({"audit.project.branches": False})) == 0

    dev_br.name = "non-existing"
    assert len(dev_br.audit({})) == 0


def test_exists():
    """test_exists"""
    if tutil.SQ.edition() == c.CE:
        with pytest.raises(exceptions.UnsupportedOperation):
            branches.exists(tutil.SQ, branch_name="develop", project_key=tutil.LIVE_PROJECT)
    else:
        assert branches.exists(tutil.SQ, branch_name="develop", project_key=tutil.LIVE_PROJECT)
        assert not branches.exists(tutil.SQ, branch_name="foobar", project_key=tutil.LIVE_PROJECT)
