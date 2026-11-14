#!/usr/bin/env python3
"""Create notes in Joplin through its local Data API (Web Clipper service).

Configuration comes from environment variables so the token never appears on a
command line or in output:
    JOPLIN_TOKEN             required, from Joplin > Options > Web Clipper
    JOPLIN_PORT              optional, defaults to 41184
    JOPLIN_DEFAULT_NOTEBOOK  optional, used when --notebook is not given

Usage:
    add_note.py notebooks
    add_note.py add TITLE [--notebook NAME] [--tag TAG ...]   (body read from stdin)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HOST = "127.0.0.1"  # Fixed on purpose: the note content and token must never leave this machine.
DEFAULT_PORT = 41184
REQUEST_TIMEOUT_SECONDS = 10


class JoplinError(Exception):
    """A problem the user can act on; the message is safe to print."""


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
        raise JoplinError(
            "Joplin returned HTTP {} for {} {}.".format(error.code, method, path)
        ) from None
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


def fetch_all_pages(path):
    items = []
    page = 1
    while True:
        result = call_api("GET", path, query={"page": page})
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


def read_body_from_stdin():
    if sys.stdin.isatty():
        return ""
    # Decode explicitly: the Windows console default is not UTF-8. "utf-8-sig" also
    # drops the byte-order mark that Windows PowerShell prepends when piping text.
    return sys.stdin.buffer.read().decode("utf-8-sig")


def build_parser():
    parser = argparse.ArgumentParser(description="Create notes in Joplin.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("notebooks", help="List notebook names.")

    add_parser = subcommands.add_parser("add", help="Create a note; the body is read from stdin.")
    add_parser.add_argument("title")
    add_parser.add_argument("--notebook", help="Notebook name (default: $JOPLIN_DEFAULT_NOTEBOOK).")
    add_parser.add_argument("--tag", action="append", default=[], dest="tags", help="Repeatable.")
    return parser


def run(arguments):
    if arguments.command == "notebooks":
        for notebook in sorted(fetch_all_pages("/folders"), key=lambda n: n["title"].casefold()):
            print(notebook["title"])
        return

    title = arguments.title.strip()
    if not title:
        raise JoplinError("The note title cannot be empty.")
    notebook_name = arguments.notebook or os.environ.get("JOPLIN_DEFAULT_NOTEBOOK") or None
    note_id = create_note(title, read_body_from_stdin(), notebook_name, arguments.tags)
    print("Created note '{}' (id {}){}.".format(
        title, note_id, " in '{}'".format(notebook_name) if notebook_name else ""
    ))


def main():
    try:
        run(build_parser().parse_args())
    except JoplinError as error:
        print("Error: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
