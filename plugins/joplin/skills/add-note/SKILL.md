---
name: add-note
description: Create a note in Joplin from the conversation. Use when the user asks to save, add, capture, or jot something down in Joplin, or to put text into a Joplin notebook. Also lists Joplin notebooks.
---

# Add a note to Joplin

Creates notes through Joplin's local Data API using a bundled script. Nothing leaves the user's machine.

## Before you start

The script needs the `JOPLIN_TOKEN` environment variable, and Joplin must be running with the Web Clipper service enabled (Tools > Options > Web Clipper). Never ask the user to paste the token into chat and never print it. If the script reports a setup problem, relay its message and stop.

Optional environment variables: `JOPLIN_DEFAULT_NOTEBOOK` (used when you pass no `--notebook`) and `JOPLIN_PORT` (default 41184).

## Create a note

The script is `${CLAUDE_PLUGIN_ROOT}/skills/add-note/scripts/add_note.py`. Run it with `python` (or `py` / `python3` if `python` is not found). Pass the title as an argument and the Markdown body on stdin, so quotes and newlines in the body need no escaping.

Bash:

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/add-note/scripts/add_note.py" add "Note title" --notebook "Inbox" --tag ideas <<'EOF'
Markdown body goes here.
EOF
```

PowerShell (the closing `'@` must start at column 0):

```powershell
@'
Markdown body goes here.
'@ | python "${CLAUDE_PLUGIN_ROOT}/skills/add-note/scripts/add_note.py" add "Note title" --notebook "Inbox" --tag ideas
```

- `--notebook` is optional and matched by name, ignoring case. `--tag` is optional and can be repeated; missing tags are created.
- Use only text the user gave you or asked you to write. Do not add secrets, tokens, or credentials to a note.
- Without `--notebook` (and without `JOPLIN_DEFAULT_NOTEBOOK`), Joplin chooses the notebook itself. In testing it picked an unrelated, previously used notebook. So if the user did not name a notebook, ask which one to use instead of omitting it, and never invent a name.
- If they named one loosely ("my work notebook"), run the `notebooks` command first and pick the closest match; ask if more than one fits. Joplin lists nested notebooks by their own name, so duplicates can appear; the script refuses to guess when a name is ambiguous.

## List notebooks

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/add-note/scripts/add_note.py" notebooks
```

## After running

Tell the user the title and notebook the script reported. If it exits with an error, show the message as-is. Do not retry with different guesses, and do not create the note a second time unless the first attempt clearly failed.
