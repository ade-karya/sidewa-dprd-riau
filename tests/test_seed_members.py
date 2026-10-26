"""Pengujian kelengkapan data anggota DPRD Riau pada seed demo."""

from collections import Counter


def test_seed_members_match_dprd_riau_2024_2029(seeded_client):
    from app.database import SessionLocal
    from app.models import Commission, Member

    _, _ = seeded_client
    db = SessionLocal()
    try:
        members = db.query(Member).all()
        assert len(members) == 65
        assert len({member.full_name for member in members}) == 65

        by_commission = Counter(
            member.commission.code if member.commission else None for member in members
        )
        assert by_commission == {
            "I": 11,
            "II": 13,
            "III": 8,
            "IV": 16,
            "V": 13,
            None: 4,
        }

        bidang = {
            commission.code: commission.bidang for commission in db.query(Commission).all()
        }
        assert bidang == {
            "I": "Pemerintahan dan Hukum",
            "II": "Perekonomian",
            "III": "Keuangan",
            "IV": "Pembangunan",
            "V": "Kesejahteraan Rakyat",
        }

        names = {member.full_name for member in members}
        assert "Kaderismanto" in names
        assert "H. Parisman Ihwan, S.E., M.M." in names
        assert "H. Ahmad Tarmizi, Lc., M.A." in names
        assert "H. Budiman Lubis" in names
        assert "H. Indra Gunawan Eet, Ph.D." in names
    finally:
        db.close()
