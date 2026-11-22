
import pytest

from knowledgehub.lectures import _write, refresh


@pytest.fixture
def school(cfg):
    course = cfg.vault / "ReadWrite/Year-1/Intro-to-Physics"
    for n in (1, 2):
        (course / f"Lecture {n}").mkdir(parents=True)
        (course / f"Lecture {n}" / f"Lecture{n}.pdf").write_bytes(b"%PDF")
    lecture1 = course / "Lecture 1"
    (lecture1 / "Lecture1_practical.md").write_text("---\ntopic: Motion quiz\n---\n# P\n", encoding="utf-8")
    (lecture1 / "Lecture1_study.md").write_text(
        "---\ncourse: PHYS101 Intro to Physics\ntopic: Kinematics\n---\n# S\n", encoding="utf-8")
    (lecture1 / "Lecture1_visual.md").write_text("# V\n", encoding="utf-8")
    (lecture1 / "Cheat sheet.md").write_text("# C\n", encoding="utf-8")
    (lecture1 / "Lecture 1.md").write_text(
        "---\ncourse: PHYS101 Intro to Physics\nlecture: 1\ntopic: Kinematics & Motion\n"
        "type: lecture\ntags: [lecture-hub]\n---\n\n# Lecture 1: Kinematics & Motion\n\n[[Lecture 2]] →\n\n"
        "Old text.\n\n![[Lecture1.pdf]]\n", encoding="utf-8")
    return cfg, course


BASE = "ReadWrite/Year-1/Intro-to-Physics"


def test_lecture_notes_link_every_sheet_and_neighbour(school):
    cfg, course = school
    written = refresh(cfg)
    assert sorted(p.name for p in written) == ["Intro to Physics.md", "Lecture 1.md", "Lecture 2.md"]
    assert (course / "Lecture 1" / "Lecture 1.md").read_text(encoding="utf-8") == (
        "---\ncourse: PHYS101 Intro to Physics\nlecture: 1\ntopic: Kinematics & Motion\n"
        "type: lecture\ntags: [lecture-hub]\ncssclasses: [study]\n---\n\n"
        "# Lecture 1: Kinematics & Motion\n\n"
        f"↑ [[{BASE}/Intro to Physics|Intro to Physics]]\n\n"
        f"[[{BASE}/Lecture 2/Lecture 2|Lecture 2]] →\n\n"
        f"[[{BASE}/Lecture 1/Lecture1_study|Study guide]] · [[{BASE}/Lecture 1/Lecture1_visual|Visual notes]]"
        f" · [[{BASE}/Lecture 1/Lecture1_practical|Practical]] · [[{BASE}/Lecture 1/Cheat sheet|Cheat sheet]]\n\n"
        f"![[{BASE}/Lecture 1/Lecture1.pdf]]\n\n## My Notes\n")
    second = (course / "Lecture 2" / "Lecture 2.md").read_text(encoding="utf-8")
    assert "course: Intro to Physics\nlecture: 2\ntype: lecture" in second  # course from the folder name
    assert f"← [[{BASE}/Lecture 1/Lecture 1|Lecture 1]]" in second and "No study notes yet." in second
    assert refresh(cfg) == []  # nothing changed, nothing written


def test_a_new_lecture_updates_its_neighbour_and_keeps_my_notes(school):
    cfg, course = school
    refresh(cfg)
    hub = course / "Lecture 2" / "Lecture 2.md"
    hub.write_text(hub.read_text(encoding="utf-8") + "\nAsk about Q3.\n", encoding="utf-8")
    (course / "Lecture 3").mkdir()
    (course / "Lecture 3" / "Lecture3_practical.md").write_text("---\ntopic: Forces\n---\n", encoding="utf-8")
    written = sorted(p.parent.name for p in refresh(cfg))
    assert written == ["Intro-to-Physics", "Lecture 2", "Lecture 3"]  # the course note lists Lecture 3 too
    text = hub.read_text(encoding="utf-8")
    assert f"[[{BASE}/Lecture 3/Lecture 3|Lecture 3]] →" in text and text.endswith("## My Notes\n\nAsk about Q3.\n")
    assert "# Lecture 3: Forces" in (course / "Lecture 3" / "Lecture 3.md").read_text(encoding="utf-8")


def test_sheets_written_later_replace_the_folder_name_course(school):
    cfg, course = school
    refresh(cfg)
    hub = course / "Lecture 2" / "Lecture 2.md"
    assert "course: Intro to Physics\n" in hub.read_text(encoding="utf-8")  # no sheets yet: the folder name
    (course / "Lecture 2" / "Lecture2_study.md").write_text(
        "---\ncourse: PHYS101 Intro to Physics\ntopic: Forces\n---\n# S\n", encoding="utf-8")
    refresh(cfg)
    assert "course: PHYS101 Intro to Physics\nlecture: 2\ntopic: Forces\n" in hub.read_text(encoding="utf-8")
    hub.write_text(hub.read_text(encoding="utf-8").replace("PHYS101 Intro to Physics", "Motion and Forces"),
                   encoding="utf-8")
    refresh(cfg)
    assert "course: Motion and Forces\n" in hub.read_text(encoding="utf-8")  # a name of the user's own stays


