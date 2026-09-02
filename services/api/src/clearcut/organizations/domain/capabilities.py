from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    REVIEWER = "reviewer"


ROLE_CAPABILITIES: dict[Role, set[str]] = {
    Role.OWNER: {
        "project:create",
        "project:read",
        "project:update",
        "item:assign",
        "item:refer",
        "item:decide",
        "item:disposition",
        "rewrite:propose",
        "rewrite:approve",
        "report:generate",
        "report:release",
        "member:invite",
        "member:manage",
        "governance:manage",
        "org:delete",
    },
    Role.ADMIN: {
        "project:create",
        "project:read",
        "project:update",
        "item:assign",
        "item:refer",
        "item:decide",
        "item:disposition",
        "rewrite:propose",
        "rewrite:approve",
        "report:generate",
        "report:release",
        "member:invite",
        "member:manage",
    },
    Role.REVIEWER: {
        "project:read",
        "item:assign",
        "item:refer",
        "item:decide",
        "item:disposition",
        "rewrite:approve",
        "report:generate",
        "report:release",
    },
    Role.EDITOR: {
        "project:read",
        "item:assign",
        "rewrite:propose",
        "comment:create",
    },
}


def has_capability(role: Role | str, action: str) -> bool:
    try:
        r = Role(role) if isinstance(role, str) else role
    except ValueError:
        return False
    return action in ROLE_CAPABILITIES.get(r, set())
