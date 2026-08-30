# Comments, Mentions, and Domain Events Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement one-level discussion, immutable revisions/mentions, and versioned collaboration events.  
**Architecture:** Comments are operational writes; event/outbox rows commit with their source change.  
**Tech Stack:** FastAPI, PostgreSQL, JSON Schema.

---

**Files:** Create `collaboration/domain/comments.py`, `application/comment_service.py`, `application/events.py`, `delivery/http.py`, `services/api/alembic/versions/0012_comments_events.py`, `packages/contracts/schemas/events/collaboration.v1.json`; test `services/api/tests/collaboration/test_comments.py`, `test_mentions.py`, `test_outbox_events.py`.

1. Add failing tests for DG-01 reply depth, edit history, attribution, mention authorization, actor self-exclusion input, schema compatibility, and duplicate delivery.
2. Add migration 0012; implement semantic comment/reply/revise operations and versioned outbox events.
3. Run collaboration/event/migration/contract tests; expect immutable history and no nested reply-to-reply.
4. Record evidence; commit `feat: add accountable item discussion events` after authorization.

**Exit:** Discussion history and event delivery remain immutable, scoped, and idempotent.
