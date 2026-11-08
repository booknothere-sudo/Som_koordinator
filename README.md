# Yoshlar kengashi

## Lokal backendni ishga tushirish

Python 3.12 yoki undan yangisini o‘rnating. Dastlabki adminni xavfsiz yaratish uchun PowerShell’da admin emailini belgilang va parolni terminaldan kiriting:

```powershell
$env:KENGASH_BOOTSTRAP_ADMIN_EMAIL = "admin@example.uz"
$env:KENGASH_BOOTSTRAP_ADMIN_PASSWORD = Read-Host "Initial admin password"
python server.py
Remove-Item Env:KENGASH_BOOTSTRAP_ADMIN_EMAIL, Env:KENGASH_BOOTSTRAP_ADMIN_PASSWORD
```

Parol kamida 12 belgidan iborat bo‘lsin. Birinchi admin yaratilgach, shu environment qiymatlarini terminaldan tozalang. Admin role’i mavjud bo‘lsa, keyingi ishga tushirishlarda bootstrap hisob yaratilmaydi.

Brauzerda `http://127.0.0.1:8000/main.html` manzilini oching. Sayt public statistikani SQLite’dan oladi; kirish/ro‘yxatdan o‘tish, dekanat verifikatsiyasi, profil sozlamalari, klub/reja/hisobot API’lari va saylov ovozlari SQLite’da yuritiladi.

SQLite bazasi Windows’da `%LOCALAPPDATA%\YoshlarKengashi\yoshlar.sqlite3` manzilida turadi. A’zolar limiti standart holatda 20; `KENGASH_MAX_MEMBERS` bilan o‘zgartirish mumkin. Portni `KENGASH_PORT` orqali sozlang.

## Tekshiruv

```powershell
python -m unittest -v test_server
```

Backend faqat `127.0.0.1`da tinglaydi. Bu bosqich production deployment emas: HTTPS, login rate limiting, email/parolni tiklash, admin rol boshqaruv UI’si, kalitlarni boshqarish, backup/restore va load/security review hali kerak. Uni internetga ochiq joylashtirmang.
