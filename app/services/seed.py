"""Data demo SIDEWA untuk DPRD Provinsi Riau.

Susunan komisi dan daftar anggota mengikuti DPRD Provinsi Riau masa jabatan
2024--2029 (sumber: laman resmi DPRD Provinsi Riau dan pemberitaan terkait).
Data biometrik tidak disertakan untuk anggota asli; foto potret pada aset demo
dibuat dengan AI (this-person-does-not-exist.com) dan tidak dipakai untuk
mewakili wajah orang sungguhan.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, time
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..config import BASE_DIR, settings
from ..constants import (
    ROLE_ADMIN,
    ROLE_HUMAS,
    ROLE_PIMPINAN,
    ROLE_STAF,
    ROLE_STAF_HUMAS,
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
    HumasStaff,
    HumasStaffAccount,
    HumasStaffFaceLogin,
    MediaMention,
    Member,
    MemberAccount,
    MemberFace,
    MemberFaceLogin,
    PressRelease,
    SentimentRun,
    User,
    activity_commissions,
    utcnow,
)
from ..security import generate_password, hash_password
from . import face_engine, jobs
from .images import ImageValidationError, copy_seed_image, delete_image, delete_paths

logger = logging.getLogger("sidewa.seed")

ASSETS = BASE_DIR / "seed_assets"
STAFF_PORTRAIT_DIR = ASSETS / "staff_portraits"

COMMISSIONS = [
    {
        "code": "I",
        "name": "Komisi I",
        "bidang": "Pemerintahan dan Hukum",
        "description": (
            "Membidangi pemerintahan umum, ketertiban dan keamanan, kependudukan, komunikasi/pers, "
            "hukum dan HAM, kepegawaian dan aparatur, sosial politik, pertanahan, perlindungan "
            "konsumen, serta perjanjian internasional di daerah."
        ),
        "color": "#7E4890",
        "sort_order": 1,
    },
    {
        "code": "II",
        "name": "Komisi II",
        "bidang": "Perekonomian",
        "description": (
            "Membidangi perekonomian, perindustrian dan perdagangan, pertanian, perikanan, "
            "peternakan, perkebunan, kehutanan, pengadaan pangan dan logistik, koperasi dan UKM, "
            "potensi wilayah laut daerah, serta pariwisata."
        ),
        "color": "#3C8DAD",
        "sort_order": 2,
    },
    {
        "code": "III",
        "name": "Komisi III",
        "bidang": "Keuangan",
        "description": (
            "Membidangi keuangan daerah, aset daerah, perpajakan dan retribusi, serta pengelolaan "
            "kas daerah dan perusahaan daerah."
        ),
        "color": "#C08A2E",
        "sort_order": 3,
    },
    {
        "code": "IV",
        "name": "Komisi IV",
        "bidang": "Pembangunan",
        "description": (
            "Membidangi pekerjaan umum, perhubungan, pertambangan dan energi, serta lingkungan hidup."
        ),
        "color": "#5B8C5A",
        "sort_order": 4,
    },
    {
        "code": "V",
        "name": "Komisi V",
        "bidang": "Kesejahteraan Rakyat",
        "description": (
            "Membidangi ketenagakerjaan dan transmigrasi, pendidikan dan kebudayaan, ilmu pengetahuan "
            "dan teknologi, kepemudaan dan olahraga, agama, sosial, kesehatan, keluarga berencana, "
            "pengembangan peranan wanita, museum dan cagar budaya, penanggulangan bencana, serta "
            "pemberdayaan masyarakat desa."
        ),
        "color": "#B85C7A",
        "sort_order": 5,
    },
]

MEMBERS = [
    # Pimpinan DPRD (tidak tergabung dalam komisi)
    {
        "name": "Kaderismanto",
        "position": "Ketua DPRD",
        "commission": None,
        "party": "PDI Perjuangan",
        "dapil": "Riau 5",
    },
    {
        "name": "H. Parisman Ihwan, S.E., M.M.",
        "position": "Wakil Ketua DPRD",
        "commission": None,
        "party": "Golkar",
        "dapil": "Riau 1",
    },
    {
        "name": "H. Ahmad Tarmizi, Lc., M.A.",
        "position": "Wakil Ketua DPRD",
        "commission": None,
        "party": "PKS",
        "dapil": "Riau 1",
    },
    {
        "name": "H. Budiman Lubis",
        "position": "Wakil Ketua DPRD",
        "commission": None,
        "party": "Gerindra",
        "dapil": "Riau 3",
    },
    # Komisi I — Pemerintahan dan Hukum
    {
        "name": "Nur Azmi Hasyim, S.T., M.M.",
        "position": "Ketua Komisi I",
        "commission": "I",
        "party": "Demokrat",
        "dapil": "Riau 5",
    },
    {
        "name": "H. Ali Rahmat Harahap, S.E.",
        "position": "Wakil Ketua Komisi I",
        "commission": "I",
        "party": "NasDem",
        "dapil": "Riau 4",
    },
    {
        "name": "H. M. Amal Fathullah A., Lc., M.A.",
        "position": "Sekretaris Komisi I",
        "commission": "I",
        "party": "PKS",
        "dapil": "Riau 2",
    },
    {
        "name": "Andi Darma Taufik, S.Kep.",
        "position": "Anggota Komisi I",
        "commission": "I",
        "party": "PDI Perjuangan",
        "dapil": "Riau 7",
    },
    {
        "name": "Nalladia Ayu Rokan",
        "position": "Anggota Komisi I",
        "commission": "I",
        "party": "Golkar",
        "dapil": "Riau 4",
    },
    {
        "name": "Hj. Zulaikhah, S.Sos., M.E.",
        "position": "Anggota Komisi I",
        "commission": "I",
        "party": "Golkar",
        "dapil": "Riau 7",
    },
    {
        "name": "H. Ayat Cahyadi, S.Si.",
        "position": "Anggota Komisi I",
        "commission": "I",
        "party": "PKS",
        "dapil": "Riau 1",
    },
    {
        "name": "H. Hardianto, S.E., M.M.",
        "position": "Anggota Komisi I",
        "commission": "I",
        "party": "Gerindra",
        "dapil": "Riau 5",
    },
    {
        "name": "H. M. Sumardany Zirnata, S.T., M.Sc.",
        "position": "Anggota Komisi I",
        "commission": "I",
        "party": "Demokrat",
        "dapil": "Riau 1",
    },
    {
        "name": "Ade Firmansyah, S.Sos.",
        "position": "Anggota Komisi I",
        "commission": "I",
        "party": "PKB",
        "dapil": "Riau 8",
    },
    {
        "name": "dr. H. Sunaryo",
        "position": "Anggota Komisi I",
        "commission": "I",
        "party": "PAN",
        "dapil": "Riau 5",
    },
    # Komisi II — Perekonomian
    {
        "name": "H. Adam Syafa'at, M.A.",
        "position": "Ketua Komisi II",
        "commission": "II",
        "party": "PKS",
        "dapil": "Riau 3",
    },
    {
        "name": "Hardi Chandra",
        "position": "Wakil Ketua Komisi II",
        "commission": "II",
        "party": "PDI Perjuangan",
        "dapil": "Riau 3",
    },
    {
        "name": "Androy Aderianda, S.H., M.H.",
        "position": "Sekretaris Komisi II",
        "commission": "II",
        "party": "Gerindra",
        "dapil": "Riau 6",
    },
    {
        "name": "Soniwati, S.H.",
        "position": "Anggota Komisi II",
        "commission": "II",
        "party": "PDI Perjuangan",
        "dapil": "Riau 6",
    },
    {
        "name": "Dodi Nefeldi SPBU, S.H.",
        "position": "Anggota Komisi II",
        "commission": "II",
        "party": "PDI Perjuangan",
        "dapil": "Riau 8",
    },
    {
        "name": "Evi Juliana, S.E., M.M.",
        "position": "Anggota Komisi II",
        "commission": "II",
        "party": "Golkar",
        "dapil": "Riau 3",
    },
    {
        "name": "Raja Jaya Dinata, S.E.",
        "position": "Anggota Komisi II",
        "commission": "II",
        "party": "Golkar",
        "dapil": "Riau 2",
    },
    {
        "name": "H. Sutan Sari Gunung",
        "position": "Anggota Komisi II",
        "commission": "II",
        "party": "PKS",
        "dapil": "Riau 4",
    },
    {
        "name": "Ginda Burnama, S.T., M.T.",
        "position": "Anggota Komisi II",
        "commission": "II",
        "party": "Gerindra",
        "dapil": "Riau 1",
    },
    {
        "name": "Monang Eliezer Pasaribu, S.Sos., M.Si.",
        "position": "Anggota Komisi II",
        "commission": "II",
        "party": "Demokrat",
        "dapil": "Riau 6",
    },
    {
        "name": "Siti Aisyah, S.Kom.",
        "position": "Anggota Komisi II",
        "commission": "II",
        "party": "PKB",
        "dapil": "Riau 7",
    },
    {
        "name": "M. Hasby Assodiqi, S.Sos.",
        "position": "Anggota Komisi II",
        "commission": "II",
        "party": "NasDem",
        "dapil": "Riau 3",
    },
    {
        "name": "H. Ikbal Sayuti",
        "position": "Anggota Komisi II",
        "commission": "II",
        "party": "PPP",
        "dapil": "Riau 7",
    },
    # Komisi III — Keuangan
    {
        "name": "H. Edi Basri, S.H., M.Si.",
        "position": "Ketua Komisi III",
        "commission": "III",
        "party": "Gerindra",
        "dapil": "Riau 2",
    },
    {
        "name": "Misliadi, S.H.I., M.M.",
        "position": "Wakil Ketua Komisi III",
        "commission": "III",
        "party": "PKB",
        "dapil": "Riau 5",
    },
    {
        "name": "Eva Yuliana, S.E.",
        "position": "Sekretaris Komisi III",
        "commission": "III",
        "party": "Demokrat",
        "dapil": "Riau 2",
    },
    {
        "name": "Sofyan, S.Pd.I., M.Si.",
        "position": "Anggota Komisi III",
        "commission": "III",
        "party": "PDI Perjuangan",
        "dapil": "Riau 5",
    },
    {
        "name": "Diski",
        "position": "Anggota Komisi III",
        "commission": "III",
        "party": "PAN",
        "dapil": "Riau 2",
    },
    {
        "name": "H. Abdullah, S.Pd.",
        "position": "Anggota Komisi III",
        "commission": "III",
        "party": "PKS",
        "dapil": "Riau 6",
    },
    {
        "name": "Imustiar, S.IP.",
        "position": "Anggota Komisi III",
        "commission": "III",
        "party": "Golkar",
        "dapil": "Riau 6",
    },
    {
        "name": "Efrinaldi, S.H.",
        "position": "Anggota Komisi III",
        "commission": "III",
        "party": "NasDem",
        "dapil": "Riau 2",
    },
    # Komisi IV — Pembangunan
    {
        "name": "Ma'mun Solikhin, S.Ag.",
        "position": "Ketua Komisi IV",
        "commission": "IV",
        "party": "PDI Perjuangan",
        "dapil": "Riau 2",
    },
    {
        "name": "Darmalis, S.E.",
        "position": "Wakil Ketua Komisi IV",
        "commission": "IV",
        "party": "Golkar",
        "dapil": "Riau 4",
    },
    {
        "name": "Zulfadhli Alhamdi, A.Md.",
        "position": "Sekretaris Komisi IV",
        "commission": "IV",
        "party": "Gerindra",
        "dapil": "Riau 7",
    },
    {
        "name": "Suyadi, S.P.",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "PDI Perjuangan",
        "dapil": "Riau 4",
    },
    {
        "name": "Jons Ade Nopendra",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "Golkar",
        "dapil": "Riau 8",
    },
    {
        "name": "H. Khairul Umam, Lc., M.E.Sy.",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "PKS",
        "dapil": "Riau 5",
    },
    {
        "name": "Samsuri Daris, S.T., M.T.",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "PKS",
        "dapil": "Riau 7",
    },
    {
        "name": "H. Zulhendri, S.P.W.K., M.Si.",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "Gerindra",
        "dapil": "Riau 8",
    },
    {
        "name": "Dodi Saputra, S.H.",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "Demokrat",
        "dapil": "Riau 4",
    },
    {
        "name": "Manahara Napitupulu, S.H., M.H.",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "Demokrat",
        "dapil": "Riau 8",
    },
    {
        "name": "Kasir, S.T.",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "PKB",
        "dapil": "Riau 1",
    },
    {
        "name": "Muhtarom, S.Ag.",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "PKB",
        "dapil": "Riau 6",
    },
    {
        "name": "Hj. Farida H. Saad, S.E.",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "NasDem",
        "dapil": "Riau 5",
    },
    {
        "name": "Munawar Syahputra, S.H.",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "NasDem",
        "dapil": "Riau 1",
    },
    {
        "name": "Dodi Irawan, S.H.I.",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "PAN",
        "dapil": "Riau 8",
    },
    {
        "name": "Mohammad Fadel Variza",
        "position": "Anggota Komisi IV",
        "commission": "IV",
        "party": "PAN",
        "dapil": "Riau 1",
    },
    # Komisi V — Kesejahteraan Rakyat
    {
        "name": "H. Indra Gunawan Eet, Ph.D.",
        "position": "Ketua Komisi V",
        "commission": "V",
        "party": "Golkar",
        "dapil": "Riau 5",
    },
    {
        "name": "H. Abdul Kasim, S.H.",
        "position": "Wakil Ketua Komisi V",
        "commission": "V",
        "party": "PKS",
        "dapil": "Riau 5",
    },
    {
        "name": "Robin P. Hutagalung, S.H.",
        "position": "Sekretaris Komisi V",
        "commission": "V",
        "party": "PDI Perjuangan",
        "dapil": "Riau 1",
    },
    {
        "name": "Sella Pitaloka, S.A.P., M.Si.",
        "position": "Anggota Komisi V",
        "commission": "V",
        "party": "PDI Perjuangan",
        "dapil": "Riau 6",
    },
    {
        "name": "M. Alga Viqky Azmi",
        "position": "Anggota Komisi V",
        "commission": "V",
        "party": "PDI Perjuangan",
        "dapil": "Riau 5",
    },
    {
        "name": "Dra. Hj. Septina Primawati, M.M.",
        "position": "Anggota Komisi V",
        "commission": "V",
        "party": "Golkar",
        "dapil": "Riau 7",
    },
    {
        "name": "Rizal Zamzami, S.H.",
        "position": "Anggota Komisi V",
        "commission": "V",
        "party": "PKS",
        "dapil": "Riau 8",
    },
    {
        "name": "Syafrudin Iput",
        "position": "Anggota Komisi V",
        "commission": "V",
        "party": "Gerindra",
        "dapil": "Riau 4",
    },
    {
        "name": "H. Agus Triansyah",
        "position": "Anggota Komisi V",
        "commission": "V",
        "party": "Demokrat",
        "dapil": "Riau 7",
    },
    {
        "name": "Dra. Hj. Adrias",
        "position": "Anggota Komisi V",
        "commission": "V",
        "party": "PKB",
        "dapil": "Riau 2",
    },
    {
        "name": "Daniel Eka Perdana, S.H.",
        "position": "Anggota Komisi V",
        "commission": "V",
        "party": "NasDem",
        "dapil": "Riau 8",
    },
    {
        "name": "Fairus, S.Ag.",
        "position": "Anggota Komisi V",
        "commission": "V",
        "party": "PAN",
        "dapil": "Riau 6",
    },
    {
        "name": "Hj. Magdalisni",
        "position": "Anggota Komisi V",
        "commission": "V",
        "party": "Demokrat",
        "dapil": "Riau 3",
    },
]

MEMBER_PORTRAITS = {
    "Kaderismanto": "portraits_real/33.webp",
    "H. Parisman Ihwan, S.E., M.M.": "portraits_real/4.webp",
    "H. Ahmad Tarmizi, Lc., M.A.": "portraits_real/6.webp",
    "H. Budiman Lubis": "portraits_real/18.webp",
    "Nur Azmi Hasyim, S.T., M.M.": "portraits_real/41.webp",
    "H. Ali Rahmat Harahap, S.E.": "portraits_real/28.webp",
    "H. M. Amal Fathullah A., Lc., M.A.": "portraits_real/15.webp",
    "Andi Darma Taufik, S.Kep.": "portraits_real/52.webp",
    "Nalladia Ayu Rokan": "portraits_real/27.webp",
    "Hj. Zulaikhah, S.Sos., M.E.": "portraits_real/54.webp",
    "H. Ayat Cahyadi, S.Si.": "portraits_real/7.webp",
    "H. Hardianto, S.E., M.M.": "portraits_real/32.webp",
    "H. M. Sumardany Zirnata, S.T., M.Sc.": "portraits_real/9.webp",
    "Ade Firmansyah, S.Sos.": "portraits_real/58.webp",
    "dr. H. Sunaryo": "portraits_real/40.webp",
    "H. Adam Syafa'at, M.A.": "portraits_real/22.webp",
    "Hardi Chandra": "portraits_real/19.webp",
    "Androy Aderianda, S.H., M.H.": "portraits_real/43.webp",
    "Soniwati, S.H.": "portraits_real/45.webp",
    "Dodi Nefeldi SPBU, S.H.": "portraits_real/60.webp",
    "Evi Juliana, S.E., M.M.": "portraits_real/20.webp",
    "Raja Jaya Dinata, S.E.": "portraits_real/13.webp",
    "H. Sutan Sari Gunung": "portraits_real/29.webp",
    "Ginda Burnama, S.T., M.T.": "portraits_real/2.webp",
    "Monang Eliezer Pasaribu, S.Sos., M.Si.": "portraits_real/49.webp",
    "Siti Aisyah, S.Kom.": "portraits_real/50.webp",
    "M. Hasby Assodiqi, S.Sos.": "portraits_real/21.webp",
    "H. Ikbal Sayuti": "portraits_real/57.webp",
    "H. Edi Basri, S.H., M.Si.": "portraits_real/11.webp",
    "Misliadi, S.H.I., M.M.": "portraits_real/31.webp",
    "Eva Yuliana, S.E.": "portraits_real/17.webp",
    "Sofyan, S.Pd.I., M.Si.": "portraits_real/35.webp",
    "Diski": "portraits_real/16.webp",
    "H. Abdullah, S.Pd.": "portraits_real/47.webp",
    "Imustiar, S.IP.": "portraits_real/46.webp",
    "Efrinaldi, S.H.": "portraits_real/14.webp",
    "Ma'mun Solikhin, S.Ag.": "portraits_real/12.webp",
    "Darmalis, S.E.": "portraits_real/26.webp",
    "Zulfadhli Alhamdi, A.Md.": "portraits_real/51.webp",
    "Suyadi, S.P.": "portraits_real/25.webp",
    "Jons Ade Nopendra": "portraits_real/61.webp",
    "H. Khairul Umam, Lc., M.E.Sy.": "portraits_real/39.webp",
    "Samsuri Daris, S.T., M.T.": "portraits_real/55.webp",
    "H. Zulhendri, S.P.W.K., M.Si.": "portraits_real/59.webp",
    "Dodi Saputra, S.H.": "portraits_real/30.webp",
    "Manahara Napitupulu, S.H., M.H.": "portraits_real/65.webp",
    "Kasir, S.T.": "portraits_real/1.webp",
    "Muhtarom, S.Ag.": "portraits_real/42.webp",
    "Hj. Farida H. Saad, S.E.": "portraits_real/37.webp",
    "Munawar Syahputra, S.H.": "portraits_real/5.webp",
    "Dodi Irawan, S.H.I.": "portraits_real/64.webp",
    "Mohammad Fadel Variza": "portraits_real/8.webp",
    "H. Indra Gunawan Eet, Ph.D.": "portraits_real/36.webp",
    "H. Abdul Kasim, S.H.": "portraits_real/38.webp",
    "Robin P. Hutagalung, S.H.": "portraits_real/3.webp",
    "Sella Pitaloka, S.A.P., M.Si.": "portraits_real/44.webp",
    "M. Alga Viqky Azmi": "portraits_real/34.webp",
    "Dra. Hj. Septina Primawati, M.M.": "portraits_real/53.webp",
    "Rizal Zamzami, S.H.": "portraits_real/63.webp",
    "Syafrudin Iput": "portraits_real/24.webp",
    "H. Agus Triansyah": "portraits_real/56.webp",
    "Dra. Hj. Adrias": "portraits_real/10.webp",
    "Daniel Eka Perdana, S.H.": "portraits_real/62.webp",
    "Fairus, S.Ag.": "portraits_real/48.webp",
    "Hj. Magdalisni": "portraits_real/23.webp",
}

HUMAS_STAFF = [
    ("Radinal Munandar, S.STP., M.M., M.IP", "Kepala Tim Humas"),
    ("Arief Adithia Irsandi, S.STP., M.Si", "Koordinator Humas"),
    ("Wahyu Jati Wibowo", "Staf Humas & Perpustakaan"),
    ("Ayatullah Khumaini", "Staf Humas & Perpustakaan"),
    ("Afdan Syaputra", "Staf Humas & Perpustakaan"),
    ("Raja Rasmawati, S.E., M.Si", "Staf Humas & Perpustakaan"),
    ("Shinta Puji Lestari", "Staf Humas & Perpustakaan"),
    ("Risky Perdana", "Staf Humas & Perpustakaan"),
    ("Muhammad Rais, S.I.Kom", "Staf Humas & Perpustakaan"),
    ("Novita Elya", "Staf Humas & Perpustakaan"),
    ("Repan", "Staf Humas & Perpustakaan"),
    ("Muhammad Rozikin", "Staf Humas & Perpustakaan"),
    ("Rio Ary Novianto", "Staf Humas & Perpustakaan"),
    ("Marthalena Diningsih D, S.IP", "Staf Humas & Perpustakaan"),
    ("Irwan Yanofrizon", "Staf Humas & Perpustakaan"),
    ("Evantio Perdana, S.S.T", "Staf Humas & Perpustakaan"),
    ("Sukma Adefa", "Staf Humas & Perpustakaan"),
    ("Rizalman", "Staf Humas & Perpustakaan"),
    ("Yusmiati", "Staf Humas & Perpustakaan"),
    ("Hastin Atas Asih", "Staf Humas & Perpustakaan"),
    ("Nasrizan, S.Pd", "Staf Humas & Perpustakaan"),
    ("Yosie Palupi, S.E.", "Staf Humas & Perpustakaan"),
    ("Randy Eka Putra", "Staf Humas & Perpustakaan"),
    ("Marthalena, A.Md", "Staf Humas & Perpustakaan"),
    ("Reza Lia Reffino", "Staf Humas & Perpustakaan"),
    ("Roby Rahman", "Staf Humas & Perpustakaan"),
    ("Muzakir, S.Sos", "Staf Humas & Perpustakaan"),
    ("Aisyah Sri Utari", "Staf Humas & Perpustakaan"),
    ("Mhd. Fauzan Kathin, S.STP", "Staf Humas & Perpustakaan"),
    ("Muhammad Reyhan Shabrinas", "Staf Humas & Perpustakaan"),
    ("Agustinus", "Staf Humas & Perpustakaan"),
    ("Ade Karya Jaya, S.Kom", "Staf Humas & Perpustakaan"),
    ("Robi Saputra", "Staf Humas & Perpustakaan"),
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
        "members": [
            "Kaderismanto",
            "H. Parisman Ihwan, S.E., M.M.",
            "H. Ahmad Tarmizi, Lc., M.A.",
            "H. Budiman Lubis",
            "Nur Azmi Hasyim, S.T., M.M.",
            "H. Adam Syafa'at, M.A.",
        ],
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
        "members": [
            "H. Adam Syafa'at, M.A.",
            "Hardi Chandra",
            "Androy Aderianda, S.H., M.H.",
        ],
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
        "members": ["H. Edi Basri, S.H., M.Si.", "Misliadi, S.H.I., M.M."],
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
        "members": ["Ma'mun Solikhin, S.Ag.", "Darmalis, S.E."],
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
        "members": [
            "Nur Azmi Hasyim, S.T., M.M.",
            "H. Ali Rahmat Harahap, S.E.",
            "H. M. Amal Fathullah A., Lc., M.A.",
            "Kaderismanto",
        ],
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
        "members": [
            "Ma'mun Solikhin, S.Ag.",
            "Darmalis, S.E.",
            "H. Parisman Ihwan, S.E., M.M.",
        ],
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
        "members": [
            "H. Edi Basri, S.H., M.Si.",
            "Misliadi, S.H.I., M.M.",
            "Eva Yuliana, S.E.",
        ],
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
        "members": [
            "H. Indra Gunawan Eet, Ph.D.",
            "H. Abdul Kasim, S.H.",
            "H. Budiman Lubis",
        ],
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
        "members": [
            "H. Adam Syafa'at, M.A.",
            "Dodi Nefeldi SPBU, S.H.",
            "H. Indra Gunawan Eet, Ph.D.",
            "H. Abdul Kasim, S.H.",
        ],
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
        "members": [
            "Kaderismanto",
            "H. Parisman Ihwan, S.E., M.M.",
            "H. Ahmad Tarmizi, Lc., M.A.",
            "H. Budiman Lubis",
            "Nur Azmi Hasyim, S.T., M.M.",
        ],
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
        "members": [
            "Kaderismanto",
            "H. Parisman Ihwan, S.E., M.M.",
            "H. Ahmad Tarmizi, Lc., M.A.",
        ],
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
        MediaMention,
        SentimentRun,
        HumasStaffFaceLogin,
        HumasStaffAccount,
        HumasStaff,
        MemberFaceLogin,
        MemberAccount,
        FaceDetection,
        ActivityPhoto,
        ActivityMember,
        ApiToken,
        AuditLog,
        MemberFace,
        Member,
        PressRelease,
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
    login_faces = db.query(MemberFaceLogin).all()
    staff_faces = db.query(HumasStaffFaceLogin).all()
    members = db.query(Member).all()
    staff_rows = db.query(HumasStaff).all()
    for photo in photos:
        delete_paths(photo.file_path, photo.thumb_path)
    for face in faces:
        delete_paths(face.image_path)
    for face in login_faces:
        delete_paths(face.image_path)
    for face in staff_faces:
        delete_paths(face.image_path)
    for member in members:
        delete_image(member.portrait_path)
    for staff in staff_rows:
        delete_image(staff.portrait_path)


def _staff_portrait_source(index: int, full_name: str) -> Path | None:
    """Cari foto staf dari folder seed_assets/staff_portraits.

    Nama berkas yang didukung: ``01.jpg`` (nomor urut) atau nama yang
    dinormalisasi, misalnya ``radinal-munandar.jpg``.
    """
    if not STAFF_PORTRAIT_DIR.exists():
        return None
    candidates: list[Path] = []
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        candidates.append(STAFF_PORTRAIT_DIR / f"{index:02d}{suffix}")
        candidates.append(STAFF_PORTRAIT_DIR / f"{index}{suffix}")
    slug = re.sub(r"[^a-z0-9]+", "-", full_name.lower()).strip("-")
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        candidates.append(STAFF_PORTRAIT_DIR / f"{slug}{suffix}")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def seed_demo(db: Session, *, force: bool = False) -> dict:
    if settings.is_production:
        raise RuntimeError(
            "seed_demo() diblokir di production: data production tidak boleh diisi ulang. "
            "Supabase dan HF S3 harus dibiarkan apa adanya."
        )
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

    staff_rows: list[HumasStaff] = []
    for index, (full_name, position) in enumerate(HUMAS_STAFF, start=1):
        staff = HumasStaff(
            full_name=full_name,
            position=position,
            unit="Bagian Humas & Perpustakaan",
            sort_order=index,
            bio=(
                f"{full_name} bertugas sebagai {position} di Bagian Humas & "
                "Perpustakaan Sekretariat DPRD Provinsi Riau."
            ),
            is_active=True,
            consent_granted_at=utcnow(),
            consent_note="Data staf Humas Sekretariat DPRD Provinsi Riau.",
        )
        portrait_source = _staff_portrait_source(index, full_name)
        if portrait_source:
            try:
                rel_main, _, _, _ = copy_seed_image(portrait_source, "staff")
                staff.portrait_path = rel_main
            except (ImageValidationError, OSError):
                logger.warning(
                    "Foto staf %s dilewati karena berkas tidak valid: %s",
                    full_name,
                    portrait_source,
                )
        db.add(staff)
        staff_rows.append(staff)
    db.flush()

    staff_users: list[User] = []
    for staff in staff_rows:
        user = User(
            username=f"humas{staff.id}",
            full_name=staff.full_name,
            email=staff.email,
            role=ROLE_STAF_HUMAS,
            password_hash=hash_password(generate_password()),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(HumasStaffAccount(user_id=user.id, staff_id=staff.id))
        staff_users.append(user)
    db.flush()

    members: list[Member] = []
    members_by_name: dict[str, Member] = {}
    for item in MEMBERS:
        full_name = item["name"]
        position = item["position"]
        commission_code = item["commission"]
        member = Member(
            full_name=full_name,
            position=position,
            commission_id=commissions[commission_code].id if commission_code else None,
            party=item["party"],
            dapil=item["dapil"],
            bio=(
                f"{full_name} merupakan anggota DPRD Provinsi Riau masa jabatan 2024–2029 "
                f"yang menjabat sebagai {position}."
            ),
            is_active=True,
            consent_granted_at=utcnow(),
            consent_note="Potret resmi DPRD Provinsi Riau 2024–2029; persetujuan penggunaan data biometrik.",
        )
        db.add(member)
        db.flush()

        portrait_rel = MEMBER_PORTRAITS.get(full_name)
        source = ASSETS / portrait_rel if portrait_rel else None
        if source and source.exists():
            rel_main, rel_thumb, _, _ = copy_seed_image(source, "members")
            member.portrait_path = rel_main
            db.flush()
            try:
                detected = face_engine.engine.detect_single(source)
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
        members_by_name[full_name] = member
    db.flush()

    created_activities = 0
    created_objects: list[Activity] = []
    for index, item in enumerate(ACTIVITIES, start=1):
        year = item["date"].year
        creator = staff_users[(index - 1) % len(staff_users)] if staff_users else users["humas"]
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
            created_by_id=creator.id,
            published_at=datetime.combine(item["date"], time(9, 0))
            if item["status"] == STATUS_PUBLISHED
            else None,
            view_count=12 + index * 7,
        )
        activity.commissions = [commissions[code] for code in item["commissions"]]
        db.add(activity)
        db.flush()

        for member_name in item["members"]:
            db.add(
                ActivityMember(
                    activity_id=activity.id,
                    member_id=members_by_name[member_name].id,
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
                uploaded_by_id=creator.id,
            )
            db.add(photo)
        created_activities += 1
        created_objects.append(activity)

    created_releases = 0
    release_sources = [
        activity
        for activity in created_objects
        if activity.status in (STATUS_PUBLISHED, STATUS_DRAFT)
    ][:8]
    for index, activity in enumerate(release_sources, start=1):
        release_status = (
            STATUS_DRAFT if activity.status == STATUS_DRAFT else STATUS_PUBLISHED
        )
        summary = " ".join(activity.description.split())[:300]
        body = (
            f"PEKANBARU — {activity.description.strip()}\n\n"
            f"Kegiatan ini berlangsung di {activity.location_name} dan menjadi bagian "
            "dari tugas pengawasan, pembentukan peraturan daerah, serta penyerapan "
            "aspirasi masyarakat oleh DPRD Provinsi Riau.\n\n"
            "Dokumentasi lengkap kegiatan dapat diakses melalui kanal SIDEWA Sekretariat "
            "DPRD Provinsi Riau."
        )
        release = PressRelease(
            code=f"RIL-{activity.activity_date.year}-{index:04d}",
            title=activity.title,
            slug=f"rilis-{activity.code.lower()}",
            summary=summary,
            body=body,
            status=release_status,
            release_date=activity.activity_date,
            activity_id=activity.id,
            author_id=activity.created_by_id,
            published_at=datetime.combine(activity.activity_date, time(11, 0))
            if release_status == STATUS_PUBLISHED
            else None,
            view_count=8 + index * 5 if release_status == STATUS_PUBLISHED else 0,
            tags=[activity.category]
            + [commission.short_name for commission in activity.commissions[:2]],
        )
        db.add(release)
        db.flush()
        created_releases += 1
        release_actor = activity.creator or users["humas"]
        db.add(
            AuditLog(
                actor_id=release_actor.id,
                actor_name=release_actor.full_name,
                action="RELEASE_CREATE",
                entity_type="release",
                entity_id=release.id,
                summary=f"Menyusun rilis {release.code} — {release.title}",
                created_at=datetime.combine(activity.activity_date, time(10, 45)),
            )
        )
        if release_status == STATUS_PUBLISHED:
            db.add(
                AuditLog(
                    actor_id=release_actor.id,
                    actor_name=release_actor.full_name,
                    action="RELEASE_PUBLISH",
                    entity_type="release",
                    entity_id=release.id,
                    summary=f"Menerbitkan rilis {release.code}",
                    created_at=datetime.combine(activity.activity_date, time(11, 0)),
                )
            )

    # Jejak audit yang realistis agar halaman riwayat tidak kosong.
    for activity in created_objects:
        uploaded_at = datetime.combine(activity.activity_date, time(10, 0))
        actor = activity.creator or users["humas"]
        db.add(
            AuditLog(
                actor_id=actor.id,
                actor_name=actor.full_name,
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
                    actor_id=actor.id,
                    actor_name=actor.full_name,
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
            detail={"activities": created_activities, "releases": created_releases, "members": len(members)},
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
        "users": len(users) + len(staff_users),
        "members": len(members),
        "humas_staff": len(staff_rows),
        "activities": created_activities,
        "releases": created_releases,
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
