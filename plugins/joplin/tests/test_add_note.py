import contextlib
import io
import json
import os
import socket
import sys
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "add-note" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import add_note  # noqa: E402

VALID_TOKEN = "test-token-value"
PAGE_SIZE = 2  # Small on purpose so pagination is exercised.


class FakeJoplinState:
    def __init__(self):
        self.notebooks = []
        self.tags = []
        self.notes = []
        self.tag_links = []

    def live_notes(self):
        return [note for note in self.notes if not note.get("deleted_time")]

    def find_note(self, note_id):
        return next((note for note in self.notes if note["id"] == note_id), None)


class FakeJoplinHandler(BaseHTTPRequestHandler):
    state = None

    def log_message(self, *args):
        pass

    def _respond(self, status, body):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _paginate(self, items, query):
        page = int(query.get("page", ["1"])[0])
        start = (page - 1) * PAGE_SIZE
        return {"items": items[start:start + PAGE_SIZE], "has_more": start + PAGE_SIZE < len(items)}

    def _handle(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("token", [""])[0] != VALID_TOKEN:
            return self._respond(403, {"error": "Invalid token"})

        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length)) if length else None
        state = self.state

        if parsed.path == "/folders" and self.command == "GET":
            return self._respond(200, self._paginate(state.notebooks, query))
        if parsed.path == "/tags" and self.command == "GET":
            return self._respond(200, self._paginate(state.tags, query))
        if parsed.path == "/tags" and self.command == "POST":
            tag = {"id": "tag{}".format(len(state.tags)), "title": payload["title"]}
            state.tags.append(tag)
            return self._respond(200, tag)
        if parsed.path == "/notes" and self.command == "POST":
            note = dict(payload, id="note{}".format(len(state.notes)))
            state.notes.append(note)
            return self._respond(200, note)
        if parsed.path.startswith("/tags/") and parsed.path.endswith("/notes"):
            state.tag_links.append((parsed.path.split("/")[2], payload["id"]))
            return self._respond(200, {})
        if parsed.path == "/notes" and self.command == "GET":
            return self._respond(200, self._paginate(state.live_notes(), query))
        if parsed.path.startswith("/folders/") and parsed.path.endswith("/notes"):
            notebook_id = parsed.path.split("/")[2]
            notes = [note for note in state.live_notes() if note.get("parent_id") == notebook_id]
            return self._respond(200, self._paginate(notes, query))
        if parsed.path.startswith("/notes/"):
            note = state.find_note(parsed.path.split("/")[2])
            if note is None:
                return self._respond(404, {"error": "not found"})
            if self.command == "PUT":
                note.update(payload)
            return self._respond(200, note)
        return self._respond(404, {"error": "not found"})

    do_GET = do_POST = do_PUT = _handle


