# API SIDEWA v1

Basis URL: `/api/v1`. Semua endpoint memerlukan autentikasi.

## Autentikasi

- **Sesi**: cookie sesi + CSRF (untuk metode tulis).
- **Bearer token**: `Authorization: Bearer <token>`. Token dibuat di `/profil` (menu Token API) atau via CLI. Metode tulis melalui Bearer tidak memerlukan CSRF.

## Endpoint

| Metode | Path | Deskripsi |
|---|---|---|
| GET | `/me` | Profil pengguna terautentikasi |
| GET | `/commissions` | Daftar komisi |
| GET | `/members` | Cari anggota (`q`, `commission`, `limit`, `offset`) |
| GET | `/activities` | Daftar kegiatan (`q`, `commission`, `category`, `location`, `date_from`, `date_to`, `member_id`, `page`, `per_page`) |
| GET | `/activities/{id}` | Detail kegiatan |
| POST | `/search/face` | Pencarian berdasarkan wajah (multipart `photo`) |
| GET | `/stats` | Statistik dashboard |

Respons dibungkus `{ "data": ..., "meta": ... }`.

## Contoh

```bash
curl -H "Authorization: Bearer $TOKEN" https://sidewa.example/api/v1/me
curl -H "Authorization: Bearer $TOKEN" \
     -F "photo=@foto.jpg" \
     https://sidewa.example/api/v1/search/face
```
