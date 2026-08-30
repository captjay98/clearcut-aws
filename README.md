# Scaffold

Bootstrap template for new agent systems. Copied to projects on first setup, never overwritten.

## Structure

```
scaffold/.agents/
├── commands/          # 21 workflow commands
├── skills/            # 4 universal skills
├── steering/          # 10 project context docs
├── rules/             # 9 coding rules
├── personas/          # 9 role templates
├── memory/            # Institutional knowledge template
├── includes/shared/   # Reusable content (delegation pattern)
├── hooks/             # Git hooks configuration
├── kiro/templates/    # Kiro agent templates
├── mcp/               # MCP server configuration
├── guide-header.md    # Critical patterns (injected into AGENTS.md)
└── profile.toml       # Toolchain configuration
```

## Usage

When bootstrapping a new project:

```bash
node bootstrap.mjs ~/projects/new-app
```

This copies the scaffold to `new-app/.agents/` with `skipExisting: true` — existing files are never overwritten.

## Customization

All scaffold files contain placeholders:
- `[PROJECT_NAME]` — Replace with actual project name
- `<!-- PROJECT: ... -->` — Fill with project-specific content
- `[Add ...]` — Add project-specific items

After copying scaffold:
1. Fill all placeholders
2. Write `guide-header.md` with critical patterns
3. Customize `memory/project-memory.md` with institutional knowledge
4. Update `includes/shared/delegation-pattern.md` with project personas
5. Run `bun .agents/scripts/build.mjs` to generate `AGENTS.md`

## Quality Levels

**8/10 — Production Ready**
- All placeholders filled
- guide-header.md with critical patterns
- Personas have project-specific context

**10/10 — World Class**
- Memory: Full institutional knowledge
- Delegation: Structured handoff format with example
- Commands: 2-3 upgraded to runbooks
- Skills: 5-8 with decision triggers
- Personas: All at depth (80-140 lines)
- Guide-header: 30-50 lines with patterns