def test_sheet_links_get_full_paths_per_course(school):
    cfg, course = school
    other = cfg.vault / "ReadWrite/Year-1/World-History"
    (other / "Lecture 1").mkdir(parents=True)
    (other / "Lecture 1" / "Lecture1.pdf").write_bytes(b"%PDF")
    (other / "Lecture 1" / "Lecture1_study.md").write_text('---\nsource: "[[Lecture 1]]"\n---\n![[Lecture1.pdf]]\n',
                                                          encoding="utf-8")
    study = course / "Lecture 1" / "Lecture1_study.md"
    study.write_text('---\nsource: "[[Lecture 1]]"\n---\n# S\nSee [[Lecture1_practical#Q3]], [[Lecture 2|next]], '
                     "![[Lecture1.pdf|300]], [[Nowhere]] and "
                     f"[[{BASE}/Lecture 2/Lecture 2|already]].\n", encoding="utf-8")
    mine = course / "Lecture 1" / "My own notes.md"  # not ignored by ingest: the user's, never rewritten
    mine.write_text("[[Lecture 1]]\n", encoding="utf-8")

    refresh(cfg)
    assert study.read_text(encoding="utf-8") == (
        f'---\nsource: "[[{BASE}/Lecture 1/Lecture 1|Lecture 1]]"\n---\n# S\n'
        f"See [[{BASE}/Lecture 1/Lecture1_practical#Q3|Lecture1_practical#Q3]], [[{BASE}/Lecture 2/Lecture 2|next]], "
        f"![[{BASE}/Lecture 1/Lecture1.pdf|300]], [[Nowhere]] and [[{BASE}/Lecture 2/Lecture 2|already]].\n")
    prob = "ReadWrite/Year-1/World-History/Lecture 1"
    assert (other / "Lecture 1" / "Lecture1_study.md").read_text(encoding="utf-8") == (
        f'---\nsource: "[[{prob}/Lecture 1|Lecture 1]]"\n---\n![[{prob}/Lecture1.pdf]]\n')
    assert mine.read_text(encoding="utf-8") == "[[Lecture 1]]\n"
    assert refresh(cfg) == []




def test_ambiguous_names_within_a_course_are_left_alone(school):
    cfg, course = school
    (course / "Lecture 2" / "Lecture1_visual.md").write_text("# copy\n", encoding="utf-8")  # same name twice
    practical = course / "Lecture 1" / "Lecture1_practical.md"
    practical.write_text("---\ntopic: Motion quiz\n---\n[[Lecture1_visual]]\n", encoding="utf-8")
    refresh(cfg)
    assert practical.read_text(encoding="utf-8").endswith("\n[[Lecture1_visual]]\n")


BIO = "ReadWrite/Year-1/Modern-Biology"


def test_asset_folders_named_like_lectures_are_not_lectures(school):
    cfg, course = school
    for assets in ("_slides", "_figures"):
        (course / assets / "Lecture1").mkdir(parents=True)
    written = refresh(cfg)
    assert not any("_slides" in p.as_posix() or "_figures" in p.as_posix() for p in written)
    assert "_figures" not in (course / "Intro to Physics.md").read_text(encoding="utf-8")
    assert "Lecture 2|Lecture 2]] →" in (course / "Lecture 1" / "Lecture 1.md").read_text(encoding="utf-8")


def test_lectures_in_week_folders_without_a_space_chain_across_weeks(school):
    cfg, _ = school
    bio = cfg.vault / BIO
    for week, n in (("Week1", 1), ("Week1", 2), ("Week2", 3)):
        (bio / week / f"Lecture{n}").mkdir(parents=True)
        (bio / week / f"Lecture{n}" / f"lecture0{n}-handout.pdf").write_bytes(b"%PDF")
    lecture1 = bio / "Week1" / "Lecture1"
    (lecture1 / "Lecture1_study.md").write_text('---\nsource: "[[Lecture1]]"\n---\n# S\n', encoding="utf-8")
    (lecture1 / "Lecture1.md").write_text("![[lecture01-handout.pdf]]\n", encoding="utf-8")  # the user's own note

    written = refresh(cfg)
    assert sorted(p.relative_to(bio).as_posix() for p in written if p.is_relative_to(bio)) == [
        "Modern Biology.md", "Week1/Lecture1/Lecture 1.md", "Week1/Lecture1/Lecture1_study.md",
        "Week1/Lecture2/Lecture 2.md", "Week2/Lecture3/Lecture 3.md"]
    first = (lecture1 / "Lecture 1.md").read_text(encoding="utf-8")
    assert "course: Modern Biology\nlecture: 1\n" in first  # the course folder, not "Week1"
    assert f"[[{BIO}/Week1/Lecture2/Lecture 2|Lecture 2]] →" in first
    assert (f"[[{BIO}/Week1/Lecture1/Lecture1_study|Study guide]] · "
            f"[[{BIO}/Week1/Lecture1/Lecture1|Lecture1]]") in first
    assert f"![[{BIO}/Week1/Lecture1/lecture01-handout.pdf]]" in first
    second = (bio / "Week1" / "Lecture2" / "Lecture 2.md").read_text(encoding="utf-8")
    assert f"[[{BIO}/Week2/Lecture3/Lecture 3|Lecture 3]] →" in second  # across the week boundary
    assert (lecture1 / "Lecture1.md").read_text(encoding="utf-8") == "![[lecture01-handout.pdf]]\n"
    assert refresh(cfg) == []


