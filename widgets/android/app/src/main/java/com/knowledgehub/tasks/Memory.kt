package com.knowledgehub.tasks

import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale

data class Task(val text: String, val due: LocalDate?)

enum class Tone { LATE, TODAY, SOON }

data class Badge(val label: String, val tone: Tone)

/** Parses the Hermes memory file (Obsidian Tasks emoji format). Same rules as the Rainmeter skin. */
object Memory {
    private val due = Regex("""📅\s*(\d{4}-\d{2}-\d{2})""")
    private val tokens = Regex("""(📅|➕|✅)\s*\S*""")
    private val blockId = Regex("""\s*\^m\d+\s*$""")
    private val checkbox = Regex("""^\[(.)]\s*""")
    private val item = Regex("""^\s*[-*] """)

    fun openTasks(markdown: String): List<Task> {
        val tasks = mutableListOf<Task>()
        var section: String? = null
        for (line in markdown.removePrefix("﻿").lines()) {
            if (line.startsWith("## ")) {
                section = line.substring(3).trim().lowercase()
                continue
            }
            if (section != "tasks" || !item.containsMatchIn(line)) continue
            var text = line.replace(item, "")
            val box = checkbox.find(text)
            if (box != null) {
                if (box.groupValues[1].equals("x", ignoreCase = true)) continue
                text = text.substring(box.range.last + 1)
            }
            val date = due.find(text)?.groupValues?.get(1)?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
            text = text.replace(tokens, "").replace(blockId, "").replace(Regex("""\s+"""), " ").trim()
            tasks += Task(text, date)
        }
        return tasks.sortedWith(compareBy(nullsLast()) { it.due })
    }

    fun badge(due: LocalDate?, today: LocalDate): Badge? {
        if (due == null) return null
        val days = ChronoUnit.DAYS.between(today, due)
        return when {
            days < 0 -> Badge("${-days}d late", Tone.LATE)
            days == 0L -> Badge("today", Tone.TODAY)
            days == 1L -> Badge("tmrw", Tone.SOON)
            days <= 6 -> Badge(due.format(weekday).lowercase(), Tone.SOON)
            else -> Badge(due.format(dayMonth).lowercase(), Tone.SOON)
        }
    }

    fun summary(tasks: List<Task>, today: LocalDate): String {
        val late = tasks.count { it.due != null && it.due < today }
        val dueToday = tasks.count { it.due == today }
        return buildList {
            add("${tasks.size} open")
            if (late > 0) add("$late late")
            if (dueToday > 0) add("$dueToday due today")
        }.joinToString(" · ")
    }

    private val weekday = DateTimeFormatter.ofPattern("EEE dd", Locale.ENGLISH)
    private val dayMonth = DateTimeFormatter.ofPattern("dd MMM", Locale.ENGLISH)
}
