---
name: add-note
description: Create, append to, or rename notes in Joplin. Use when the user asks to save, add, capture, or jot something down in Joplin, to add text to an existing Joplin note, to rename a Joplin note, or to list their Joplin notebooks.
---

# Create, append to, and rename Joplin notes

Works through Joplin's local Data API using a bundled script. Nothing leaves the user's machine.

## Before you start

The script needs the `JOPLIN_TOKEN` environment variable, and Joplin must be running with the Web Clipper service enabled (Tools > Options > Web Clipper). Never ask the user to paste the token into chat and never print it. If the script reports a setup problem, relay its message and stop.

Optional environment variables: `JOPLIN_DEFAULT_NOTEBOOK` (used by `add` when you pass no `--notebook`; it does not affect finding existing notes) and `JOPLIN_PORT` (default 41184).

The script is `${CLAUDE_PLUGIN_ROOT}/skills/add-note/scripts/add_note.py`. Run it with `python` (or `py` / `python3` if `python` is not found). Text for a note goes on stdin, so quotes and newlines need no escaping. Examples below use bash; in PowerShell pipe a single-quoted here-string instead (`@'` ... `'@`, with the closing `'@` at column 0) into the same command.

## Create a note

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/add-note/scripts/add_note.py" add "Note title" --notebook "Inbox" --tag ideas <<'EOF'
Markdown body goes here.
EOF
```

- `--notebook` is optional and matched by name, ignoring case. `--tag` is optional and can be repeated; missing tags are created.
- Without `--notebook` (and without `JOPLIN_DEFAULT_NOTEBOOK`), Joplin chooses the notebook itself. In testing it picked an unrelated, previously used notebook. So if the user did not name a notebook, ask which one to use instead of omitting it, and never invent a name.
- If they named one loosely ("my work notebook"), run the `notebooks` command first and pick the closest match; ask if more than one fits. Joplin lists nested notebooks by their own name, so duplicates can appear; the script refuses to guess when a name is ambiguous.
- Use only text the user gave you or asked you to write. Do not add secrets, tokens, or credentials to a note.

## Append to an existing note

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/add-note/scripts/add_note.py" append "Note title" --notebook "Work" <<'EOF'
Text to add at the end of the note.
EOF
```

The text is added after the existing content, separated by a blank line. Existing content is never changed or removed.

## Rename a note

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/add-note/scripts/add_note.py" rename "Old title" "New title" --notebook "Work"
```

Only the title changes; the body, notebook, and tags stay as they are.

## Choosing the note for append and rename

The first argument is the note's exact title (case-insensitive) or its 32-character note id.

- Only touch a note the user named or clearly described. If you are inferring which note they mean, say which title you are about to change and let them confirm first.
- `--notebook` narrows a title lookup to one notebook. It cannot be combined with a note id.
- If several notes share the title, the script stops and prints each match's id and notebook, changing nothing. Show the user the options, then rerun with the chosen id (or `--notebook`).
- Notes in the trash are never matched.
- Do not delete notes or notebooks; this skill does not support it.

## List notebooks

```bash
python "${CLAUDE_PLUGIN_ROOT}/skills/add-note/scripts/add_note.py" notebooks
```

## After running

Tell the user what the script reported (the title and notebook for a new note, or which note was appended to or renamed). If it exits with an error, show the message as-is. Do not retry with different guesses, and do not repeat a command that may have succeeded: an append run twice adds the text twice.
