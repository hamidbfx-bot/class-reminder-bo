"""
تست سریع توکن و چت‌آیدی تلگرام
---------------------------------
این فقط یک پیام تست میفرسته تا مطمئن شیم توکن و چت‌آیدی درستن.
هیچ ربطی به گیت‌هاب یا Firestore نداره - فقط رو کامپیوتر خودت اجرا میشه.

نحوه اجرا:
1. pip install requests
2. توکن و چت‌آیدی رو پایین همین فایل، بین دو تا "" بنویس
3. python quick_test.py
"""

import requests

TELEGRAM_TOKEN = "اینجا توکن رو بنویس"
CHAT_ID = "اینجا چت‌آیدی رو بنویس"

url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
resp = requests.post(url, data={"chat_id": CHAT_ID, "text": "✅ Test message - if you see this, it works!"})

print("Status code:", resp.status_code)
print("Response:", resp.json())
