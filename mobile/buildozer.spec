[app]

# Назва застосунку
title = ZP Patronat

# Ім'я пакета (латиниця, без пробілів)
package.name = zppatronat
package.domain = ua.patronat.zp

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 1.0

# Залежності
requirements = python3,kivy==2.3.0

# Орієнтація
orientation = portrait

# Повноекранний режим вимкнено
fullscreen = 0

# Іконка (за бажанням покладіть icon.png у цю папку і розкоментуйте)
# icon.filename = %(source.dir)s/icon.png

# Кольори splash / вимоги
android.presplash_color = #1a1a1a

# API / NDK
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

# Дозволяємо резервне копіювання
android.allow_backup = True

# Приймаємо ліцензії SDK автоматично (для CI)
android.accept_sdk_license = True

# Фіксуємо python-for-android на стабільному релізі (Python 3.11.5),
# бо master збирає під Python 3.14, несумісний з Kivy 2.3.0 (помилка _PyLong_AsByteArray).
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 0
