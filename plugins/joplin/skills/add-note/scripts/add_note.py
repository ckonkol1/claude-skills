#!/usr/bin/env python3
"""Create, append to, and rename notes in Joplin through its local Data API.

Configuration comes from environment variables so the token never appears on a
command line or in output:
    JOPLIN_TOKEN             required, from Joplin > Options > Web Clipper
    JOPLIN_PORT              optional, defaults to 41184
    JOPLIN_DEFAULT_NOTEBOOK  optional, used by "add" when --notebook is not given

Usage (a NOTE is a 32-character note id or an exact note title):
    add_note.py notebooks
    add_note.py add TITLE [--notebook NAME] [--tag TAG ...]      (body from stdin)
    add_note.py append NOTE [--notebook NAME]                    (text from stdin)
    add_note.py rename NOTE NEW_TITLE [--notebook NAME]
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HOST = "127.0.0.1"  # Fixed on purpose: the note content and token must never leave this machine.
DEFAULT_PORT = 41184
REQUEST_TIMEOUT_SECONDS = 10
PAGE_LIMIT = 100
MAX_LISTED_MATCHES = 10
NOTE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


class JoplinError(Exception):
    """A problem the user can act on; the message is safe to print."""


class JoplinNotFoundError(JoplinError):
    """Joplin answered 404 for the requested item."""


def read_port():
    raw_port = os.environ.get("JOPLIN_PORT", str(DEFAULT_PORT))
    if not raw_port.isdigit() or not 1 <= int(raw_port) <= 65535:
        raise JoplinError("JOPLIN_PORT must be a number between 1 and 65535.")
    return int(raw_port)


def read_token():
    token = os.environ.get("JOPLIN_TOKEN", "").strip()
    if not token:
        raise JoplinError(
            "JOPLIN_TOKEN is not set. In Joplin open Tools > Options > Web Clipper, "
            "enable the service, copy the authorization token, and set it as the "
            "JOPLIN_TOKEN environment variable."
        )
    return token


def call_api(method, path, query=None, payload=None):
    """Call the Joplin Data API and return the decoded JSON response.

    The token is sent as a query parameter because that is how the API expects it.
    The URL is never included in error messages so the token cannot leak.
    """
    query_params = dict(query or {})
    query_params["token"] = read_token()
    url = "http://{}:{}{}?{}".format(
        HOST, read_port(), path, urllib.parse.urlencode(query_params)
    )
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise JoplinError("Joplin rejected the token. Check JOPLIN_TOKEN.") from None
        message = "Joplin returned HTTP {} for {} {}.".format(error.code, method, path)
        if error.code == 404:
            raise JoplinNotFoundError(message) from None
        raise JoplinError(message) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        raise JoplinError(
            "Cannot reach Joplin on port {}. Make sure Joplin is running and the "
            "Web Clipper service is enabled (Tools > Options > Web Clipper).".format(
                read_port()
            )
        ) from None
    except json.JSONDecodeError:
        raise JoplinError(
            "Port {} did not answer like Joplin (response was not JSON).".format(read_port())
        ) from None


def fetch_all_pages(path, query=None):
    items = []
    page = 1
    while True:
        page_query = dict(query or {}, page=page, limit=PAGE_LIMIT)
        result = call_api("GET", path, query=page_query)
        items.extend(result["items"])
        if not result.get("has_more"):
            return items
        page += 1


def find_notebook_id(notebook_name):
    matches = [
        notebook
        for notebook in fetch_all_pages("/folders")
        if notebook["title"].casefold() == notebook_name.casefold()
    ]
    if not matches:
        raise JoplinError(
            "No notebook named '{}'. Run the 'notebooks' command to see the options.".format(
                notebook_name
            )
        )
    if len(matches) > 1:
        raise JoplinError(
            "{} notebooks are named '{}'. Rename one so the target is unambiguous.".format(
                len(matches), notebook_name
            )
        )
    return matches[0]["id"]


def find_or_create_tag_id(tag_name):
    for tag in fetch_all_pages("/tags"):
        if tag["title"].casefold() == tag_name.casefold():
            return tag["id"]
    return call_api("POST", "/tags", payload={"title": tag_name})["id"]


def create_note(title, body, notebook_name, tag_names):
    # Resolve the notebook and tags first so a typo fails before any note is created.
    note_fields = {"title": title, "body": body}
    if notebook_name:
        note_fields["parent_id"] = find_notebook_id(notebook_name)
    tag_ids = [find_or_create_tag_id(tag_name) for tag_name in tag_names]

    note = call_api("POST", "/notes", payload=note_fields)
    for tag_id in tag_ids:
        call_api("POST", "/tags/{}/notes".format(tag_id), payload={"id": note["id"]})
    return note["id"]


def find_note_by_id(note_id):
    try:
        note = call_api(
            "GET", "/notes/{}".format(note_id), query={"fields": "id,title,parent_id,deleted_time"}
        )
    except JoplinNotFoundError:
        raise JoplinError("No note with id {}.".format(note_id)) from None
    # Joplin still returns trashed notes when asked for them by id.
    if note.get("deleted_time"):
        raise JoplinError("The note '{}' is in the trash.".format(note["title"]))
    return note


def describe_notes_by_notebook(notes):
    notebook_titles = {notebook["id"]: notebook["title"] for notebook in fetch_all_pages("/folders")}
    return "\n".join(
        "  {} (notebook: {})".format(note["id"], notebook_titles.get(note["parent_id"], "unknown"))
        for note in notes[:MAX_LISTED_MATCHES]
    )


def find_note_by_title(title, notebook_name):
    notebook_id = find_notebook_id(notebook_name) if notebook_name else None
    path = "/folders/{}/notes".format(notebook_id) if notebook_id else "/notes"
    # Scan titles instead of using Joplin's search: it is exact, and the listing
    # leaves out trashed notes. A fixed order keeps paging stable.
    notes = fetch_all_pages(path, query={"fields": "id,title,parent_id", "order_by": "id"})
    matches = [note for note in notes if note["title"].casefold() == title.casefold()]
    if not matches:
        raise JoplinError("No note titled '{}'.".format(title))
    if len(matches) > 1:
        raise JoplinError(
            "{} notes are titled '{}'. Pass --notebook, or use the note id:\n{}".format(
                len(matches), title, describe_notes_by_notebook(matches)
            )
        )
    return matches[0]


def find_note(note_reference, notebook_name):
    reference = note_reference.strip()
    if NOTE_ID_PATTERN.match(reference):
        if notebook_name:
            raise JoplinError("--notebook only applies when the note is given by title, not by id.")
        return find_note_by_id(reference)
    return find_note_by_title(reference, notebook_name)


def join_appended_text(existing_body, new_text):
    """Add new_text after the existing body, separated by one blank line."""
    if not existing_body:
        return new_text
    line_break = "" if existing_body.endswith("\n") else "\n"
    return existing_body + line_break + "\n" + new_text


def append_to_note(note_id, text):
    note_path = "/notes/{}".format(note_id)
    existing_body = call_api("GET", note_path, query={"fields": "body"})["body"]
    call_api("PUT", note_path, payload={"body": join_appended_text(existing_body, text)})


def rename_note(note_id, new_title):
    call_api("PUT", "/notes/{}".format(note_id), payload={"title": new_title})


def read_body_from_stdin():
    if sys.stdin.isatty():
        return ""
    # Decode explicitly: the Windows console default is not UTF-8. "utf-8-sig" also
    # drops the byte-order mark that Windows PowerShell prepends when piping text.
    return sys.stdin.buffer.read().decode("utf-8-sig")


def require_text(text, description):
    if not text.strip():
        raise JoplinError("{} cannot be empty.".format(description))
    return text


def run_notebooks(arguments):
    for notebook in sorted(fetch_all_pages("/folders"), key=lambda n: n["title"].casefold()):
        print(notebook["title"])


def run_add(arguments):
    title = require_text(arguments.title, "The note title").strip()
    notebook_name = arguments.notebook or os.environ.get("JOPLIN_DEFAULT_NOTEBOOK") or None
    note_id = create_note(title, read_body_from_stdin(), notebook_name, arguments.tags)
    print("Created note '{}' (id {}){}.".format(
        title, note_id, " in '{}'".format(notebook_name) if notebook_name else ""
    ))


def run_append(arguments):
    # Check the input first so an empty append fails before any lookup.
    text = require_text(read_body_from_stdin(), "The text to append").strip("\r\n")
    note = find_note(arguments.note, arguments.notebook)
    append_to_note(note["id"], text)
    print("Appended to note '{}' (id {}).".format(note["title"], note["id"]))


def run_rename(arguments):
    new_title = require_text(arguments.new_title, "The new title").strip()
    note = find_note(arguments.note, arguments.notebook)
    rename_note(note["id"], new_title)
    print("Renamed note '{}' to '{}' (id {}).".format(note["title"], new_title, note["id"]))


def build_parser():
    parser = argparse.ArgumentParser(description="Create, append to, and rename Joplin notes.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    notebooks_parser = subcommands.add_parser("notebooks", help="List notebook names.")
    notebooks_parser.set_defaults(handler=run_notebooks)

    add_parser = subcommands.add_parser("add", help="Create a note; the body is read from stdin.")
    add_parser.add_argument("title")
    add_parser.add_argument("--notebook", help="Notebook name (default: $JOPLIN_DEFAULT_NOTEBOOK).")
    add_parser.add_argument("--tag", action="append", default=[], dest="tags", help="Repeatable.")
    add_parser.set_defaults(handler=run_add)

    note_help = "Note id (32 characters) or exact note title."
    notebook_help = "Notebook to look the note up in; needed when titles repeat."

    append_parser = subcommands.add_parser("append", help="Append stdin text to an existing note.")
    append_parser.add_argument("note", help=note_help)
    append_parser.add_argument("--notebook", help=notebook_help)
    append_parser.set_defaults(handler=run_append)

    rename_parser = subcommands.add_parser("rename", help="Change an existing note's title.")
    rename_parser.add_argument("note", help=note_help)
    rename_parser.add_argument("new_title")
    rename_parser.add_argument("--notebook", help=notebook_help)
    rename_parser.set_defaults(handler=run_rename)
    return parser


def run(arguments):
    arguments.handler(arguments)


def main():
    try:
        run(build_parser().parse_args())
    except JoplinError as error:
        print("Error: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
