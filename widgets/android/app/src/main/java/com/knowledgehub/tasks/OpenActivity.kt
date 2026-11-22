package com.knowledgehub.tasks

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.os.Bundle
import android.widget.Toast

/**
 * Widget taps land here and are forwarded to Obsidian. List items need a mutable PendingIntent template,
 * and Android 14+ only allows those for explicit intents, so the template can't point at Obsidian directly.
 */
class OpenActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val target = Source.obsidianUri(this)
        try {
            if (target == null) startActivity(Intent(this, SetupActivity::class.java))
            else startActivity(Intent(Intent.ACTION_VIEW, target))
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, "Obsidian isn't installed", Toast.LENGTH_SHORT).show()
        }
        finish()
    }
}
