"""Prompt text. Kept short and literal: small local models follow plain instructions best."""

from __future__ import annotations

from datetime import date, timedelta

MEMORY_SYSTEM = ("You turn a short message into memory records for a personal assistant. "
                 "Reply with JSON only, following the schema.")


MEMORY_CALENDAR_DAYS = 31


def _next_day_of_month(today: date, day: int) -> date:
    """The next date after today that falls on `day` of a month (for the worked example)."""
    d = today + timedelta(days=1)
    while d.day != day:
        d += timedelta(days=1)
    return d


def _idea_rules(ideas, only_idea: bool) -> str:
    known = "\n".join(f"- {idea_id}: {title}: {gist}".rstrip(": ") for idea_id, title, gist in ideas) or "- (none yet)"
    first = ("This message is an idea: return exactly one item of kind idea for the whole message (no tasks or "
             "events).\n" if only_idea else "")
    return (
        f"{first}For an idea: text is \"\"; title is a short name for it (2 to 6 words, e.g. \"Plant-watering "
        "robot\"); idea_ref is the id of an existing idea from the list below when the message adds to that idea "
        '(talks about the same thing, maybe under another name), else "". At most one idea per message. For '
        'other kinds title and idea_ref are "".\n'
        f"Existing ideas:\n{known}\n"
    )


def memory_prompt(message: str, today: date, ideas=(), allow_ideas: bool = True, only_idea: bool = False) -> str:
    """`ideas`: (id, title, gist) of the user's open ideas, so a follow-up can name the one it adds to.
    `allow_ideas=False` leaves the idea kind out (`memory-add --no-ideas`)."""
    # Small models resolve "Friday" / "the 20th" reliably only with a calendar to copy from and a worked
    # example whose dates are real dates relative to today.
    days = "\n".join(f"- {d:%a} {d.isoformat()}"
                     for d in (today + timedelta(days=n) for n in range(1, MEMORY_CALENDAR_DAYS + 1)))
    tomorrow, twentieth = today + timedelta(days=1), _next_day_of_month(today, 20)
    tuesday = today + timedelta(days=(1 - today.weekday()) % 7)  # the first Tuesday from today
    example = (
        '{"items": [{"kind": "task", "text": "Call the dentist", "due": "' + tomorrow.isoformat() + '", "time": "", '
        '"repeat": ""}, '
        '{"kind": "event", "text": "Exam", "due": "' + twentieth.isoformat() + '", "time": "09:30", "repeat": ""}, '
        '{"kind": "event", "text": "Physics lab", "due": "' + tuesday.isoformat() + '", "time": "10:00", '
        '"repeat": "every week on Tuesday"}], "is_question": false}'
    )
    return (
        f"Today is {today:%A} {today.isoformat()}.\nCalendar for the next month:\n{days}\n\n"
        "Turn the user's message into memory items. Kinds:\n"
        "- task: something the user has to do, with or without a date or time (deadlines, errands, "
        '"buy milk friday", "submit the report by the 20th", "gym at 6")\n'
        "- event: only a fixed occasion the user attends or that happens to them, such as an exam, lecture, lab, "
        "appointment, meeting, flight, party or birthday\n"
        "When unsure between task and event, use task.\n"
        + ("- idea: something the user thought up and wants to keep exploring (a game, app, project, invention, "
           'plan); usually long and descriptive, often "what if…", "idea:", "I could make…"; never has a due date\n'
           if allow_ideas or only_idea else "")
        + (_idea_rules(ideas, only_idea) if allow_ideas or only_idea else "")
        + "Anything else (things about the user such as preferences, small talk) is not an item: leave it out.\n"
        "Split several things into several items. text: short, in the user's words, WITHOUT the date or "
        'words like "by friday" / "on the 20th" (the date goes in due).\n'
        'due: the date as YYYY-MM-DD, copied from the calendar above (or worked out the same way for later '
        'dates), or "" when the message gives no date. Never invent a date. Dates the user writes in numbers are '
        'day first: "05/10", "5.10" or "05/10/2026" mean 5 October.\n'
        'time: the time of day as HH:MM in 24-hour form ("2pm" -> "14:00", "9.30am" -> "09:30"), or "" when the '
        "message gives no time. Keep the time out of text too. A time with no day means today: then due is "
        "today's date.\n"
        'repeat: "" for a one-off. For something that repeats, one of: "every day", "every weekday", '
        '"every week", "every 2 weeks", "every week on Tuesday", "every week on Monday, Thursday", "every month"; '
        "then due is the first date it happens. Keep the repeat words out of text.\n"
        "is_question: true when the user is asking something rather than telling you something to remember; "
        "then items is empty.\n\n"
        'Example message: "remind me to call the dentist tomorrow, my exam is on the 20th at 9:30, I have '
        'physics lab every Tuesday at 10, and I\'m vegetarian"\n'
        f"Example answer: {example}\n\n"
        f"Message:\n{message}"
    )


IDEA_SYSTEM = "You summarise the user's own idea notes for them. Reply with JSON only, following the schema."


def idea_summary_prompt(title: str, entries: list[str], notes: str) -> str:
    said = "\n\n".join(f"[{n}] {text}" for n, text in enumerate(entries, 1)) or "(nothing yet)"
    return (
        f"Idea: {title}\n\n"
        "Write the summary of this idea for the user's notes: 2 to 5 plain sentences in the user's own terms, "
        "saying what the idea is and the main parts or features they have described. Write it like a short "
        'product description: the first sentence follows the pattern "A <kind of thing> that/where <what it does>." '
        'Do not mention the user or "the idea". Leave out reminders, tasks and deadlines in the messages that are '
        "not part of the idea. Use only what is below; "
        "add nothing new, no advice and no questions. Where later thoughts change earlier ones, describe the "
        "newest version.\n\n"
        f"What the user said, oldest first:\n{said}\n\n"
        f"The user's own notes:\n{notes.strip() or '(none)'}"
    )