def test_course_note_links_every_lecture_and_keeps_my_notes(school):
    cfg, course = school
    (cfg.vault / "ReadWrite/Year-1/Empty-Course").mkdir()
    refresh(cfg)
    note = course / "Intro to Physics.md"
    assert note.read_text(encoding="utf-8") == (
        "---\ncourse: PHYS101 Intro to Physics\ntype: course\ntags: [course-hub]\ncssclasses: [study]\n---\n\n"
        "# PHYS101 Intro to Physics\n\n"
        f"- [[{BASE}/Lecture 1/Lecture 1|Lecture 1]] — Kinematics & Motion\n"
        f"- [[{BASE}/Lecture 2/Lecture 2|Lecture 2]]\n\n## My Notes\n")
    assert not list((cfg.vault / "ReadWrite/Year-1/Empty-Course").iterdir())  # no lectures, no course note
    note.write_text(note.read_text(encoding="utf-8") + "\nExam in May.\n", encoding="utf-8")
    (course / "Lecture 3").mkdir()
    refresh(cfg)
    text = note.read_text(encoding="utf-8")
    assert f"- [[{BASE}/Lecture 3/Lecture 3|Lecture 3]]\n" in text and text.endswith("## My Notes\n\nExam in May.\n")
    assert refresh(cfg) == []


def test_a_note_of_the_users_with_the_course_name_is_left_alone(school):
    cfg, course = school
    mine = course / "Intro to Physics.md"
    mine.write_text("# My own overview\n", encoding="utf-8")
    written = refresh(cfg)
    assert mine not in written and mine.read_text(encoding="utf-8") == "# My own overview\n"
    assert f"↑ [[{BASE}/Intro to Physics|Intro to Physics]]" in \
        (course / "Lecture 1" / "Lecture 1.md").read_text(encoding="utf-8")


def test_writes_are_refused_outside_lecture_notes(school):
    cfg, course = school
    for bad in (course / "Lecture 1" / "Lecture1_study.md",  # a sheet, without sheet=True
                course / "Lecture 1" / "Lecture 2.md",  # wrong folder
                cfg.memory_root / "Lecture 1.md"):  # not under a school dir
        with pytest.raises(PermissionError):
            _write(cfg, bad, "x")
    _write(cfg, course / "Lecture 1" / "Lecture1_study.md", "x", sheet=True)
    for bad in (course / "Lecture 1" / "Lecture1_mynotes.md", course / "Lecture 1" / "Cheat sheet.md"):
        with pytest.raises(PermissionError):  # the user's own notes
            _write(cfg, bad, "x", sheet=True)
    nested = cfg.vault / BIO / "Week1" / "Lecture1"
    nested.mkdir(parents=True)
    _write(cfg, nested / "Lecture 1.md", "x")  # a "LectureN" folder, nested in a week, is fine
    with pytest.raises(PermissionError):
        _write(cfg, cfg.vault / BIO / "Week1" / "Lecture 1.md", "x")  # the week folder is not a lecture
    _write(cfg, course / "Intro to Physics.md", "x")  # the course note
    for bad in (course / "Notes.md", cfg.vault / BIO / "Week1" / "Modern Biology.md"):
        with pytest.raises(PermissionError):
            _write(cfg, bad, "x")


def test_lecture_notes_page_is_linked_first(school):
    cfg, course = school
    (course / "Lecture 1" / "Lecture1_notes.md").write_text(
        "---\ntype: lecture\ncssclasses: [lecture]\n---\n# N\n", encoding="utf-8")
    refresh(cfg)
    hub = (course / "Lecture 1" / "Lecture 1.md").read_text(encoding="utf-8")
    assert f"[[{BASE}/Lecture 1/Lecture1_notes|Lecture notes]] · [[{BASE}/Lecture 1/Lecture1_study|" in hub
    assert (course / "Lecture 1" / "Lecture1_notes.md").read_text(encoding="utf-8").startswith(
        "---\ntype: lecture\ncssclasses: [lecture]\n---")


def test_my_notes_file_is_linked_last_and_never_rewritten(school):
    cfg, course = school
    mine = course / "Lecture 1" / "Lecture1_mynotes.md"
    text = "# my scribbles\n\nsee [[Lecture 1]] and ![[Lecture1.pdf]]\n"
    mine.write_text(text, encoding="utf-8")
    written = refresh(cfg)
    assert mine not in written
    assert mine.read_text(encoding="utf-8") == text
    hub = (course / "Lecture 1" / "Lecture 1.md").read_text(encoding="utf-8")
    assert f"[[{BASE}/Lecture 1/Lecture1_practical|Practical]] · [[{BASE}/Lecture 1/Lecture1_mynotes|My notes]]" in hub
