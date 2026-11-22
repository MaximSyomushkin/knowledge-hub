package com.knowledgehub.tasks

import android.app.Activity
import android.appwidget.AppWidgetManager
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import java.time.LocalDate

/** Picks memory.md. Also the widget's configure screen, so adding a widget asks for the file the first time. */
class SetupActivity : Activity() {
    private var widgetId = AppWidgetManager.INVALID_APPWIDGET_ID

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_setup)
        widgetId = intent.getIntExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID)
        setResult(RESULT_CANCELED)

        findViewById<Button>(R.id.pick).setOnClickListener {
            startActivityForResult(
                Intent(Intent.ACTION_OPEN_DOCUMENT)
                    .addCategory(Intent.CATEGORY_OPENABLE)
                    .setType("*/*")
                    .addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION),
                PICK,
            )
        }
        findViewById<Button>(R.id.done).setOnClickListener { finishSetup() }

        if (widgetId != AppWidgetManager.INVALID_APPWIDGET_ID && Source.uri(this) != null) finishSetup()
        else showStatus()
    }

    @Deprecated("Activity result API needs AndroidX; this app has no dependencies")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val uri = data?.data
        if (requestCode == PICK && resultCode == RESULT_OK && uri != null) {
            Source.save(this, uri)
            TasksWidget.refreshAll(this)
        }
        showStatus()
    }

    private fun showStatus() {
        val status = findViewById<TextView>(R.id.status)
        val markdown = Source.read(this)
        status.text = when {
            Source.uri(this) == null -> "Pick memory.md in your Syncthing copy of the vault:\n<vault> › ReadWrite › Memory › memory.md"
            markdown == null -> "Can't read the chosen file. Pick it again."
            else -> {
                val tasks = Memory.openTasks(markdown)
                val where = Source.uri(this)?.let { Source.absolutePath(this, it) }
                    ?: "memory.md (folder unknown, so taps can't open it)"
                "Reading $where\n" +
                    Memory.summary(tasks, LocalDate.now())
            }
        }
        findViewById<Button>(R.id.done).isEnabled = markdown != null
    }

    private fun finishSetup() {
        TasksWidget.refreshAll(this)
        if (widgetId != AppWidgetManager.INVALID_APPWIDGET_ID) {
            setResult(RESULT_OK, Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId))
        }
        finish()
    }

    private companion object {
        const val PICK = 1
    }
}
