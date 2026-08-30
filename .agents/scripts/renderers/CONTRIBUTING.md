# Adding a New AI Tool Renderer

To add support for a new AI coding tool, create a single file in `tooling/renderers/`.

## 1. Create the renderer

Create `tooling/renderers/<toolname>.mjs` with two exports:

```js
export const meta = {
  name: '<toolname>',           // Must match the filename (without .mjs)
  outputDirs: [                 // Files/dirs this renderer creates (for cleanup)
    '.<toolname>/agents',
    '.<toolname>/commands',
    '.<toolname>/GUIDE.md',
  ],
  mcpCapable: true,             // Does this tool support MCP servers?
}

export function render<Toolname>(canonical, options = {}) {
  // canonical contains: personas, commands, rules, steering, skills, hooks, memory, mcpServers
  // options contains: strict (boolean), projectName (string)
  //
  // Write files to the tool's output directory using helpers from common.mjs
  // Return: { warnings: string[] }

  return { warnings: [] }
}
```

## 2. That's it

The system auto-discovers renderers by scanning `tooling/renderers/*.mjs` (excluding `common.mjs`). No other files need to be modified.

## Available helpers (from `common.mjs`)

| Helper | Purpose |
|--------|---------|
| `writeMarkdownSet(items, dir)` | Write a collection of markdown files to a directory |
| `copySkills(skills, dir)` | Copy skill directories to target |
| `renderGuide({ title, subtitle, toolName, canonical })` | Generate a guide markdown string |
| `hooksForTool(hooks, toolName)` | Filter hooks that target this tool |
| `renderMcpConfig(mcpServers, format)` | Render MCP server config |
| `writeUtf8(path, content)` | Write a file (creates parent dirs) |
| `resetDir(dir)` | Remove and recreate a directory |
| `removeIfExists(path)` | Delete a file/dir if it exists |

## The `canonical` object

```js
{
  personas: [{ id, description, mode, model, raw, frontmatter }],
  commands: [{ id, description, raw, frontmatter }],
  rules:    [{ id, raw, frontmatter }],
  steering: [{ id, raw, frontmatter }],
  skills:   [{ id, dirPath, description, frontmatter }],
  hooks:    { hooks: [{ id, event, matcher, command, tools }] },
  memory:   'string',
  mcpServers: { ... } | null,
}
```

## Reference implementations

- `claude.mjs` — simplest, good starting point
- `kiro.mjs` — most complex (JSON templates, steering, .kiro.hook files)
- `opencode.mjs` — generates TypeScript plugin for hooks
