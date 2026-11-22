package com.knowledgehub.tasks

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.RemoteViews
import java.time.LocalDate

class TasksWidget : AppWidgetProvider() {

    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val markdown = Source.read(context)
        val header = when {
            Source.uri(context) == null -> "tap to set up"
            markdown == null -> "file not found"
            else -> Memory.summary(Memory.openTasks(markdown), LocalDate.now())
        }
        for (id in ids) manager.updateAppWidget(id, views(context, id, header))
        manager.notifyAppWidgetViewDataChanged(ids, R.id.list)
    }

    override fun onReceive(context: Context, intent: Intent) {
        super.onReceive(context, intent)
        if (intent.action == ACTION_REFRESH) refreshAll(context)
    }

    private fun views(context: Context, id: Int, header: String) =
        RemoteViews(context.packageName, R.layout.widget).apply {
            setTextViewText(R.id.summary, header)

            val adapter = Intent(context, TasksService::class.java)
                .putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, id)
            adapter.data = Uri.parse(adapter.toUri(Intent.URI_INTENT_SCHEME))
            @Suppress("DEPRECATION")
            setRemoteAdapter(R.id.list, adapter)
            setEmptyView(R.id.list, R.id.empty)
            setTextViewText(R.id.empty, if (Source.uri(context) == null) "Choose memory.md" else "All clear")

            val refresh = Intent(context, TasksWidget::class.java).setAction(ACTION_REFRESH)
            setOnClickPendingIntent(
                R.id.header,
                PendingIntent.getBroadcast(context, 0, refresh, PendingIntent.FLAG_IMMUTABLE),
            )

            val open = Intent(context, OpenActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            val openPending = PendingIntent.getActivity(
                context, 1, open, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_MUTABLE,
            )
            setPendingIntentTemplate(R.id.list, openPending)
            setOnClickPendingIntent(R.id.empty, openPending)
        }

    companion object {
        const val ACTION_REFRESH = "com.knowledgehub.tasks.REFRESH"

        fun refreshAll(context: Context) {
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, TasksWidget::class.java))
            if (ids.isNotEmpty()) TasksWidget().onUpdate(context, manager, ids)
        }
    }
}
