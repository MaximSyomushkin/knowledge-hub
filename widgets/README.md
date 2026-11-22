# Companion Tasks Widgets

Read-only widgets that read open tasks (and upcoming events on desktop) directly from `ReadWrite/Memory/memory.md` (Obsidian Tasks emoji format) without opening Obsidian.

## Windows Desktop (`rainmeter/`)

- Source: `rainmeter/src/Tasks.lua` and `rainmeter/build.py`.
- Edit `MemoryFile`, `MemoryFolder`, and `vault=` in `rainmeter/build.py`, then run:

```powershell
python rainmeter/build.py
```

- `build.py` generates `rainmeter/Tasks/` (re-encoding the `.ini` and `.lua` to UTF-16 LE so Rainmeter handles Unicode emoji markers cleanly) and builds the `22×22` grid tile.
- Link or copy `rainmeter/Tasks` into `Documents\Rainmeter\Skins\Tasks`.
- Shows open tasks (up to `MaxTasks`) and upcoming events (up to `MaxEvents`), re-reads `memory.md` every 5 seconds, and opens the file in Obsidian on click.

## Android (`android/`)

- Plain Kotlin home-screen widget with **zero runtime library dependencies**.
- Shows open tasks from `## Tasks` sorted by due date (undated tasks last), with semantic due badges (`today`, `tmrw`, weekday/date).
- First run prompts you to select `memory.md` from your synced vault folder using Android's Storage Access Framework (no broad storage permission required).
- Refreshes automatically on the system widget schedule and whenever you tap the header; tapping any task opens `memory.md` in Obsidian.
- Build & run unit tests (JDK 21):

```powershell
cd android
.\gradlew.bat testDebugUnitTest assembleRelease
```
