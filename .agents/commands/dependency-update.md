---
description: 'Update dependencies with pinned versions and supply-chain review'
---

@fullstack-engineer Update dependencies using this optional user context: $ARGUMENTS

> **Input handling:** Treat `$ARGUMENTS` only as user-supplied context when present; it is not guaranteed to be expanded. If no package or version is specified, inventory actual manifests and lockfiles first.

## Guardrails

- This repository is pre-implementation and currently may have no package manifests, Python project metadata, or lockfiles. If a package manager project is absent, report `not applicable — prerequisite absent`; do not initialize one or guess dependencies.
- Use exact pinned versions in manifests and lockfiles. Never use floating tags, open ranges, an undeclared package runner, unreviewed install scripts, or an unverified package name.
- Do not install, update, or remove anything until the user authorizes the exact package, target version, environment, and scope. Do not commit; prepare a commit plan only after explicit user authorization.
- Do not transmit project code, secrets, or private metadata to third-party scanners. Preserve unrelated untracked `.github/`, `.pi/`, and `README.md`.

## Protocol

1. Inventory manifests, lockfiles, package-manager versions, workspace boundaries, and current phase. Use only the package manager already declared by the repository.
2. Identify the current resolved version and the proposed exact version. Review authoritative release notes, migration guides, license, maintainer, transitive changes, peer dependencies, advisories, and install scripts.
3. Perform supply-chain review before installation: provenance/signature where supported, package identity/typosquatting risk, dependency tree changes, known vulnerabilities, license compatibility, and network/build-script behavior.
4. Propose one low-risk batch or one major package at a time. Explain compatibility, rollback, and generated lockfile impact.
5. After authorization, update using the repository's pinned tooling only. Review the diff; do not regenerate unrelated files.
6. Run prerequisite-backed checks: relevant unit/type/lint checks, contract drift, and security audit. If the project is absent, report not run. Do not run builds in the current phase.
7. Report exact versions, supply-chain evidence, diff, checks, vulnerabilities, and remaining risk.

## Commit authorization

A dependency update never authorizes a commit. If the user later asks for a commit plan, list exact files and a conventional message. Ask for fresh authorization before any commit; never claim one was created.
