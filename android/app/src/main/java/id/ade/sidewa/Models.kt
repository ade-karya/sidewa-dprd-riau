package id.ade.sidewa

import com.google.gson.annotations.SerializedName

data class Stats(
    @SerializedName("members") val members: Int,
    @SerializedName("activities") val activities: Int,
    @SerializedName("pressReleases") val pressReleases: Int,
    @SerializedName("photos") val photos: Int,
)

data class Commission(
    @SerializedName("id") val id: Int,
    @SerializedName("code") val code: String,
    @SerializedName("name") val name: String,
    @SerializedName("color") val color: String,
)

data class ActivityItem(
    @SerializedName("id") val id: Int,
    @SerializedName("code") val code: String,
    @SerializedName("title") val title: String,
    @SerializedName("category") val category: String,
    @SerializedName("activityDate") val activityDate: String,
    @SerializedName("startTime") val startTime: String?,
    @SerializedName("endTime") val endTime: String?,
    @SerializedName("locationName") val locationName: String,
    @SerializedName("locationAddress") val locationAddress: String,
    @SerializedName("commissions") val commissions: List<String>,
    @SerializedName("coverPath") val coverPath: String?,
    @SerializedName("memberCount") val memberCount: Int,
)

data class ActivityDetail(
    @SerializedName("id") val id: Int,
    @SerializedName("code") val code: String,
    @SerializedName("title") val title: String,
    @SerializedName("description") val description: String,
    @SerializedName("category") val category: String,
    @SerializedName("activityDate") val activityDate: String,
    @SerializedName("startTime") val startTime: String?,
    @SerializedName("endTime") val endTime: String?,
    @SerializedName("locationName") val locationName: String,
    @SerializedName("locationAddress") val locationAddress: String,
    @SerializedName("commissions") val commissions: List<String>,
    @SerializedName("coverPath") val coverPath: String?,
    @SerializedName("memberCount") val memberCount: Int,
    @SerializedName("photos") val photos: List<ActivityPhoto>,
    @SerializedName("members") val members: List<MemberBrief>,
)

data class ActivityPhoto(
    @SerializedName("id") val id: Int,
    @SerializedName("path") val path: String?,
    @SerializedName("thumbPath") val thumbPath: String?,
)

data class MemberBrief(
    @SerializedName("id") val id: Int,
    @SerializedName("fullName") val fullName: String,
    @SerializedName("position") val position: String,
    @SerializedName("party") val party: String,
)

data class MemberListItem(
    @SerializedName("id") val id: Int,
    @SerializedName("fullName") val fullName: String,
    @SerializedName("position") val position: String,
    @SerializedName("party") val party: String,
    @SerializedName("dapil") val dapil: String,
    @SerializedName("commission") val commission: String,
    @SerializedName("portraitPath") val portraitPath: String?,
    @SerializedName("activityCount") val activityCount: Int,
)

data class MemberDetail(
    @SerializedName("id") val id: Int,
    @SerializedName("fullName") val fullName: String,
    @SerializedName("position") val position: String,
    @SerializedName("party") val party: String,
    @SerializedName("dapil") val dapil: String,
    @SerializedName("bio") val bio: String,
    @SerializedName("commission") val commission: String,
    @SerializedName("portraitPath") val portraitPath: String?,
    @SerializedName("activityCount") val activityCount: Int,
    @SerializedName("activities") val activities: List<ActivityItem>,
)

data class PressItem(
    @SerializedName("id") val id: Int,
    @SerializedName("code") val code: String,
    @SerializedName("title") val title: String,
    @SerializedName("slug") val slug: String,
    @SerializedName("summary") val summary: String,
    @SerializedName("releaseDate") val releaseDate: String,
    @SerializedName("tags") val tags: List<String>,
    @SerializedName("coverPath") val coverPath: String?,
)

data class PressDetail(
    @SerializedName("id") val id: Int,
    @SerializedName("code") val code: String,
    @SerializedName("title") val title: String,
    @SerializedName("slug") val slug: String,
    @SerializedName("summary") val summary: String,
    @SerializedName("body") val body: String,
    @SerializedName("releaseDate") val releaseDate: String,
    @SerializedName("tags") val tags: List<String>,
    @SerializedName("activityId") val activityId: Int?,
    @SerializedName("activityTitle") val activityTitle: String?,
    @SerializedName("coverPath") val coverPath: String?,
)

data class FaceEntry(
    @SerializedName("memberId") val memberId: Int,
    @SerializedName("memberName") val memberName: String,
    @SerializedName("registeredFaces") val registeredFaces: Int,
    @SerializedName("logins") val logins: Int,
)

data class Feed(
    @SerializedName("stats") val stats: Stats,
    @SerializedName("commissions") val commissions: List<Commission>,
    @SerializedName("activities") val activities: List<ActivityItem>,
    @SerializedName("activityDetails") val activityDetails: List<ActivityDetail>,
    @SerializedName("members") val members: List<MemberListItem>,
    @SerializedName("memberDetails") val memberDetails: List<MemberDetail>,
    @SerializedName("pressReleases") val pressReleases: List<PressItem>,
    @SerializedName("pressReleaseDetails") val pressReleaseDetails: List<PressDetail>,
    @SerializedName("faces") val faces: List<FaceEntry>,
)

class Config(
    val supabaseUrl: String,
    val anonKey: String,
    val backendUrl: String,
    val appName: String,
    val mediaSignUrl: String,
)
