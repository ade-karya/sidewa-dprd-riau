"""Data demo SIDEWA untuk DPRD Provinsi Riau.

Seluruh foto potret pada data demo dibuat dengan AI (this-person-does-not-exist.com)
dan bukan wajah orang sungguhan.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..config import BASE_DIR
from ..constants import (
    ROLE_ADMIN,
    ROLE_HUMAS,
    ROLE_PIMPINAN,
    ROLE_STAF,
    ROLE_SUPERADMIN,
    STATUS_ARCHIVED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
)
from ..models import (
    Activity,
    ActivityMember,
    ActivityPhoto,
    ApiToken,
    AuditLog,
    Commission,
    FaceDetection,
    Member,
    MemberFace,
    User,
    activity_commissions,
    utcnow,
)
from ..security import hash_password
from . import face_engine, jobs
from .images import copy_seed_image, delete_paths

logger = logging.getLogger("sidewa.seed")

ASSETS = BASE_DIR / "seed_assets"

COMMISSIONS = [
    {
        "code": "I",
        "name": "Komisi I",
        "bidang": "Pemerintahan, Hukum dan HAM, Keamanan",
        "description": "Membidangi pemerintahan, otonomi daerah, hukum, HAM, keamanan, dan hubungan antarlembaga.",
        "color": "#7E4890",
        "sort_order": 1,
    },
    {
        "code": "II",
        "name": "Komisi II",
        "bidang": "Ekonomi, Keuangan, Pertanian dan Perkebunan",
        "description": "Membidangi perekonomian, keuangan daerah, perpajakan, pertanian, perkebunan, dan koperasi.",
        "color": "#3C8DAD",
        "sort_order": 2,
    },
    {
        "code": "III",
        "name": "Komisi III",
        "bidang": "Pembangunan, Infrastruktur dan Perhubungan",
        "description": "Membidangi pekerjaan umum, tata ruang, perumahan, perhubungan, dan infrastruktur daerah.",
        "color": "#C08A2E",
        "sort_order": 3,
    },
    {
        "code": "IV",
        "name": "Komisi IV",
        "bidang": "Pendidikan, Kesehatan, Sosial dan Budaya",
        "description": "Membidangi pendidikan, kesehatan, sosial, agama, kebudayaan, dan pemberdayaan perempuan.",
        "color": "#5B8C5A",
        "sort_order": 4,
    },
    {
        "code": "V",
        "name": "Komisi V",
        "bidang": "Lingkungan Hidup, Kehutanan dan Pariwisata",
        "description": "Membidangi lingkungan hidup, kehutanan, pertambangan, energi, pariwisata, dan perikanan.",
        "color": "#B85C7A",
        "sort_order": 5,
    },
]

MEMBERS = [
    # (portrait, nama, jabatan, komisi, partai, dapil)
    ("p10.jpg", "H. Ahmad Fauzan, S.H., M.H.", "Ketua DPRD", None, "Golkar", "Riau I"),
    ("p3.jpg", "Hj. Siti Rahmawati, S.E.", "Wakil Ketua DPRD", None, "Gerindra", "Riau II"),
    ("x15.jpg", "Ir. Budi Santoso, M.M.", "Wakil Ketua DPRD", None, "PDI Perjuangan", "Riau III"),
    ("p4.jpg", "H. Muhammad Iqbal, S.Ag.", "Wakil Ketua DPRD", None, "PKS", "Riau IV"),
    ("p6.jpg", "Drs. Hendra Wijaya, M.Si.", "Ketua Komisi I", "I", "Golkar", "Riau I"),
    ("p5.jpg", "Rina Kartika, S.H., M.H.", "Sekretaris Komisi I", "I", "PDI Perjuangan", "Riau II"),
    ("p2.jpg", "Fajar Nugroho, S.IP.", "Anggota Komisi I", "I", "NasDem", "Riau III"),
    ("p14.jpg", "Hj. Nurmala Sari, S.E., M.M.", "Ketua Komisi II", "II", "Gerindra", "Riau IV"),
    ("p8.jpg", "Andi Pratama, S.Kom.", "Wakil Ketua Komisi II", "II", "Demokrat", "Riau V"),
    ("p11.jpg", "Dewi Anggraini, S.E.", "Anggota Komisi II", "II", "PAN", "Riau VI"),
    ("x14.jpg", "Ir. Rizal Kurniawan, M.T.", "Ketua Komisi III", "III", "Golkar", "Riau I"),
    ("p16.jpg", "Maya Lestari, S.T.", "Sekretaris Komisi III", "III", "PDI Perjuangan", "Riau II"),
    ("x13.jpg", "dr. Rudi Hartono, M.Kes.", "Ketua Komisi IV", "IV", "NasDem", "Riau III"),
    ("p7.jpg", "Fitri Handayani, S.Pd.", "Anggota Komisi IV", "IV", "PKB", "Riau IV"),
    ("extra04.jpg", "H. Syafril, S.Hut.", "Ketua Komisi V", "V", "Gerindra", "Riau V"),
    ("x16.jpg", "Lina Marlina, S.Sos.", "Anggota Komisi V", "V", "PAN", "Riau VI"),
]

ACTIVITIES = [
    {
        "slug": "paripurna-apbd",
        "title": "Rapat Paripurna Pengesahan APBD Provinsi Riau Tahun 2026",
        "category": "Rapat Paripurna",
        "date": date(2026, 10, 20),
        "time": ("09.00", "13.30"),
        "location": "Ruang Rapat Paripurna, Gedung DPRD Provinsi Riau",
        "address": "Jl. Jenderal Sudirman No. 1, Pekanbaru, Riau",
        "commissions": ["I", "II", "III", "IV", "V"],
        "members": [1, 2, 3, 4, 5, 8],
        "status": STATUS_PUBLISHED,
        "description": (
            "DPRD Provinsi Riau menggelar Rapat Paripurna dalam rangka pengesahan Rancangan Anggaran "
            "Pendapatan dan Belanja Daerah (APBD) Provinsi Riau Tahun Anggaran 2026. Rapat dipimpin "
            "langsung oleh Ketua DPRD dan dihadiri seluruh pimpinan serta perwakilan lima komisi.\n\n"
            "Dalam forum tersebut, Badan Anggaran menyampaikan laporan akhir pembahasan yang menekankan "
            "efisiensi belanja daerah, penguatan program prioritas, serta peningkatan alokasi untuk "
            "pendidikan, kesehatan, dan infrastruktur perdesaan.\n\n"
            "Pimpinan DPRD menegaskan komitmen pengawasan bersama agar seluruh program yang telah "
            "disepakati dapat berjalan tepat sasaran dan akuntabel."
        ),
        "photos": ["paripurna-apbd-1.jpg", "paripurna-apbd-2.jpg"],
    },
    {
        "slug": "kerja-komisi-ii",
        "title": "Rapat Kerja Komisi II Evaluasi Realisasi APBD",
        "category": "Rapat Kerja",
        "date": date(2026, 10, 14),
        "time": ("10.00", "12.30"),
        "location": "Ruang Rapat Komisi II, Gedung DPRD Provinsi Riau",
        "address": "Jl. Jenderal Sudirman No. 1, Pekanbaru, Riau",
        "commissions": ["II"],
        "members": [8, 9, 10],
        "status": STATUS_PUBLISHED,
        "description": (
            "Komisi II DPRD Provinsi Riau menggelar rapat kerja bersama Organisasi Perangkat Daerah "
            "terkait untuk mengevaluasi realisasi APBD triwulan III tahun 2026.\n\n"
            "Pembahasan menyoroti capaian pendapatan daerah, serapan belanja program, serta kendala "
            "administratif yang menyebabkan keterlambatan pada beberapa kegiatan. Komisi II meminta "
            "perangkat daerah mempercepat proses pengadaan tanpa mengabaikan prinsip akuntabilitas."
        ),
        "photos": ["kerja-komisi-ii-1.jpg", "kerja-komisi-ii-2.jpg"],
    },
    {
        "slug": "kunker-komisi-iii",
        "title": "Kunjungan Kerja Komisi III ke Kabupaten Kampar",
        "category": "Kunjungan Kerja",
        "date": date(2026, 10, 8),
        "time": ("08.00", "15.00"),
        "location": "Kantor Bupati Kampar",
        "address": "Bangkinang, Kabupaten Kampar, Riau",
        "commissions": ["III"],
        "members": [11, 12],
        "status": STATUS_PUBLISHED,
        "description": (
            "Komisi III melakukan kunjungan kerja ke Kabupaten Kampar untuk meninjau progres pembangunan "
            "jalan provinsi dan jembatan penghubung antardesa.\n\n"
            "Tim komisi berdialog dengan pemerintah kabupaten, pelaksana proyek, dan perwakilan masyarakat "
            "untuk memastikan mutu pekerjaan sesuai spesifikasi. Beberapa catatan lapangan akan dibahas "
            "kembali bersama dinas teknis pada rapat kerja berikutnya."
        ),
        "photos": ["kunker-komisi-iii-1.jpg", "kunker-komisi-iii-2.jpg"],
    },
    {
        "slug": "rdp-komisi-iv",
        "title": "Rapat Dengar Pendapat Komisi IV bersama Tenaga Kesehatan",
        "category": "Rapat Dengar Pendapat",
        "date": date(2026, 9, 30),
        "time": ("13.00", "16.00"),
        "location": "Ruang Rapat Komisi IV, Gedung DPRD Provinsi Riau",
        "address": "Jl. Jenderal Sudirman No. 1, Pekanbaru, Riau",
        "commissions": ["IV"],
        "members": [13, 14],
        "status": STATUS_PUBLISHED,
        "description": (
            "Komisi IV menerima aspirasi organisasi profesi tenaga kesehatan terkait pemerataan tenaga "
            "medis di daerah terpencil, status kepegawaian, dan insentif layanan.\n\n"
            "Komisi IV berkomitmen mendorong revisi kebijakan daerah agar distribusi tenaga kesehatan "
            "lebih merata, khususnya di puskesmas kepulauan dan wilayah perbatasan."
        ),
        "photos": ["rdp-komisi-iv-1.jpg", "rdp-komisi-iv-2.jpg"],
    },
    {
        "slug": "reses-komisi-i",
        "title": "Reses Masa Sidang III di Daerah Pemilihan Riau I",
        "category": "Reses",
        "date": date(2026, 9, 22),
        "time": ("08.30", "16.30"),
        "location": "Balai Desa Kubang Jaya, Kecamatan Siak Hulu",
        "address": "Kabupaten Kampar, Riau",
        "commissions": ["I"],
        "members": [5, 6, 7, 1],
        "status": STATUS_PUBLISHED,
        "description": (
            "Anggota DPRD Provinsi Riau melaksanakan reses di Daerah Pemilihan Riau I untuk menyerap "
            "aspirasi masyarakat terkait pelayanan publik, infrastruktur dasar, dan legalitas lahan.\n\n"
            "Warga menyampaikan kebutuhan perbaikan jalan usaha tani, penerangan jalan, serta percepatan "
            "pengurusan sertifikat tanah. Seluruh aspirasi dicatat sebagai bahan penyusunan pokok-pokok "
            "pikiran DPRD."
        ),
        "photos": ["reses-komisi-i-1.jpg", "reses-komisi-i-2.jpg"],
    },
    {
        "slug": "sosialisasi-perda",
        "title": "Sosialisasi Perda Perlindungan Anak di Sekolah Dasar",
        "category": "Sosialisasi",
        "date": date(2026, 9, 15),
        "time": ("09.00", "11.30"),
        "location": "SD Negeri 12 Pekanbaru",
        "address": "Kecamatan Sukajadi, Pekanbaru, Riau",
        "commissions": ["IV"],
        "members": [13, 14, 2],
        "status": STATUS_PUBLISHED,
        "description": (
            "Komisi IV bersama Dinas Pendidikan menggelar sosialisasi Peraturan Daerah tentang "
            "Penyelenggaraan Perlindungan Anak kepada guru, orang tua, dan peserta didik.\n\n"
            "Kegiatan menekankan pencegahan kekerasan di lingkungan sekolah, peran satuan tugas, serta "
            "mekanisme pelaporan yang aman dan ramah anak."
        ),
        "photos": ["sosialisasi-perda-1.jpg", "sosialisasi-perda-2.jpg"],
    },
    {
        "slug": "monitoring-siak",
        "title": "Monitoring Infrastruktur Jalan Provinsi di Kabupaten Siak",
        "category": "Monitoring",
        "date": date(2026, 9, 5),
        "time": ("08.00", "14.00"),
        "location": "Jalan Provinsi Siak–Pekanbaru",
        "address": "Kabupaten Siak, Riau",
        "commissions": ["III"],
        "members": [11, 12, 3],
        "status": STATUS_PUBLISHED,
        "description": (
            "Komisi III meninjau kondisi ruas jalan provinsi di Kabupaten Siak yang menjadi jalur utama "
            "distribusi hasil perkebunan.\n\n"
            "Hasil monitoring menemukan beberapa titik rusak berat yang memerlukan penanganan segera. "
            "Komisi III akan meminta dinas teknis menyusun rencana perbaikan sebelum musim penghujan."
        ),
        "photos": ["monitoring-siak-1.jpg", "monitoring-siak-2.jpg"],
    },
    {
        "slug": "kerja-komisi-v",
        "title": "Rapat Kerja Komisi V Penanganan Karhutla",
        "category": "Rapat Kerja",
        "date": date(2026, 8, 28),
        "time": ("10.00", "13.00"),
        "location": "Ruang Rapat Komisi V, Gedung DPRD Provinsi Riau",
        "address": "Jl. Jenderal Sudirman No. 1, Pekanbaru, Riau",
        "commissions": ["V"],
        "members": [15, 16, 4],
        "status": STATUS_PUBLISHED,
        "description": (
            "Komisi V membahas kesiapsiagaan daerah dalam menghadapi kebakaran hutan dan lahan, termasuk "
            "ketersediaan personel, peralatan, dan anggaran operasi.\n\n"
            "Komisi V mendorong penguatan koordinasi lintas sektor serta keterlibatan masyarakat dalam "
            "pencegahan pembukaan lahan dengan cara membakar."
        ),
        "photos": ["kerja-komisi-v-1.jpg", "kerja-komisi-v-2.jpg"],
    },
    {
        "slug": "audiensi-pesisir",
        "title": "Audiensi Masyarakat Pesisir bersama Komisi II dan Komisi V",
        "category": "Rapat Dengar Pendapat",
        "date": date(2026, 8, 19),
        "time": ("14.00", "16.30"),
        "location": "Ruang Rapat Utama, Gedung DPRD Provinsi Riau",
        "address": "Jl. Jenderal Sudirman No. 1, Pekanbaru, Riau",
        "commissions": ["II", "V"],
        "members": [8, 10, 15, 16],
        "status": STATUS_PUBLISHED,
        "description": (
            "Perwakilan masyarakat pesisir menyampaikan aspirasi mengenai akses permodalan usaha, "
            "harga hasil tangkapan, dan kerusakan ekosistem mangrove.\n\n"
            "Komisi II dan Komisi V sepakat menindaklanjuti aspirasi melalui rapat bersama dinas kelautan, "
            "koperasi, dan lingkungan hidup."
        ),
        "photos": ["audiensi-pesisir-1.jpg", "audiensi-pesisir-2.jpg"],
    },
    {
        "slug": "pelantikan-paw",
        "title": "Pelantikan Anggota Pengganti Antar Waktu DPRD Riau",
        "category": "Pelantikan",
        "date": date(2026, 8, 10),
        "time": ("09.00", "10.30"),
        "location": "Ruang Rapat Paripurna, Gedung DPRD Provinsi Riau",
        "address": "Jl. Jenderal Sudirman No. 1, Pekanbaru, Riau",
        "commissions": ["I", "II", "III", "IV", "V"],
        "members": [1, 2, 3, 4, 5],
        "status": STATUS_DRAFT,
        "description": (
            "Rapat Paripurna Khusus pelantikan dan pengambilan sumpah anggota Pengganti Antar Waktu "
            "DPRD Provinsi Riau. Dokumen ini masih dalam proses penyuntingan oleh tim humas."
        ),
        "photos": ["pelantikan-paw-1.jpg", "pelantikan-paw-2.jpg"],
    },
    {
        "slug": "rakor-akhir-tahun",
        "title": "Rapat Koordinasi Akhir Tahun 2025",
        "category": "Rapat Kerja",
        "date": date(2025, 12, 18),
        "time": ("09.00", "12.00"),
        "location": "Ruang Rapat Utama, Gedung DPRD Provinsi Riau",
        "address": "Jl. Jenderal Sudirman No. 1, Pekanbaru, Riau",
        "commissions": ["I", "II"],
        "members": [1, 2, 3],
        "status": STATUS_ARCHIVED,
        "description": (
            "Rapat koordinasi evaluasi kinerja akhir tahun 2025 yang membahas capaian program, "
            "serapan anggaran, dan rencana kerja tahun berikutnya. Dokumentasi diarsipkan sebagai "
            "referensi historis."
        ),
        "photos": ["rakor-akhir-tahun-1.jpg", "rakor-akhir-tahun-2.jpg"],
    },
]

USERS = [
    ("superadmin", "Riau#Admin2026", "Administrator SIDEWA", ROLE_SUPERADMIN, None),
    ("admin", "Admin#Riau2026", "Sekretariat DPRD Riau", ROLE_ADMIN, None),
    ("humas", "Humas#Riau2026", "Tim Humas DPRD Riau", ROLE_HUMAS, None),
    ("komisi1", "Komisi1#Riau2026", "Staf Komisi I", ROLE_STAF, "I"),
    ("komisi2", "Komisi2#Riau2026", "Staf Komisi II", ROLE_STAF, "II"),
    ("komisi3", "Komisi3#Riau2026", "Staf Komisi III", ROLE_STAF, "III"),
    ("komisi4", "Komisi4#Riau2026", "Staf Komisi IV", ROLE_STAF, "IV"),
    ("komisi5", "Komisi5#Riau2026", "Staf Komisi V", ROLE_STAF, "V"),
    ("pimpinan", "Pimpinan#Riau2026", "Pimpinan DPRD Riau", ROLE_PIMPINAN, None),
]


def _reset(db: Session) -> None:
    for model in (
        FaceDetection,
        ActivityPhoto,
        ActivityMember,
        ApiToken,
        AuditLog,
        MemberFace,
        Member,
        Activity,
        User,
        Commission,
    ):
        db.execute(delete(model))
    db.execute(delete(activity_commissions))
    db.commit()


def _wipe_media(db: Session) -> None:
    photos = db.query(ActivityPhoto).all()
    faces = db.query(MemberFace).all()
    members = db.query(Member).all()
    for photo in photos:
        delete_paths(photo.file_path, photo.thumb_path)
    for face in faces:
        delete_paths(face.image_path)
    for member in members:
        delete_paths(member.portrait_path)


def seed_demo(db: Session, *, force: bool = False) -> dict:
    if db.query(Commission).count() and not force:
        return {
            "skipped": True,
            "reason": "Database sudah berisi data. Gunakan --force untuk menimpa.",
        }

    if force:
        _wipe_media(db)
        _reset(db)

    commissions: dict[str, Commission] = {}
    for item in COMMISSIONS:
        commission = Commission(**item)
        db.add(commission)
        commissions[item["code"]] = commission
    db.flush()

    users: dict[str, User] = {}
    for username, password, full_name, role, commission_code in USERS:
        user = User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            role=role,
            commission_id=commissions[commission_code].id if commission_code else None,
            is_active=True,
            last_login_at=utcnow() if username != "superadmin" else None,
        )
        db.add(user)
        users[username] = user
    db.flush()

    members: list[Member] = []
    for portrait, full_name, position, commission_code, party, dapil in MEMBERS:
        member = Member(
            full_name=full_name,
            position=position,
            commission_id=commissions[commission_code].id if commission_code else None,
            party=party,
            dapil=dapil,
            bio=f"{full_name} merupakan anggota DPRD Provinsi Riau yang menjabat sebagai {position}.",
            is_active=True,
            consent_granted_at=utcnow(),
            consent_note="Persetujuan penggunaan data biometrik untuk dokumentasi resmi (data demo AI).",
        )
        db.add(member)
        db.flush()

        source = ASSETS / "portraits" / portrait
        if source.exists():
            rel_main, rel_thumb, _, _ = copy_seed_image(source, "members")
            member.portrait_path = rel_thumb
            db.flush()
            try:
                detected = face_engine.engine.detect_single(ASSETS / "portraits" / portrait)
                db.add(
                    MemberFace(
                        member_id=member.id,
                        image_path=rel_main,
                        encoding=detected.encoding,
                        quality=detected.quality,
                        is_primary=True,
                        source="seed",
                        created_by_id=users["admin"].id,
                    )
                )
            except face_engine.FaceEngineError as exc:
                logger.warning("Wajah %s tidak dapat didaftarkan: %s", full_name, exc)
        members.append(member)
    db.flush()

    created_activities = 0
    created_objects: list[Activity] = []
    for index, item in enumerate(ACTIVITIES, start=1):
        year = item["date"].year
        activity = Activity(
            code=f"KEG-{year}-{index:04d}",
            title=item["title"],
            description=item["description"],
            category=item["category"],
            status=item["status"],
            activity_date=item["date"],
            start_time=item["time"][0],
            end_time=item["time"][1],
            location_name=item["location"],
            location_address=item["address"],
            commission_id=commissions[item["commissions"][0]].id
            if len(item["commissions"]) == 1
            else None,
            created_by_id=users["humas"].id,
            published_at=datetime.combine(item["date"], time(9, 0))
            if item["status"] == STATUS_PUBLISHED
            else None,
            view_count=12 + index * 7,
        )
        activity.commissions = [commissions[code] for code in item["commissions"]]
        db.add(activity)
        db.flush()

        for member_index in item["members"]:
            db.add(
                ActivityMember(
                    activity_id=activity.id,
                    member_id=members[member_index - 1].id,
                    source="manual",
                    confirmed=True,
                    added_by_id=users["humas"].id,
                )
            )

        for photo_index, filename in enumerate(item["photos"], start=1):
            source = ASSETS / "activities" / filename
            if not source.exists():
                continue
            rel_main, rel_thumb, width, height = copy_seed_image(source, "activities")
            photo = ActivityPhoto(
                activity_id=activity.id,
                file_path=rel_main,
                thumb_path=rel_thumb,
                width=width,
                height=height,
                caption=f"Dokumentasi {item['title']}",
                status="pending",
                sort_order=photo_index,
                uploaded_by_id=users["humas"].id,
            )
            db.add(photo)
        created_activities += 1
        created_objects.append(activity)

    # Jejak audit yang realistis agar halaman riwayat tidak kosong.
    for activity in created_objects:
        uploaded_at = datetime.combine(activity.activity_date, time(10, 0))
        db.add(
            AuditLog(
                actor_id=users["humas"].id,
                actor_name=users["humas"].full_name,
                action="ACTIVITY_CREATE",
                entity_type="activity",
                entity_id=activity.id,
                summary=f"Mengunggah dokumentasi {activity.code} — {activity.title}",
                created_at=uploaded_at,
            )
        )
        if activity.status == STATUS_PUBLISHED:
            db.add(
                AuditLog(
                    actor_id=users["humas"].id,
                    actor_name=users["humas"].full_name,
                    action="ACTIVITY_PUBLISH",
                    entity_type="activity",
                    entity_id=activity.id,
                    summary=f"Menerbitkan kegiatan {activity.code}",
                    created_at=datetime.combine(activity.activity_date, time(10, 30)),
                )
            )
        elif activity.status == STATUS_ARCHIVED:
            db.add(
                AuditLog(
                    actor_id=users["admin"].id,
                    actor_name=users["admin"].full_name,
                    action="ACTIVITY_ARCHIVE",
                    entity_type="activity",
                    entity_id=activity.id,
                    summary=f"Mengarsipkan kegiatan {activity.code} sebagai referensi historis",
                    created_at=datetime.combine(activity.activity_date, time(10, 30)),
                )
            )

    db.add(
        AuditLog(
            actor_id=users["superadmin"].id,
            actor_name=users["superadmin"].full_name,
            action="USER_CREATE",
            entity_type="system",
            summary="Inisialisasi data demo SIDEWA DPRD Provinsi Riau",
            detail={"activities": created_activities, "members": len(members)},
        )
    )
    db.commit()

    # Proses wajah untuk seluruh foto demo.
    photos = db.query(ActivityPhoto).filter(ActivityPhoto.status == "pending").all()
    for photo in photos:
        jobs.process_photo(photo.id)

    return {
        "skipped": False,
        "commissions": len(commissions),
        "users": len(users),
        "members": len(members),
        "activities": created_activities,
        "photos": len(photos),
    }


def demo_credentials() -> list[dict]:
    labels = {
        "superadmin": "Super Admin",
        "admin": "Administrator",
        "humas": "Tim Humas",
        "komisi1": "Staf Komisi I",
        "komisi2": "Staf Komisi II",
        "komisi3": "Staf Komisi III",
        "komisi4": "Staf Komisi IV",
        "komisi5": "Staf Komisi V",
        "pimpinan": "Pimpinan",
    }
    return [
        {"username": username, "password": password, "label": labels.get(username, username)}
        for username, password, *_ in USERS
    ]
