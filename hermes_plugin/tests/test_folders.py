import pytest

from knowledge_hub.folders import FolderBrowser, PickerState

ROOTS = {"/vault/readonly": "ReadOnly", "/vault/readwrite": "ReadWrite"}


def make_vault(tmp_path):
    course = tmp_path / "ReadWrite" / "Year-1" / "Intro-to-Physics"
    for n in (1, 2, 10):
        (course / f"Lecture {n}").mkdir(parents=True)
    (course / "Lecture 1" / "Lecture1.pdf").write_bytes(b"%PDF")
    (course / "Lecture 1" / "notes.md").write_text("x")
    (course / ".hidden").mkdir()
    (tmp_path / "ReadOnly").mkdir()
    (tmp_path / "Private").mkdir()
    return FolderBrowser(tmp_path, ROOTS)


def test_top_level_lists_only_the_sandbox_roots(tmp_path):
    listing = make_vault(tmp_path).listing("")
    assert listing.folders == ["readonly", "readwrite"]
    assert listing.files == []


def test_listing_sorts_naturally_and_skips_hidden(tmp_path):
    listing = make_vault(tmp_path).listing("/vault/readwrite/Year-1/Intro-to-Physics")
    assert listing.folders == ["Lecture 1", "Lecture 2", "Lecture 10"]


def test_listing_shows_files(tmp_path):
    listing = make_vault(tmp_path).listing("/vault/readwrite/Year-1/Intro-to-Physics/Lecture 1")
    assert listing.folders == []
    assert listing.files == ["Lecture1.pdf", "notes.md"]


def test_child_and_parent(tmp_path):
    browser = make_vault(tmp_path)
    assert browser.child("", "readwrite") == "/vault/readwrite"
    assert browser.child("/vault/readwrite", "Year-1") == "/vault/readwrite/Year-1"
    assert browser.parent("/vault/readwrite/Year-1") == "/vault/readwrite"
    assert browser.parent("/vault/readwrite") == ""
    assert browser.parent("") == ""


def test_normalize_rejects_escapes_and_unknown_paths(tmp_path):
    browser = make_vault(tmp_path)
    assert browser.normalize("/vault/readwrite/Year-1/") == "/vault/readwrite/Year-1"
    assert browser.normalize("/vault/readwrite\\Year-1") == "/vault/readwrite/Year-1"
    assert browser.normalize("/vault/readwrite/../../Private") == ""
    assert browser.normalize("/etc") == ""
    assert browser.normalize("") == ""


def test_symlinks_pointing_outside_root_are_blocked(tmp_path, monkeypatch):
    from pathlib import Path

    browser = make_vault(tmp_path)
    escape = tmp_path / "ReadWrite" / "escape"
    outside = (tmp_path / "Private").resolve()
    try:
        escape.symlink_to(outside, target_is_directory=True)
    except OSError:
        escape.mkdir()
        real_resolve = Path.resolve
        monkeypatch.setattr(Path, "resolve", lambda self, *a, **kw: outside if self == escape else real_resolve(self, *a, **kw))
    assert "escape" not in browser.listing("/vault/readwrite").folders
    assert browser.host("/vault/readwrite/escape") is None
    assert browser.normalize("/vault/readwrite/escape") == "/vault/readwrite"


def test_normalize_falls_back_to_the_closest_existing_folder(tmp_path):
    browser = make_vault(tmp_path)
    assert browser.normalize("/vault/readwrite/does-not-exist") == "/vault/readwrite"
    assert browser.normalize("/vault/readwrite/Year-1/Intro-to-Physics/Lecture\\ 1") == \
        "/vault/readwrite/Year-1/Intro-to-Physics"
    assert browser.normalize("/vault/readwrite/Year-1/Intro-to-Physics/Lecture 1/Lecture1.pdf") == \
        "/vault/readwrite/Year-1/Intro-to-Physics/Lecture 1"


def test_state_navigates_by_button_presses(tmp_path):
    state = PickerState(make_vault(tmp_path), "/vault/readwrite/Year-1")
    keys = [b.key for b in state.buttons() if b.kind == "folder"]
    assert keys == ["f:0"]
    assert state.press("f:0") is None
    assert state.path == "/vault/readwrite/Year-1/Intro-to-Physics"
    assert state.press("up") is None
    assert state.path == "/vault/readwrite/Year-1"
    assert state.press("ok") == "ok"


def test_ok_is_disabled_at_top_level_and_up_too(tmp_path):
    state = PickerState(make_vault(tmp_path), "")
    by_key = {b.key: b for b in state.buttons()}
    assert by_key["ok"].disabled and by_key["up"].disabled
    assert state.press("ok") is None  # a stale click on a disabled button does nothing
    assert state.press("cancel") == "cancel"


def test_content_lists_path_and_files(tmp_path):
    state = PickerState(make_vault(tmp_path), "/vault/readwrite/Year-1/Intro-to-Physics/Lecture 1",
                        question="Which lecture?")
    text = state.content()
    assert text.startswith("Which lecture?")
    assert "/vault/readwrite/Year-1/Intro-to-Physics/Lecture 1" in text
    assert "📄 Lecture1.pdf" in text and "📄 notes.md" in text


def test_many_folders_page_with_prev_next(tmp_path):
    many = tmp_path / "ReadWrite" / "many"
    for n in range(45):
        (many / f"d{n}").mkdir(parents=True)
    state = PickerState(FolderBrowser(tmp_path, ROOTS), "/vault/readwrite/many")
    folders = [b for b in state.buttons() if b.kind == "folder"]
    assert len(folders) == 20 and folders[0].label == "d0"
    assert len(state.buttons()) <= 25
    by_key = {b.key: b for b in state.buttons()}
    assert by_key["prev"].disabled and not by_key["next"].disabled
    state.press("next")
    state.press("next")
    folders = [b for b in state.buttons() if b.kind == "folder"]
    assert [b.label for b in folders] == [f"d{n}" for n in range(40, 45)]
    assert {b.key: b for b in state.buttons()}["next"].disabled
    state.press("f:1")
    assert state.path == "/vault/readwrite/many/d41"
    assert state.page == 0


def test_long_listings_stay_under_discord_limits(tmp_path):
    big = tmp_path / "ReadWrite" / "big"
    big.mkdir(parents=True)
    for n in range(40):
        (big / f"{'x' * 90}{n}.pdf").write_bytes(b"")
    (big / ("y" * 120)).mkdir()
    state = PickerState(FolderBrowser(tmp_path, ROOTS), "/vault/readwrite/big")
    assert len(state.content()) <= 2000
    assert "…and 25 more" in state.content()
    assert all(len(b.label) <= 80 for b in state.buttons())


def test_final_text(tmp_path):
    state = PickerState(make_vault(tmp_path), "/vault/readwrite/Year-1")
    assert "/vault/readwrite/Year-1" in state.final_text("ok")
    assert "Cancelled" in state.final_text("cancel")
    assert "expired" in state.final_text("timeout")
