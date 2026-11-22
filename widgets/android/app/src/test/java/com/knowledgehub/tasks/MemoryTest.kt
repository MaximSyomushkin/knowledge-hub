package com.knowledgehub.tasks

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.LocalDate

class MemoryTest {
    private val today = LocalDate.of(2026, 11, 3)

    private val file = """
        # Memory

        What you asked the bot to remember.

        ## Tasks
        - [ ] Maths deadline 📅 2026-11-08 ➕ 2026-10-23 ^m8
        - [x] Already done 📅 2026-11-01 ➕ 2026-10-20 ✅ 2026-11-02 ^m2
        - [ ] Café résumé ➕ 2026-10-21 ^m3
        - [ ] Overdue thing 📅 2026-10-30 ➕ 2026-10-20 ^m1
        - No checkbox 📅 2026-11-03
        - [ ] Make an applet for memory 📅 2026-11-03 ➕ 2026-11-03 ^m11

        ## Events
        - Stats 📅 2026-10-28 ➕ 2026-10-27 ^m9

        ## Facts
        - Likes tea ^m13
    """.trimIndent()

    @Test
    fun keepsOpenTasksSortedByDueWithUndatedLast() {
        assertEquals(
            listOf(
                Task("Overdue thing", LocalDate.of(2026, 10, 30)),
                Task("No checkbox", today),
                Task("Make an applet for memory", today),
                Task("Maths deadline", LocalDate.of(2026, 11, 8)),
                Task("Café résumé", null),
            ),
            Memory.openTasks(file),
        )
    }

    @Test
    fun handlesBomAndCrlf() {
        val tasks = Memory.openTasks("﻿## Tasks\r\n- [ ] One 📅 2026-11-04 ^m1\r\n")
        assertEquals(listOf(Task("One", LocalDate.of(2026, 11, 4))), tasks)
    }

    @Test
    fun badges() {
        assertNull(Memory.badge(null, today))
        assertEquals(Badge("4d late", Tone.LATE), Memory.badge(LocalDate.of(2026, 10, 30), today))
        assertEquals(Badge("today", Tone.TODAY), Memory.badge(today, today))
        assertEquals(Badge("tmrw", Tone.SOON), Memory.badge(LocalDate.of(2026, 11, 4), today))
        assertEquals(Badge("sun 08", Tone.SOON), Memory.badge(LocalDate.of(2026, 11, 8), today))
        assertEquals(Badge("15 dec", Tone.SOON), Memory.badge(LocalDate.of(2026, 12, 15), today))
    }

    @Test
    fun summary() {
        assertEquals("5 open · 1 late · 2 due today", Memory.summary(Memory.openTasks(file), today))
        assertEquals("0 open", Memory.summary(emptyList(), today))
    }
}