class AddNoteTests(unittest.TestCase):
    def setUp(self):
        self.state = FakeJoplinState()
        handler = type("Handler", (FakeJoplinHandler,), {"state": self.state})
        self.server = HTTPServer((add_note.HOST, 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

        environment = {"JOPLIN_TOKEN": VALID_TOKEN, "JOPLIN_PORT": str(self.server.server_port)}
        patcher = mock.patch.dict(os.environ, environment)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("JOPLIN_DEFAULT_NOTEBOOK", None)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()

    def add_notebook(self, title):
        self.state.notebooks.append({"id": "nb{}".format(len(self.state.notebooks)), "title": title})

    def seed_note(self, title, body="", notebook_id="nb0", trashed=False):
        note = {
            "id": "{:032x}".format(len(self.state.notes) + 1),
            "title": title,
            "body": body,
            "parent_id": notebook_id,
            "deleted_time": 1 if trashed else 0,
        }
        self.state.notes.append(note)
        return note["id"]

    def run_command(self, argv, body=""):
        arguments = add_note.build_parser().parse_args(argv)
        output = io.StringIO()
        with mock.patch.object(add_note, "read_body_from_stdin", return_value=body):
            with contextlib.redirect_stdout(output):
                add_note.run(arguments)
        return output.getvalue()

    def test_notebooks_lists_all_pages_sorted(self):
        for title in ["Work", "archive", "Personal"]:
            self.add_notebook(title)
        self.assertEqual(self.run_command(["notebooks"]).splitlines(), ["archive", "Personal", "Work"])

    def test_add_creates_note_in_named_notebook_ignoring_case(self):
        for title in ["Work", "Personal", "Inbox"]:
            self.add_notebook(title)
        self.run_command(["add", "Title", "--notebook", "inbox"], body="text")
        self.assertEqual(self.state.notes[0]["parent_id"], "nb2")

    def test_add_preserves_quotes_newlines_and_unicode_in_body(self):
        body = 'He said "hi"\nline two \\ backslash\n日本語 café ✓'
        self.run_command(["add", "Title"], body=body)
        self.assertEqual(self.state.notes[0]["body"], body)

    def test_stdin_body_drops_byte_order_mark_but_keeps_unicode(self):
        fake_stdin = mock.Mock()
        fake_stdin.isatty.return_value = False
        fake_stdin.buffer = io.BytesIO("﻿café ✓".encode("utf-8"))
        with mock.patch.object(sys, "stdin", fake_stdin):
            self.assertEqual(add_note.read_body_from_stdin(), "café ✓")

    def test_add_without_notebook_omits_parent_id(self):
        self.run_command(["add", "Title"], body="text")
        self.assertNotIn("parent_id", self.state.notes[0])

    def test_default_notebook_comes_from_environment(self):
        self.add_notebook("Inbox")
        with mock.patch.dict(os.environ, {"JOPLIN_DEFAULT_NOTEBOOK": "Inbox"}):
            self.run_command(["add", "Title"], body="text")
        self.assertEqual(self.state.notes[0]["parent_id"], "nb0")

    def test_add_reuses_existing_tag_and_creates_missing_one(self):
        self.state.tags.append({"id": "existing", "title": "Ideas"})
        self.run_command(["add", "Title", "--tag", "ideas", "--tag", "new"], body="text")
        self.assertEqual([tag["title"] for tag in self.state.tags], ["Ideas", "new"])
        self.assertEqual(self.state.tag_links, [("existing", "note0"), ("tag1", "note0")])

    def test_unknown_notebook_fails_before_creating_a_note(self):
        self.add_notebook("Work")
        with self.assertRaisesRegex(add_note.JoplinError, "No notebook named 'Nope'"):
            self.run_command(["add", "Title", "--notebook", "Nope"], body="text")
        self.assertEqual(self.state.notes, [])

    def test_duplicate_notebook_names_are_rejected(self):
        self.add_notebook("Work")
        self.add_notebook("work")
        with self.assertRaisesRegex(add_note.JoplinError, "2 notebooks are named"):
            self.run_command(["add", "Title", "--notebook", "Work"], body="text")
        self.assertEqual(self.state.notes, [])

    def test_empty_title_is_rejected(self):
        with self.assertRaisesRegex(add_note.JoplinError, "title cannot be empty"):
            self.run_command(["add", "   "], body="text")

    def test_missing_token_gives_setup_instructions(self):
        with mock.patch.dict(os.environ, {"JOPLIN_TOKEN": ""}):
            with self.assertRaisesRegex(add_note.JoplinError, "JOPLIN_TOKEN is not set"):
                self.run_command(["notebooks"])

    def test_wrong_token_error_does_not_leak_the_token(self):
        with mock.patch.dict(os.environ, {"JOPLIN_TOKEN": "wrong-secret-token"}):
            with self.assertRaises(add_note.JoplinError) as context:
                self.run_command(["notebooks"])
        self.assertIn("rejected the token", str(context.exception))
        self.assertNotIn("wrong-secret-token", str(context.exception))

    def test_unreachable_joplin_gives_actionable_error(self):
        with socket.socket() as probe:
            probe.bind((add_note.HOST, 0))
            unused_port = probe.getsockname()[1]
        with mock.patch.dict(os.environ, {"JOPLIN_PORT": str(unused_port)}):
            with self.assertRaisesRegex(add_note.JoplinError, "Cannot reach Joplin"):
                self.run_command(["notebooks"])

    def test_invalid_port_is_rejected(self):
        for bad_port in ["abc", "0", "70000", "80; rm -rf"]:
            with self.subTest(port=bad_port), mock.patch.dict(os.environ, {"JOPLIN_PORT": bad_port}):
                with self.assertRaisesRegex(add_note.JoplinError, "JOPLIN_PORT"):
                    self.run_command(["notebooks"])

    def test_join_appended_text_separates_with_one_blank_line(self):
        self.assertEqual(add_note.join_appended_text("first", "second"), "first\n\nsecond")
        self.assertEqual(add_note.join_appended_text("first\n", "second"), "first\n\nsecond")
        self.assertEqual(add_note.join_appended_text("", "second"), "second")

    def test_append_by_title_adds_text_and_keeps_existing_body(self):
        self.seed_note("Log", body="first entry")
        output = self.run_command(["append", "log"], body="second entry\n")
        self.assertEqual(self.state.notes[0]["body"], "first entry\n\nsecond entry")
        self.assertIn("Appended to note 'Log'", output)

    def test_append_by_id_does_not_need_a_title_match(self):
        note_id = self.seed_note("Log", body="first")
        self.run_command(["append", note_id], body="second")
        self.assertEqual(self.state.notes[0]["body"], "first\n\nsecond")

    def test_append_finds_note_beyond_the_first_page_of_results(self):
        for index in range(5):
            self.seed_note("Filler {}".format(index))
        self.seed_note("Target", body="old")
        self.run_command(["append", "Target"], body="new")
        self.assertEqual(self.state.notes[-1]["body"], "old\n\nnew")

    def test_append_with_notebook_picks_the_right_note_among_duplicates(self):
        self.add_notebook("Work")
        self.add_notebook("Personal")
        self.seed_note("Todo", body="work", notebook_id="nb0")
        self.seed_note("Todo", body="home", notebook_id="nb1")
        self.run_command(["append", "Todo", "--notebook", "personal"], body="more")
        self.assertEqual([note["body"] for note in self.state.notes], ["work", "home\n\nmore"])

    def test_ambiguous_title_lists_ids_and_notebooks_and_changes_nothing(self):
        self.add_notebook("Work")
        self.add_notebook("Personal")
        first_id = self.seed_note("Todo", body="work", notebook_id="nb0")
        self.seed_note("Todo", body="home", notebook_id="nb1")
        with self.assertRaises(add_note.JoplinError) as context:
            self.run_command(["append", "Todo"], body="more")
        self.assertIn("2 notes are titled 'Todo'", str(context.exception))
        self.assertIn("{} (notebook: Work)".format(first_id), str(context.exception))
        self.assertIn("(notebook: Personal)", str(context.exception))
        self.assertEqual([note["body"] for note in self.state.notes], ["work", "home"])

    def test_default_notebook_setting_does_not_narrow_note_lookup(self):
        self.add_notebook("Inbox")
        self.add_notebook("Elsewhere")
        self.seed_note("Log", body="a", notebook_id="nb1")
        with mock.patch.dict(os.environ, {"JOPLIN_DEFAULT_NOTEBOOK": "Inbox"}):
            self.run_command(["append", "Log"], body="b")
        self.assertEqual(self.state.notes[0]["body"], "a\n\nb")

    def test_unknown_title_and_unknown_id_are_reported(self):
        self.seed_note("Log")
        with self.assertRaisesRegex(add_note.JoplinError, "No note titled 'Missing'"):
            self.run_command(["append", "Missing"], body="x")
        with self.assertRaisesRegex(add_note.JoplinError, "No note with id " + "f" * 32):
            self.run_command(["append", "f" * 32], body="x")

    def test_trashed_note_is_rejected_by_id_and_hidden_from_title_lookup(self):
        note_id = self.seed_note("Old", body="keep", trashed=True)
        with self.assertRaisesRegex(add_note.JoplinError, "is in the trash"):
            self.run_command(["append", note_id], body="x")
        with self.assertRaisesRegex(add_note.JoplinError, "No note titled 'Old'"):
            self.run_command(["rename", "Old", "New"])
        self.assertEqual(self.state.notes[0]["body"], "keep")
        self.assertEqual(self.state.notes[0]["title"], "Old")

    def test_notebook_option_is_rejected_when_note_is_given_by_id(self):
        self.add_notebook("Work")
        note_id = self.seed_note("Log")
        with self.assertRaisesRegex(add_note.JoplinError, "only applies when the note is given by title"):
            self.run_command(["append", note_id, "--notebook", "Work"], body="x")

    def test_empty_append_is_rejected_and_changes_nothing(self):
        self.seed_note("Log", body="keep")
        with self.assertRaisesRegex(add_note.JoplinError, "text to append cannot be empty"):
            self.run_command(["append", "Log"], body="  \n")
        self.assertEqual(self.state.notes[0]["body"], "keep")

    def test_rename_by_title_changes_only_the_title(self):
        self.seed_note("Old title", body="body stays")
        output = self.run_command(["rename", "old TITLE", "New title"])
        self.assertEqual(self.state.notes[0]["title"], "New title")
        self.assertEqual(self.state.notes[0]["body"], "body stays")
        self.assertIn("Renamed note 'Old title' to 'New title'", output)

    def test_rename_by_id_works(self):
        note_id = self.seed_note("Old title")
        self.run_command(["rename", note_id, "New title"])
        self.assertEqual(self.state.notes[0]["title"], "New title")

    def test_rename_rejects_empty_new_title(self):
        self.seed_note("Keep me")
        with self.assertRaisesRegex(add_note.JoplinError, "new title cannot be empty"):
            self.run_command(["rename", "Keep me", "   "])
        self.assertEqual(self.state.notes[0]["title"], "Keep me")

    def test_main_prints_error_and_returns_nonzero(self):
        errors = io.StringIO()
        with mock.patch.dict(os.environ, {"JOPLIN_TOKEN": ""}), \
                mock.patch.object(sys, "argv", ["add_note.py", "notebooks"]), \
                contextlib.redirect_stderr(errors):
            exit_code = add_note.main()
        self.assertEqual(exit_code, 1)
        self.assertIn("Error: JOPLIN_TOKEN is not set", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
