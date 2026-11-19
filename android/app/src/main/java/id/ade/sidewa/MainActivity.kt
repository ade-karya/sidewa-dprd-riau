package id.ade.sidewa

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView

class MainActivity : AppCompatActivity(R.layout.activity_main) {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val nav = findViewById<com.google.android.material.bottomnavigation.BottomNavigationView>(R.id.bottomNav)
        fun show(fragment: androidx.fragment.app.Fragment) {
            supportFragmentManager.beginTransaction().replace(R.id.fragmentContainer, fragment).commit()
        }
        nav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.menu_beranda -> { show(HomeFragment()); true }
                R.id.menu_kegiatan -> { show(ActivitiesFragment()); true }
                R.id.menu_anggota -> { show(MembersFragment()); true }
                R.id.menu_rilis -> { show(PressFragment()); true }
                else -> false
            }
        }
        if (savedInstanceState == null) show(HomeFragment())
    }
}

class DetailActivity : AppCompatActivity() {
    companion object {
        const val EXTRA_TYPE = "type"
        const val EXTRA_ID = "id"
        const val TYPE_ACTIVITY = "activity"
        const val TYPE_MEMBER = "member"
        const val TYPE_PRESS = "press"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_detail)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        val feed = Repository.feed(this)
        val type = intent.getStringExtra(EXTRA_TYPE) ?: TYPE_ACTIVITY
        val id = intent.getIntExtra(EXTRA_ID, -1)

        when (type) {
            TYPE_ACTIVITY -> {
                val activity = feed.activityDetails.find { it.id == id }
                if (activity != null) {
                    setTitle(activity.title)
                    findViewById<TextView>(R.id.title).text = activity.title
                    findViewById<TextView>(R.id.description).text = activity.description
                    findViewById<TextView>(R.id.info).text = buildString {
                        appendLine("Tanggal: ${activity.activityDate}")
                        if (activity.locationName.isNotBlank()) appendLine("Lokasi: ${activity.locationName}")
                        if (activity.commissions.isNotEmpty()) appendLine("Komisi: ${activity.commissions.joinToString(", ")}")
                    }
                    findViewById<TextView>(R.id.memberCount).text = "Peserta: ${activity.members.size}"
                    addPhotos(activity.photos.map { it.path ?: it.thumbPath })
                }
            }
            TYPE_MEMBER -> {
                val member = feed.memberDetails.find { it.id == id }
                if (member != null) {
                    setTitle(member.fullName)
                    findViewById<TextView>(R.id.title).text = member.fullName
                    findViewById<TextView>(R.id.fullName).text = member.fullName
                    findViewById<TextView>(R.id.position).text = member.position
                    findViewById<TextView>(R.id.party).text = member.party
                    findViewById<TextView>(R.id.dapil).text = member.dapil
                    findViewById<TextView>(R.id.commission).text = member.commission
                    findViewById<TextView>(R.id.bio).text = member.bio
                    findViewById<TextView>(R.id.memberCount).text = "Kegiatan: ${member.activityCount}"
                    addPhotos(listOf(member.portraitPath), square = true)
                }
            }
            TYPE_PRESS -> {
                val press = feed.pressReleaseDetails.find { it.id == id }
                if (press != null) {
                    setTitle(press.title)
                    findViewById<TextView>(R.id.title).text = press.title
                    findViewById<TextView>(R.id.summary).text = press.summary
                    findViewById<TextView>(R.id.releaseDate).text = "Rilis: ${press.releaseDate}"
                    findViewById<TextView>(R.id.description).text = press.body.ifBlank { press.summary }
                    findViewById<TextView>(R.id.body).text = press.body
                    addPhotos(listOf(press.coverPath))
                }
            }
        }
    }

    private fun addPhotos(paths: List<String?>, square: Boolean = false) {
        val row = findViewById<LinearLayout>(R.id.photos)
        for (path in paths) {
            if (path == null) continue
            Repository.bitmap(this, path)?.let { bm ->
                row.addView(android.widget.ImageView(this).apply { setImageBitmap(bm) })
            }
        }
    }
}

class FaceLoginActivity : AppCompatActivity(R.layout.activity_face_login) {
    companion object { const val REQ_PICK = 1001 }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        val feed = Repository.feed(this)
        findViewById<RecyclerView>(R.id.memberList).apply {
            layoutManager = LinearLayoutManager(context)
            adapter = FaceListAdapter(feed.faces)
        }
        findViewById<android.widget.Button>(R.id.faceLoginButton).setOnClickListener {
            startActivityForResult(android.content.Intent(android.content.Intent.ACTION_GET_CONTENT).apply {
                type = "image/*"
            }, REQ_PICK)
        }
        findViewById<TextView>(R.id.statusText).text = "Ambil foto wajah menggunakan tombol Ambil Foto Wajah."
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_PICK && resultCode == RESULT_OK && data != null) {
            val uri = data.data ?: return
            val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() }
            if (bytes == null) {
                findViewById<TextView>(R.id.statusText).text = "Gagal membaca foto."
                return
            }
            findViewById<TextView>(R.id.statusText).text = "Mengirim foto wajah ke server..."
            Thread {
                val ok = Repository.faceLogin(this, bytes)
                runOnUiThread {
                    findViewById<TextView>(R.id.statusText).text =
                        if (ok) "Face ID berhasil disiapkan. Buka tombol 'Masuk dengan Face ID' di Beranda."
                        else "Gagal: server tidak dapat membaca wajah (pastikan server hidup)."
                }
            }.start()
        }
    }
}

class FaceListAdapter(private val items: List<FaceEntry>) :
    RecyclerView.Adapter<FaceListAdapter.VH>() {
    class VH(view: View) : RecyclerView.ViewHolder(view)
    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH =
        VH(LayoutInflater.from(parent.context).inflate(R.layout.item_face, parent, false))
    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]
        with(holder.itemView) {
            findViewById<TextView>(R.id.fullName).text = item.memberName
            findViewById<TextView>(R.id.position).text = "Faces: ${item.registeredFaces} | Login: ${item.logins}"
        }
    }
    override fun getItemCount() = items.size
}
