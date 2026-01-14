from __future__ import annotations

from enum import Enum


class Granularity(str, Enum):
    STMT = "stmt"
    BLOCK = "block"
    FUNC = "func"
    PROGRAM = "program"


class RenderStatus(str, Enum):
    OK = "ok"
    CONTINUE = "continue"
    FAIL = "fail"


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class GroupEventAction(str, Enum):
    OPEN = "open"
    CLOSE = "close"


class Action(str, Enum):
    GENERATE = "generate"
    VERIFY = "verify"
    FEEDBACK = "feedback"
    APPLY_PATCH = "apply_patch"
    CONTINUE = "continue"
    COMMIT = "commit"
    ROLLBACK = "rollback"
    TERMINATE = "terminate"


class RollbackScope(str, Enum):
    STMT = "stmt"
    BLOCK = "block"
    FUNC = "func"
    PROGRAM = "program"
