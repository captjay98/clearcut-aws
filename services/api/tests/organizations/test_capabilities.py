from clearcut.organizations.domain.capabilities import Role, has_capability


def test_fixed_role_capabilities_matrix():
    # Project creation: Owner and Admin only
    assert has_capability(Role.OWNER, "project:create") is True
    assert has_capability(Role.ADMIN, "project:create") is True
    assert has_capability(Role.EDITOR, "project:create") is False
    assert has_capability(Role.REVIEWER, "project:create") is False

    # Assignment: Owner, Admin, Editor, Reviewer (DG-02)
    assert has_capability(Role.OWNER, "item:assign") is True
    assert has_capability(Role.ADMIN, "item:assign") is True
    assert has_capability(Role.EDITOR, "item:assign") is True
    assert has_capability(Role.REVIEWER, "item:assign") is True

    # Specialist referral: Owner, Admin, Reviewer only (DG-03)
    assert has_capability(Role.OWNER, "item:refer") is True
    assert has_capability(Role.ADMIN, "item:refer") is True
    assert has_capability(Role.REVIEWER, "item:refer") is True
    assert has_capability(Role.EDITOR, "item:refer") is False

    # Governed report release: Owner, Admin, Reviewer
    assert has_capability(Role.OWNER, "report:release") is True
    assert has_capability(Role.ADMIN, "report:release") is True
    assert has_capability(Role.REVIEWER, "report:release") is True
    assert has_capability(Role.EDITOR, "report:release") is False

    # Protected configuration: Owner only
    assert has_capability(Role.OWNER, "governance:manage") is True
    assert has_capability(Role.ADMIN, "governance:manage") is False
    assert has_capability(Role.REVIEWER, "governance:manage") is False
    assert has_capability(Role.EDITOR, "governance:manage") is False
