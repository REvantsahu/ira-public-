# Memory System
description: How to use IRA's persistent memory — reading, saving, updating, and deleting memories
when_to_use: User asks about past work ("do you remember", "what did we do", "last time"), shares info to remember, asks what you know about them, or topic shifts to past work

## Instructions
IRA's memory lives in `C:\Users\reban\iradmemory\` as structured `.md` files.
Tools: `memory_save`, `memory_read`, `memory_list`, `memory_update`, `memory_delete`

### Folder Structure
```
iradmemory/
  blueprint.md              ← the map (read first)
  personal/                 ← profile, preferences, working-style
  projects/                 ← per-project files
  approaches/               ← debugging patterns, codebase maps
  facts/                    ← durable facts
  errors/                   ← recurring errors + fixes
```

### On Read (User asks "what do you remember")
1. Read `blueprint.md` first — it tells you which folder has what
2. Use `memory_read("path/to/topic")` to get specific memories
3. Use `memory_list()` to see all available memory files
4. For broad questions like "what do you know about me", read personal/ files
5. Synthesize from contents — don't invent. Say "I don't have that stored" if nothing matches.

### Auto-Save Rules
**Save proactively** when user shares:
- Project state changes ("IRA ab X kar raha hai")
- New bugs/fixes found
- User info updates (location, contact, what they're building)
- Code patterns discovered
- Decisions made
- Cross-session context

**Don't save:**
- Ephemeral one-off questions
- Current debug logs
- Random date facts
- Transient state
- Things already in codebase

### Edit (Don't Duplicate)
When new info contradicts stored info, edit the existing file — don't create a duplicate.

### Delete (With Confirmation)
Always confirm before deleting unless user is explicit. Ask: "Should I delete X from memory?"

## Examples
- User: "do you remember my project?" → memory_read("projects/ira/overview")
- User: "yaad rakh main class 10 mein hu" → memory_save("personal/profile", "Class: 10")
- User: "delete that memory" → memory_delete("path/file")
