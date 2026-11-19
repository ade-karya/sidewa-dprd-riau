package id.ade.sidewa

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.ConnectivityManager
import android.os.Build
import android.util.JsonReader
import com.google.gson.Gson
import com.google.gson.JsonParser
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

object Repository {
    private val gson = Gson()
    private val bitmapCache = ConcurrentHashMap<String, Bitmap>()

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    fun config(ctx: Context): Config {
        val text = ctx.assets.open("config.json").use { it.readBytes().decodeToString() }
        val j = JsonParser.parseString(text).asJsonObject
        return Config(
            supabaseUrl = j.get("supabase_url").asString.trimEnd('/'),
            anonKey = j.get("anon_key").asString,
            backendUrl = j.get("backend_url")?.takeIf { it.isJsonPrimitive }?.asString?.trimEnd('/') ?: "https://dprd.riau.ai",
            appName = j.get("app_name").asString,
            mediaSignUrl = (j.get("supabase_url").asString.trimEnd('/') + "/functions/v1/media-sign").trimEnd('/'),
        )
    }

    fun isOnline(ctx: Context): Boolean {
        val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        @Suppress("DEPRECATION")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            return cm.activeNetwork != null
        }
        @Suppress("DEPRECATION")
        return cm.activeNetworkInfo?.isConnected == true
    }

    private fun fetchJson(url: String, body: String? = null): String? = try {
        val request = Request.Builder()
            .url(url)
            .apply {
                if (body != null) {
                    post(body.toRequestBody("application/json".toMediaType()))
                } else method("GET", null)
            }
            .build()
        client.newCall(request).execute().use { it.body?.string() }
    } catch (e: IOException) { null }

    fun feed(ctx: Context): Feed {
        val online = onlineFeed(ctx)
        return online ?: loadAssetFeed(ctx)
    }

    fun loadAssetFeed(ctx: Context): Feed {
        val text = ctx.assets.open("feed.json").use { it.readBytes().decodeToString() }
        val j = JsonParser.parseString(text).asJsonObject
        return gson.fromJson(text, Feed::class.java)
    }

    fun onlineFeed(ctx: Context): Feed? {
        if (!isOnline(ctx)) return null
        val cfg = config(ctx)
        fun rpc(fn: String, body: String): String? {
            val url = "${cfg.supabaseUrl}/rest/v1/rpc/$fn"
            val raw = fetchJson(url, body) ?: return null
            val js = JsonParser.parseString(raw)
            return js.takeIf { it.isJsonObject } ?.let { gson.toJson(it) } ?: gson.toJson(js)
        }
        try {
            val stats = gson.fromJson(rpc("android_stats", "{}"), Stats::class.java)
            val commissions = gson.fromJson(rpc("android_commissions", "{}"), Array<Commission>::class.java).toList()
            val acts = gson.fromJson(rpc("android_activities", "{}"), Array<ActivityItem>::class.java).toList()
            val details = acts.map { a -> gson.fromJson(rpc("android_activity", """{"p_id":${a.id}}"""), ActivityDetail::class.java) }
            val members = gson.fromJson(rpc("android_members", "{}"), Array<MemberListItem>::class.java).toList()
            val mdetails = members.map { m -> gson.fromJson(rpc("android_member", """{"p_id":${m.id}}"""), MemberDetail::class.java) }
            val presses = gson.fromJson(rpc("android_press_releases", "{}"), Array<PressItem>::class.java).toList()
            val pdetails = presses.map { p -> gson.fromJson(rpc("android_press_release", """{"p_id":${p.id}}"""), PressDetail::class.java) }
            val faces = gson.fromJson(rpc("android_faces", "{}"), Array<FaceEntry>::class.java).toList()
            return Feed(stats, commissions, acts, details, members, mdetails, presses, pdetails, faces)
        } catch (e: Exception) {
            return null
        }
    }

    fun faceLogin(ctx: Context, jpegBytes: ByteArray): Boolean {
        val cfg = config(ctx)
        val url = cfg.backendUrl + "/api/v1/login/wajah"
        val boundary = "----dewank8formboundary" + (1..6).map { "0123456789abcdef"[(Math.random() * 16).toInt()] }.joinToString("")
        val body = java.io.ByteArrayOutputStream()
        fun part(name: String, value: String, filename: String? = null, mime: String? = null) {
            body.write("--$boundary\r\n".toByteArray())
            val disp = if (filename != null) "Content-Disposition: form-data; name=\"$name\"; filename=\"$filename\"\r\n"
                                        else "Content-Disposition: form-data; name=\"$name\"\r\n"
            body.write((disp + (if (mime != null) "Content-Type: $mime\r\n" else "") + "\r\n").toByteArray())
            if (filename != null) { body.write(jpegBytes) } else { body.write(value.toByteArray()) }
            body.write("\r\n".toByteArray())
        }
        part("photo", "", "face.jpg", "image/jpeg")
        body.write(("--$boundary--\r\n").toByteArray())
        val request = Request.Builder()
            .url(url)
            .post(body.toByteArray().toRequestBody("multipart/form-data; boundary=$boundary".toMediaType()))
            .build()
        return client.newCall(request).execute().use { it.isSuccessful }
    }

    fun bitmap(ctx: Context, path: String?): Bitmap? {
        if (path.isNullOrEmpty()) return null
        bitmapCache[path]?.let { return it }
        val bytes = if (isOnline(ctx)) {
            val url = signUrls(ctx, listOf(path))?.get(path) ?: return null
            val req = Request.Builder().url(url).build()
            client.newCall(req).execute().use { r ->
                if (!r.isSuccessful) null else r.body?.bytes()
            }
        } else {
            ctx.assets.open("media/$path").use { it.readBytes() }
        } ?: return null
        return BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.also { bitmapCache[path] = it }
    }

    private fun signUrls(ctx: Context, paths: List<String>): Map<String, String>? {
        if (paths.isEmpty()) return null
        val cfg = config(ctx)
        val json = JsonParser.parseString("""{"keys":${paths.toString()},"expires":3600}""").toString()
        val raw = fetchJson(cfg.mediaSignUrl, json) ?: return null
        val result = JsonParser.parseString(raw).asJsonObject
        val urls = result.get("urls").asJsonObject
        val out = HashMap<String, String>()
        paths.forEach { p -> urls.get(p)?.takeIf { it.isJsonPrimitive }?.let { out[p] = it.asString } }
        return out.takeIf { it.isNotEmpty() }
    }

    fun clearBitmapCache() { bitmapCache.clear() }
}
