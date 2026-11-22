package com.knowledgehub.tasks

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.DocumentsContract
import android.provider.MediaStore

/** The memory.md file the user picked (a persisted Storage Access Framework URI). */
object Source {
    private const val PREFS = "source"
    private const val KEY = "uri"

    fun uri(context: Context): Uri? =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, null)?.let(Uri::parse)

    fun save(context: Context, uri: Uri) {
        context.contentResolver.takePersistableUriPermission(uri, Intent.FLAG_GRANT_READ_URI_PERMISSION)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString(KEY, uri.toString()).apply()
    }

    /** Null when no file is picked or it can't be read. */
    fun read(context: Context): String? {
        val uri = uri(context) ?: return null
        return runCatching {
            context.contentResolver.openInputStream(uri)?.use { it.readBytes().toString(Charsets.UTF_8) }
        }.getOrNull()
    }

    /**
     * obsidian://open?file=Memory/memory. Obsidian mobile ignores `path=`, but resolves `file=` like a wikilink in the
     * open vault, so the parent folder plus the note name is enough and the vault's name and root aren't needed.
     */
    fun obsidianUri(context: Context): Uri? {
        val uri = uri(context) ?: return null
        val path = absolutePath(context, uri) ?: return null
        val note = path.split('/').takeLast(2).joinToString("/").removeSuffix(".md")
        return Uri.parse("obsidian://open?file=" + Uri.encode(note))
    }

    fun absolutePath(context: Context, uri: Uri): String? = runCatching {
        if (uri.authority == "com.android.externalstorage.documents") {
            val id = DocumentsContract.getDocumentId(uri)
            val volume = id.substringBefore(':')
            val root = if (volume == "primary") "/storage/emulated/0" else "/storage/$volume"
            "$root/${id.substringAfter(':')}"
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            // Picked via Recent/Downloads/media: the document id is a MediaStore row, so ask MediaStore where it is.
            val media = MediaStore.getMediaUri(context, uri) ?: return@runCatching null
            context.contentResolver.query(
                media,
                arrayOf(MediaStore.MediaColumns.VOLUME_NAME, MediaStore.MediaColumns.RELATIVE_PATH, MediaStore.MediaColumns.DISPLAY_NAME),
                null, null, null,
            )?.use { c ->
                if (!c.moveToFirst()) return@use null
                val volume = c.getString(0)
                val root = if (volume == MediaStore.VOLUME_EXTERNAL_PRIMARY) "/storage/emulated/0" else "/storage/${volume.uppercase()}"
                "$root/${c.getString(1)}${c.getString(2)}"
            }
        } else {
            null
        }
    }.getOrNull()
}
