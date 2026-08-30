# Screenplay Parsers and Immutable Version One Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Parse paste, Fountain, FDX, and PDF into one immutable normalized script version.  
**Architecture:** Deterministic parsers and isolated PDF extraction share a typed parse result; warnings require human acceptance.  
**Tech Stack:** Python, safe XML, isolated PDF worker, Gemini structured output, Hypothesis.

---

**Files:** Create `scripts/domain/versions.py`, `domain/elements.py`, `ports/parser.py`, `adapters/paste_parser.py`, `fountain_parser.py`, `fdx_parser.py`, `pdf_parser.py`, `application/parse_service.py`, `services/api/alembic/versions/0005_script_versions.py`; test `services/api/tests/scripts/parsers/`, `test_version_immutability.py`, `test_parse_commit.py`, `tests/conformance/test_pdf_extraction.py`.

1. Add golden and property fixtures for elements/spans/scenes/pages/lineage plus malformed encodings, XML entities/bombs, PDF actions/limits/injection, and provider failures.
2. Add migration 0005 with immutable version ordinal/hash and composite tenant relationships; test migration paths.
3. Implement parsers and atomic warning acceptance/version commit with audit/outbox.
4. Run four parser suites, hostile corpus, property tests, migrations, contract drift, and contest-profile adapter validation; expect exit 0.
5. Record evidence; commit `feat: add safe screenplay parsing and immutable versions` after authorization.

**Exit:** Every accepted input creates exact v1; failure creates no partial version or invented structure.

