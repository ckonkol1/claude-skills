# claude-skills

Claude Code skills for personal productivity tools, starting with Joplin note-taking via its local Data API.

## Plugins

| Plugin | Skills | What it does |
| --- | --- | --- |
| [joplin](plugins/joplin) | `add-note` | Create, append to, and rename Joplin notes, and list notebooks, from Claude Code. No MCP server needed. |

## Install

```bash
claude plugin marketplace add ckonkol1/claude-skills
```

```bash
claude plugin install joplin@claude-skills
```

## Joplin setup

1. In Joplin, open **Tools > Options > Web Clipper** and enable the Web Clipper service.
2. Copy the authorization token and set it as the `JOPLIN_TOKEN` environment variable, then restart Claude Code.
3. Recommended: set `JOPLIN_DEFAULT_NOTEBOOK` to the notebook new notes should go in. Without it, and without a notebook named in your request, Joplin picks the notebook itself (in testing, a previously used one).
4. Optional: set `JOPLIN_PORT` if Joplin is not on the default port 41184.

Requires Python 3 (standard library only; nothing to `pip install`). Tested on Python 3.13.

## Usage

The `joplin` plugin has one skill, `add-note`, with four features: creating a note, appending to an existing note, renaming a note, and listing notebooks. Claude loads the skill when you mention Joplin, so you can just ask in plain language. The skill's full name is `/joplin:add-note` if you want to invoke it explicitly.

### Create a note

Ask Claude:

> Add a note to Joplin titled "Meeting notes" with a summary of what we just discussed.

Name a notebook:

> Save this in my "Work" notebook in Joplin as "Deploy checklist".

Add tags (they are created if they don't exist yet):

> Put this in Joplin in the "Personal" notebook, titled "Book ideas", tagged "ideas" and "reading".

If you name no notebook and have not set `JOPLIN_DEFAULT_NOTEBOOK`, Claude asks which one to use, because Joplin would otherwise choose a notebook itself.

### Append to an existing note

> Append today's decisions to my Joplin note "Meeting notes".

> Add "call the vendor on Monday" to the "Todo" note in my "Work" notebook.

The new text goes after the existing content, separated by a blank line. Nothing already in the note is changed or removed. The script reads the note and then writes it back, so don't edit the same note in Joplin at the very moment you append to it, or that edit can be overwritten.

### Rename a note

> Rename my Joplin note "Meeting notes" to "Weekly sync notes".

Only the title changes. The body, notebook, and tags stay as they are.

### How notes are found (append and rename)

You can refer to a note by its exact title (case-insensitive) or by its 32-character note id.

- If several notes share the title, the script stops and prints each match's id and notebook, and changes nothing. Tell Claude which one you mean, for example "the one in Work", or give the id.
- Naming a notebook ("in my Work notebook") narrows the search to that notebook. It can't be combined with a note id.
- Notes in the Joplin trash are never matched.
- `JOPLIN_DEFAULT_NOTEBOOK` only applies to creating notes. It doesn't limit where append and rename look.
- Claude should tell you which note it is about to change when it had to work that out from your wording.

### List notebooks

> Which notebooks do I have in Joplin?

Matching is by name and ignores case. If two notebooks share a name, the script stops with an error instead of guessing, so rename one of them.

### Running the script directly

Claude runs `add_note.py` for you, but you can call it yourself. From the repo root, with `JOPLIN_TOKEN` set:

```bash
python plugins/joplin/skills/add-note/scripts/add_note.py notebooks
```

The title is an argument and the Markdown text is read from stdin, so quotes and newlines need no escaping. The commands are:

| Command | What it does |
| --- | --- |
| `notebooks` | List notebook names. |
| `add TITLE [--notebook NAME] [--tag TAG ...]` | Create a note from stdin. `--tag` can be repeated. |
| `append NOTE [--notebook NAME]` | Add stdin text to the end of an existing note. |
| `rename NOTE NEW_TITLE [--notebook NAME]` | Change a note's title. |

`NOTE` is an exact note title or a 32-character note id.

Bash:

```bash
python plugins/joplin/skills/add-note/scripts/add_note.py add "Deploy checklist" --notebook "Work" --tag ops --tag checklist <<'EOF'
- Run migrations
- Smoke test the API
EOF
```

PowerShell:

```powershell
@'
- Run migrations
- Smoke test the API
'@ | python plugins/joplin/skills/add-note/scripts/add_note.py add "Deploy checklist" --notebook "Work" --tag ops --tag checklist
```

Append to that note (bash), then rename it:

```bash
python plugins/joplin/skills/add-note/scripts/add_note.py append "Deploy checklist" --notebook "Work" <<'EOF'
- Announce in the team channel
EOF
```

```bash
python plugins/joplin/skills/add-note/scripts/add_note.py rename "Deploy checklist" "Release checklist" --notebook "Work"
```

The same append in PowerShell:

```powershell
'- Announce in the team channel' | python plugins/joplin/skills/add-note/scripts/add_note.py append "Deploy checklist" --notebook "Work"
```

A successful `add` prints `Created note 'Deploy checklist' (id ...) in 'Work'.`; `append` prints `Appended to note 'Deploy checklist' (id ...).`; `rename` prints `Renamed note 'Deploy checklist' to 'Release checklist' (id ...).` Problems print `Error: ...` and exit with code 1. The usual causes are Joplin not running, the Web Clipper service being off, or a missing or wrong `JOPLIN_TOKEN`.

## Security notes

- The token grants full read and write access to all your notes. Keep it in an environment variable, never in a file you commit or in chat.
- The script only talks to `127.0.0.1`. Note content and the token never leave your machine.
- The script never prints the token, including in error messages.

## Development

```bash
python -m unittest discover -s plugins/joplin/tests
```

The tests run against a fake local Joplin server. They do not touch a real Joplin install.

## License

MIT
