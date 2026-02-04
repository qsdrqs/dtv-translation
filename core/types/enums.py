from __future__ import annotations

from enum import Enum


class Granularity(str, Enum):
    STMT = "stmt"
    BLOCK = "block"
    FUNC = "func"
    PROGRAM = "program"

    _ORDER = {
        "stmt": 0,
        "block": 1,
        "func": 2,
        "program": 3,
    }

    def _order(self) -> int:
        return self._ORDER[self.value]

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Granularity):
            return NotImplemented
        return self._order() < other._order()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Granularity):
            return NotImplemented
        return self._order() <= other._order()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Granularity):
            return NotImplemented
        return self._order() > other._order()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Granularity):
            return NotImplemented
        return self._order() >= other._order()


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


class FeedbackMode(str, Enum):
    INLINE = "inline"
    FENCED = "fenced"


RollbackScope = Granularity
