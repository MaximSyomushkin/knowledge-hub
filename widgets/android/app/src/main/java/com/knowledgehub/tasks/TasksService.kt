package com.knowledgehub.tasks

import android.content.Context
import android.content.Intent
import android.view.View
import android.widget.RemoteViews
import android.widget.RemoteViewsService
import java.time.LocalDate

class TasksService : RemoteViewsService() {
    override fun onGetViewFactory(intent: Intent): RemoteViewsFactory = Rows(applicationContext)
}

private class Rows(private val context: Context) : RemoteViewsService.RemoteViewsFactory {
    private var tasks = emptyList<Task>()
    private var today = LocalDate.now()

    override fun onDataSetChanged() {
        today = LocalDate.now()
        tasks = Source.read(context)?.let(Memory::openTasks).orEmpty()
    }

    override fun getViewAt(position: Int): RemoteViews {
        val task = tasks.getOrNull(position) ?: return RemoteViews(context.packageName, R.layout.widget_row)
        return RemoteViews(context.packageName, R.layout.widget_row).apply {
            setTextViewText(R.id.text, task.text)
            val badge = Memory.badge(task.due, today)
            if (badge == null) {
                setViewVisibility(R.id.badge, View.GONE)
            } else {
                setViewVisibility(R.id.badge, View.VISIBLE)
                setTextViewText(R.id.badge, badge.label)
                val (color, background) = when (badge.tone) {
                    Tone.LATE -> R.color.bad to R.drawable.badge_late
                    Tone.TODAY -> R.color.warn to R.drawable.badge_today
                    Tone.SOON -> R.color.live to R.drawable.badge_soon
                }
                setTextColor(R.id.badge, context.getColor(color))
                setInt(R.id.badge, "setBackgroundResource", background)
            }
            setOnClickFillInIntent(R.id.row, Intent())
        }
    }

    override fun getCount() = tasks.size
    override fun getViewTypeCount() = 1
    override fun getItemId(position: Int) = position.toLong()
    override fun hasStableIds() = false
    override fun getLoadingView(): RemoteViews? = null
    override fun onCreate() {}
    override fun onDestroy() {}
}
