# claude-skills

Claude Code skills for personal productivity tools, starting with Joplin note-taking via its local Data API.

## Plugins

| Plugin | Skills | What it does |
| --- | --- | --- |
| [joplin](plugins/joplin) | `add-note` | Create Joplin notes (and list notebooks) from Claude Code. No MCP server needed. |

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

The `joplin` plugin has one skill, `add-note`, with two features: creating a note and listing notebooks. Claude loads the skill when you mention Joplin, so you can just ask in plain language. The skill's full name is `/joplin:add-note` if you want to invoke it explicitly.

### Create a note

Ask Claude:

> Add a note to Joplin titled "Meeting notes" with a summary of what we just discussed.

Name a notebook:

> Save this in my "Work" notebook in Joplin as "Deploy checklist".

Add tags (they are created if they don't exist yet):

> Put this in Joplin in the "Personal" notebook, titled "Book ideas", tagged "ideas" and "reading".

If you name no notebook and have not set `JOPLIN_DEFAULT_NOTEBOOK`, Claude asks which one to use, because Joplin would otherwise choose a notebook itself.

### List notebooks

> Which notebooks do I have in Joplin?

Matching is by name and ignores case. If two notebooks share a name, the script stops with an error instead of guessing, so rename one of them.

### Running the script directly

Claude runs `add_note.py` for you, but you can call it yourself. From the repo root, with `JOPLIN_TOKEN` set:

```bash
python plugins/joplin/skills/add-note/scripts/add_note.py notebooks
```

The title is an argument and the Markdown body is read from stdin, so quotes and newlines need no escaping. `--notebook` and `--tag` are optional, and `--tag` can be repeated.

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

A successful run prints `Created note 'Deploy checklist' (id ...) in 'Work'.` Problems print `Error: ...` and exit with code 1. The usual causes are Joplin not running, the Web Clipper service being off, or a missing or wrong `JOPLIN_TOKEN`.

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
