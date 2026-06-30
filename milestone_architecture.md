# Milestone Architecture (PR-1A)

This document is intentionally not yet written.

Per ADR-0007 §1, the architectural contract (invariants, vocabulary,
rejected alternatives, deferred decisions) is defined there and should not
be duplicated here ahead of an implementation to describe.

This file becomes the canonical schema/implementation reference once
PR-1A (`MilestoneDefinition`, `SeasonMilestone`, `SeasonMilestoneHistory`
— models, migration, enums, repository helpers, seed data) is concrete
enough to document accurately. Writing it before then risks the same
drift problem ADR-0007 exists to prevent: documentation describing a
design that hasn't been implemented, and code drifting away from it
unnoticed.

See `ADR-0007-milestone-based-scheduling.md` for the architectural
contract and `scheduling_principles.md` for the five governing
principles in the meantime.
