package id.ade.sidewa

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView

class HomeFragment : Fragment(R.layout.fragment_home) {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val ctx = requireContext()
        val feed = Repository.feed(ctx)
        val statsRow = view.findViewById<android.widget.LinearLayout>(R.id.statsRow)
        val labels = listOf("Member", "Kegiatan", "Rilis", "Foto")
        val values = listOf(feed.stats.members, feed.stats.activities, feed.stats.pressReleases, feed.stats.photos)
        labels.forEachIndexed { i, l ->
            statsRow.addView(android.widget.TextView(ctx).apply {
                text = "${l}: ${values[i]}"
                setPadding(48, 0, 48, 0)
            })
        }
        val featured = feed.activities.firstOrNull()
        if (featured != null) {
            view.findViewById<TextView>(R.id.featuredTitle).text = featured.title
            Repository.bitmap(ctx, featured.coverPath)?.let { bm ->
                view.findViewById<android.widget.LinearLayout>(R.id.featuredPhotos)
                    .addView(android.widget.ImageView(ctx).apply { setImageBitmap(bm) })
            }
            view.setOnClickListener {
                startActivity(android.content.Intent(ctx, DetailActivity::class.java).apply {
                    putExtra(DetailActivity.EXTRA_TYPE, DetailActivity.TYPE_ACTIVITY)
                    putExtra(DetailActivity.EXTRA_ID, featured.id)
                })
            }
        }
    }
}

class ActivitiesFragment : Fragment(R.layout.fragment_activities) {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val feed = Repository.feed(requireContext())
        view.findViewById<RecyclerView>(R.id.activityList).apply {
            layoutManager = LinearLayoutManager(context)
            adapter = ActivitiesAdapter(feed.activities) { activity ->
                startActivity(android.content.Intent(context, DetailActivity::class.java).apply {
                    putExtra(DetailActivity.EXTRA_TYPE, DetailActivity.TYPE_ACTIVITY)
                    putExtra(DetailActivity.EXTRA_ID, activity.id)
                })
            }
        }
    }
}

class ActivitiesAdapter(
    private val items: List<ActivityItem>,
    private val onClick: (ActivityItem) -> Unit,
) : RecyclerView.Adapter<ActivitiesAdapter.VH>() {
    class VH(view: View) : RecyclerView.ViewHolder(view)
    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH =
        VH(LayoutInflater.from(parent.context).inflate(R.layout.item_activity, parent, false))
    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]
        with(holder.itemView) {
            findViewById<TextView>(R.id.title).text = item.title
            findViewById<TextView>(R.id.date).text = item.activityDate
            findViewById<android.widget.ImageView>(R.id.cover)
                .setImageBitmap(Repository.bitmap(context, item.coverPath))
            setOnClickListener { onClick(item) }
        }
    }
    override fun getItemCount() = items.size
}

class MembersFragment : Fragment(R.layout.fragment_members) {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val feed = Repository.feed(requireContext())
        view.findViewById<RecyclerView>(R.id.memberList).apply {
            layoutManager = LinearLayoutManager(context)
            adapter = MembersAdapter(feed.members) { member ->
                startActivity(android.content.Intent(context, DetailActivity::class.java).apply {
                    putExtra(DetailActivity.EXTRA_TYPE, DetailActivity.TYPE_MEMBER)
                    putExtra(DetailActivity.EXTRA_ID, member.id)
                })
            }
        }
        view.findViewById<android.widget.Button>(R.id.faceLoginButton).setOnClickListener {
            startActivity(android.content.Intent(requireContext(), FaceLoginActivity::class.java))
        }
    }
}

class MembersAdapter(
    private val items: List<MemberListItem>,
    private val onClick: (MemberListItem) -> Unit,
) : RecyclerView.Adapter<MembersAdapter.VH>() {
    class VH(view: View) : RecyclerView.ViewHolder(view)
    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH =
        VH(LayoutInflater.from(parent.context).inflate(R.layout.item_member, parent, false))
    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]
        with(holder.itemView) {
            findViewById<TextView>(R.id.fullName).text = item.fullName
            findViewById<TextView>(R.id.position).text = item.position
            findViewById<TextView>(R.id.party).text = item.party
            findViewById<TextView>(R.id.commission).text = item.commission
            findViewById<android.widget.ImageView>(R.id.portrait)
                .setImageBitmap(Repository.bitmap(context, item.portraitPath))
            setOnClickListener { onClick(item) }
        }
    }
    override fun getItemCount() = items.size
}

class PressFragment : Fragment(R.layout.fragment_press) {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val feed = Repository.feed(requireContext())
        view.findViewById<RecyclerView>(R.id.pressList).apply {
            layoutManager = LinearLayoutManager(context)
            adapter = PressAdapter(feed.pressReleases) { press ->
                startActivity(android.content.Intent(context, DetailActivity::class.java).apply {
                    putExtra(DetailActivity.EXTRA_TYPE, DetailActivity.TYPE_PRESS)
                    putExtra(DetailActivity.EXTRA_ID, press.id)
                })
            }
        }
    }
}

class PressAdapter(
    private val items: List<PressItem>,
    private val onClick: (PressItem) -> Unit,
) : RecyclerView.Adapter<PressAdapter.VH>() {
    class VH(view: View) : RecyclerView.ViewHolder(view)
    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH =
        VH(LayoutInflater.from(parent.context).inflate(R.layout.item_press, parent, false))
    override fun onBindViewHolder(holder: VH, position: Int) {
        val item = items[position]
        with(holder.itemView) {
            findViewById<TextView>(R.id.title).text = item.title
            findViewById<TextView>(R.id.date).text = item.releaseDate
            findViewById<TextView>(R.id.summary).text = item.summary.ifBlank { item.title }
            setOnClickListener { onClick(item) }
        }
    }
    override fun getItemCount() = items.size
}
