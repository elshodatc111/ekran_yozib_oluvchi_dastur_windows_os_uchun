# Ekran Yozuvchi (MVP, v0.1.0)

Zoom darslarini (2–3 soat) to'liq yozib olish uchun sodda ekran yozuvchi: ekran + mikrofon + kompyuter ovozi → bitta `.mp4` fayl.
Windows 10/11 (64-bit). Admin huquqi kerak emas.

## Birinchi ishga tushirish (ishlab chiqish rejimi)
1. Python 3.11 (64-bit) o'rnating (python.org, "Add to PATH" belgisi bilan).
2. `setup.bat` — virtual muhit, kutubxonalar va FFmpeg'ni o'rnatadi.
3. `run.bat` — dasturni ishga tushiradi (xatolarni ko'rish uchun `run_debug.bat`).

## Foydalanish
- **Yozishni boshlash** → **Pauza / Davom etish** → **To'xtatish** (30 soniyadan uzun yozuvda tasdiq so'raydi).
- Taymer faqat faol yozuv vaqtini ko'rsatadi (pauza hisobga olinmaydi).
- **MIK / DIN** chiziqlari — mikrofon va kompyuter ovozi darajasi; yonidagi tugma ovozni o'chiradi/yoqadi.
- Videolar standart bo'yicha tizim diskidan boshqa eng bo'sh diskdagi `Yozuvlar` papkasiga saqlanadi (Sozlamalarda o'zgartiriladi).
- Yozuv paytida `_vaqtinchalik` papkasida xom fayllar turadi; to'xtatilgach MP4 yig'iladi va ular o'chiriladi.
  Kompyuter o'chib qolsa, keyingi ishga tushirishda yozuv avtomatik tiklanadi (`tiklangan_...mp4`).
- Dastur oynasi doim eng ustida; Windows 10 (2004+) da yozuvga/Zoom ulashishiga tushmaydi (Sozlamalarda o'chiriladi).

## O'rnatuvchi (.exe) yig'ish
`build.bat` — PyInstaller bilan `dist\EkranYozuvchi\` yig'adi (FFmpeg ichiga ko'chiriladi).
Inno Setup o'rnatilgan bo'lsa, `installer_out\EkranYozuvchi_Setup.exe` ham yaratiladi
(jim o'rnatish: `EkranYozuvchi_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES`).

## Tuzilma
```
main.py                      kirish nuqtasi
ekran_yozuvchi/
  app.py  config.py  paths.py
  core/  audio_capture.py  video_capture.py  encoder.py  recorder.py
         profiles.py  levels.py  disk.py  winutil.py
  ui/    main_window.py  settings_panel.py  level_bar.py  widgets.py  icons.py  theme.py
tests/   test_units.py  test_integration.py  test_ui.py
```

## Testlar (Windows shart emas)
```
python -m unittest tests.test_units
EKRAN_FFMPEG=<ffmpeg yo'li> python -m unittest tests.test_integration tests.test_ui
```

## Texnik eslatmalar
- Video: dxcam (Desktop Duplication) → FFmpeg (BGRA, CFR); zaxira: mss. Kodlovchi avtomatik: NVENC → QuickSync → AMF → x264.
- Ovoz: mikrofon (WASAPI) + loopback (PyAudioWPatch) → 48 kHz → AAC 192k. Sukunat vaqtida ham ovoz/video sinxron qoladi.
- Sozlamalar: `%APPDATA%\EkranYozuvchi\config.json`, jurnal: `%APPDATA%\EkranYozuvchi\logs\`.
- Hozircha yo'q (v2): aks-sado (echo) kamaytirish, tezkor tugmalar, Windows 7/8 qo'llovi.
