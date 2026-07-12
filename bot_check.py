"""
بات کلاس - نسخه GitHub Actions (کاملا رایگان) - با دکمه و پشتیبانی تایم‌زون
------------------------------------------------------------------------------
زمان‌هایی که توی سایت وارد میکنی، بر اساس تایم فیلیپین (Asia/Manila) در نظر گرفته میشه
و پیام‌ها هم بر همون تایم نمایش داده میشن.

این اسکریپت هر بار اجرا میشه:
1. پیام‌های جدید تلگرام رو چک میکنه، به دستورها یا دکمه‌های فشرده‌شده جواب میده
2. ۱۵ دقیقه قبل از هر کلاس و لحظه شروع کلاس، پیام میفرسته
"""

import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
CHAT_IDS = [c.strip() for c in CHAT_ID.split(",") if c.strip()]
TEACHER_NAME = os.environ.get("TEACHER_NAME", "Ma.Fe")

SCHEDULE_TIMEZONE = ZoneInfo("Asia/Manila")   # زمانی که توی سایت وارد میکنی بر این حساب میشه
DISPLAY_TIMEZONE = ZoneInfo("Asia/Manila")    # پیام‌ها و لحظه ارسال بر این حساب میشه

PROJECT_ID = "tutor-schedule-90593"
FIRESTORE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/sessions"
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

# ===== دکمه‌های زیر کیبورد تلگرام =====
BUTTON_LABELS = {
    "📅 Today": "/today",
    "📆 Tomorrow": "/tomorrow",
    "🗓️ This Week": "/thisweek",
    "📆 Next Week": "/nextweek",
    "⏭️ Next Class": "/next",
}
KEYBOARD_LAYOUT = {
    "keyboard": [
        ["📅 Today", "📆 Tomorrow"],
        ["🗓️ This Week", "📆 Next Week"],
        ["⏭️ Next Class"],
    ],
    "resize_keyboard": True,
    "one_time_keyboard": False,
}
KNOWN_COMMANDS = ("/start", "/today", "/tomorrow", "/next", "/thisweek", "/nextweek", "/week", "/addclass", "/help")


# ===================== Firestore =====================

def get_sessions():
    try:
        resp = requests.get(FIRESTORE_URL, timeout=15)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch sessions (will try again next run): {e}")
        return []
    data = resp.json()

    sessions = []
    for doc in data.get("documents", []):
        fields = doc.get("fields", {})
        day = fields.get("day", {}).get("stringValue")
        time_str = fields.get("time", {}).get("stringValue")
        week_start = fields.get("weekStart", {}).get("stringValue")

        if not (day and time_str and week_start and day in DAYS_ORDER):
            continue

        try:
            monday = datetime.strptime(week_start, "%Y-%m-%d")
            hour, minute = map(int, time_str.split(":"))
            session_date = monday + timedelta(days=DAYS_ORDER.index(day))
            session_dt = session_date.replace(
                hour=hour, minute=minute, second=0, microsecond=0, tzinfo=SCHEDULE_TIMEZONE
            )
        except ValueError:
            continue

        sessions.append({
            "id": doc["name"].split("/")[-1],
            "student": fields.get("student", {}).get("stringValue", ""),
            "subject": fields.get("subject", {}).get("stringValue", "Class"),
            "grade": fields.get("grade", {}).get("stringValue", ""),
            "note": fields.get("note", {}).get("stringValue", ""),
            "datetime": session_dt,
        })

    sessions.sort(key=lambda s: s["datetime"])
    return sessions


def add_session_to_firestore(day, time_str, student, subject, grade, week_start):
    body = {
        "fields": {
            "day": {"stringValue": day},
            "time": {"stringValue": time_str},
            "student": {"stringValue": student},
            "subject": {"stringValue": subject},
            "grade": {"stringValue": grade},
            "weekStart": {"stringValue": week_start},
            "note": {"stringValue": ""},
        }
    }
    try:
        resp = requests.post(FIRESTORE_URL, json=body, timeout=15)
        return resp.status_code in (200, 201), resp.text
    except requests.exceptions.RequestException as e:
        return False, str(e)


def local_dt(s):
    return s["datetime"].astimezone(DISPLAY_TIMEZONE)


# ===================== قالب پیام‌ها =====================

def format_time_12h(dt):
    fmt = "%#I:%M %p" if os.name == "nt" else "%-I:%M %p"
    return dt.strftime(fmt)


def greeting():
    hour = datetime.now(DISPLAY_TIMEZONE).hour
    if hour < 12:
        return f"Good morning, {TEACHER_NAME}!"
    if hour < 18:
        return f"Good afternoon, {TEACHER_NAME}!"
    return f"Good evening, {TEACHER_NAME}!"


def session_line(s):
    dt = local_dt(s)
    return f"🕕 {format_time_12h(dt)} — {s['student']} ({s['subject']}, {s['grade']})"


def reminder_message(s):
    dt = local_dt(s)
    return (
        f"🔔 {s['subject']} Class Reminder\n\n"
        f"{greeting()}\n\n"
        f"Your {s['subject'].lower()} lesson starts in 15 minutes.\n\n"
        f"👨‍🎓 Student: {s['student']}\n"
        f"🎓 Grade: {s['grade']}\n"
        f"🕕 Time: {format_time_12h(dt)}\n\n"
        "📚 Have a wonderful lesson!"
    )


def started_message(s):
    return (
        f"🟢 {s['subject']} Class Started\n\n"
        f"Your {s['subject'].lower()} lesson has started.\n\n"
        f"👨‍🎓 Student: {s['student']}\n\n"
        "✨ Have a great lesson!"
    )


# ===================== ارسال پیام =====================

def send_message(chat_id, text, with_keyboard=True):
    data = {"chat_id": chat_id, "text": text}
    if with_keyboard:
        data["reply_markup"] = json.dumps(KEYBOARD_LAYOUT)
    requests.post(f"{TELEGRAM_API}/sendMessage", data=data, timeout=15)


def set_bot_commands():
    """منوی اسلش تلگرام رو ثبت میکنه (وقتی / رو تایپ میکنی پیشنهاد میده)"""
    commands = [
        {"command": "today", "description": "Today's classes"},
        {"command": "tomorrow", "description": "Tomorrow's classes"},
        {"command": "thisweek", "description": "This week's schedule"},
        {"command": "nextweek", "description": "Next week's schedule"},
        {"command": "next", "description": "Your next class"},
        {"command": "addclass", "description": "Add a new class"},
        {"command": "help", "description": "How to use this bot"},
    ]
    try:
        requests.post(f"{TELEGRAM_API}/setMyCommands", json={"commands": commands}, timeout=15)
    except Exception as e:
        print(f"Could not set bot commands: {e}")


# ===================== state =====================

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_update_id": 0, "sent": {}, "commands_registered": False}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


# ===================== دستورها =====================

def build_week_text(title, monday, sessions):
    sunday = monday + timedelta(days=6)
    week_sessions = [s for s in sessions if monday <= local_dt(s).date() <= sunday]

    if not week_sessions:
        return f"🎉 No classes scheduled for {title.lower()}."

    text = f"📆 {title}\n"
    for day_offset in range(7):
        day_date = monday + timedelta(days=day_offset)
        day_sessions = [s for s in week_sessions if local_dt(s).date() == day_date]
        if not day_sessions:
            continue
        text += f"\n{DAYS_ORDER[day_offset]} ({day_date.strftime('%b %d')}):\n"
        for s in day_sessions:
            text += f"  {session_line(s)}\n"
    return text


def cmd_addclass(chat_id, raw_text):
    args = raw_text[len("/addclass"):].strip()

    usage = (
        "⚠️ Wrong format. Use:\n"
        "/addclass Day HH:MM Student | Subject | Grade\n\n"
        "Example:\n"
        "/addclass Monday 18:00 Sophia | Math | Grade 7\n\n"
        "Add 'next' before the day to schedule it for next week:\n"
        "/addclass next Monday 18:00 Sophia | Math | Grade 7\n\n"
        "Note: time must be 24-hour format (e.g. 18:00 for 6 PM)."
    )

    if not args:
        send_message(chat_id, usage)
        return

    next_week = False
    if args.lower().startswith("next "):
        next_week = True
        args = args[5:].strip()

    parts = args.split(None, 2)
    if len(parts) < 3:
        send_message(chat_id, usage)
        return

    day_raw, time_raw, rest = parts
    day = day_raw.capitalize()
    if day not in DAYS_ORDER:
        send_message(chat_id, f"⚠️ Day '{day_raw}' not recognized. Use full names: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday.")
        return

    try:
        datetime.strptime(time_raw, "%H:%M")
    except ValueError:
        send_message(chat_id, "⚠️ Time must be in 24-hour format, like 18:00 for 6 PM.")
        return

    fields = [p.strip() for p in rest.split("|")]
    student = fields[0] if len(fields) > 0 else ""
    subject = fields[1] if len(fields) > 1 else ""
    grade = fields[2] if len(fields) > 2 else ""

    if not student:
        send_message(chat_id, usage)
        return

    today = datetime.now(DISPLAY_TIMEZONE).date()
    monday = today - timedelta(days=today.weekday())
    if next_week:
        monday += timedelta(days=7)
    week_start = monday.strftime("%Y-%m-%d")

    ok, info = add_session_to_firestore(day, time_raw, student, subject, grade, week_start)
    if ok:
        send_message(chat_id, f"✅ Added: {student} — {subject} ({grade})\n{day} at {time_raw}")
    else:
        print(f"Firestore write failed: {info}")
        send_message(chat_id, "❌ Couldn't save to the website (permission issue on the database). Let your admin check Firestore security rules.")


def handle_command(cmd, chat_id, sessions, raw_text=""):
    now = datetime.now(DISPLAY_TIMEZONE)

    if cmd == "/start":
        send_message(chat_id,
            "👋 Hi! I track your tutoring schedule.\n\n"
            "Use the buttons below, or type a command:\n"
            "/today — today's classes\n"
            "/tomorrow — tomorrow's classes\n"
            "/thisweek — this week's schedule\n"
            "/nextweek — next week's schedule\n"
            "/next — your next class\n"
            "/addclass — add a new class\n"
            "/help — full usage guide\n\n"
            "I'll also remind you automatically 15 minutes before each class."
        )

    elif cmd == "/today":
        today = now.date()
        todays = [s for s in sessions if local_dt(s).date() == today]
        if not todays:
            send_message(chat_id, "🎉 No classes today!")
        else:
            lines = "\n".join(session_line(s) for s in todays)
            send_message(chat_id, f"📅 Today's Classes\n\n{lines}")

    elif cmd == "/tomorrow":
        tomorrow = (now + timedelta(days=1)).date()
        tomorrows = [s for s in sessions if local_dt(s).date() == tomorrow]
        if not tomorrows:
            send_message(chat_id, "🎉 No classes tomorrow!")
        else:
            lines = "\n".join(session_line(s) for s in tomorrows)
            send_message(chat_id, f"📅 Tomorrow's Classes\n\n{lines}")

    elif cmd == "/next":
        now_utc = datetime.now(timezone.utc)
        upcoming = [s for s in sessions if s["datetime"] >= now_utc]
        if not upcoming:
            send_message(chat_id, "🎉 No upcoming classes scheduled.")
        else:
            s = upcoming[0]
            minutes_until = int((s["datetime"] - now_utc).total_seconds() / 60)
            hours, mins = divmod(minutes_until, 60)
            countdown = f"{hours}h {mins}m" if hours else f"{mins}m"
            dt = local_dt(s)
            send_message(chat_id,
                "⏭️ Next Class\n\n"
                f"👨‍🎓 Student: {s['student']}\n"
                f"📘 Subject: {s['subject']}\n"
                f"🎓 Grade: {s['grade']}\n"
                f"🕕 Time: {format_time_12h(dt)} ({dt.strftime('%A')})\n"
                f"⏳ Starts in: {countdown}"
            )

    elif cmd in ("/thisweek", "/week"):
        today = now.date()
        monday = today - timedelta(days=today.weekday())
        send_message(chat_id, build_week_text("This Week's Schedule", monday, sessions))

    elif cmd == "/nextweek":
        today = now.date()
        this_monday = today - timedelta(days=today.weekday())
        next_monday = this_monday + timedelta(days=7)
        send_message(chat_id, build_week_text("Next Week's Schedule", next_monday, sessions))


    elif cmd == "/help":
        send_message(chat_id,
            "📖 How to Use This Bot\n\n"
            "🔘 Buttons (tap below):\n"
            "📅 Today — today's classes\n"
            "📆 Tomorrow — tomorrow's classes\n"
            "🗓️ This Week — this week's full schedule\n"
            "📆 Next Week — next week's full schedule\n"
            "⏭️ Next Class — your very next upcoming class\n\n"
            "⌨️ Commands (type manually):\n"
            "/today\n"
            "/tomorrow\n"
            "/thisweek\n"
            "/nextweek\n"
            "/next\n"
            "/addclass — add a new class to the schedule\n\n"
            "➕ Adding a class:\n"
            "/addclass Day HH:MM Student | Subject | Grade\n\n"
            "Example:\n"
            "/addclass Monday 18:00 Sophia | Math | Grade 7\n\n"
            "To schedule it for next week instead, add 'next' before the day:\n"
            "/addclass next Monday 18:00 Sophia | Math | Grade 7\n\n"
            "⚠️ Time must be 24-hour format (e.g. 18:00 = 6:00 PM).\n"
            "⚠️ Day must be spelled out fully: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday.\n\n"
            "🔔 Automatic reminders:\n"
            "You'll get a message 15 minutes before each class, and another one when it starts — no need to do anything."
        )

    elif cmd == "/addclass":
        cmd_addclass(chat_id, raw_text)


def poll_commands(state, sessions):
    resp = requests.get(
        f"{TELEGRAM_API}/getUpdates",
        params={"offset": state["last_update_id"] + 1, "timeout": 0},
        timeout=15,
    )
    resp.raise_for_status()
    updates = resp.json().get("result", [])

    for u in updates:
        state["last_update_id"] = u["update_id"]
        msg = u.get("message")
        if not msg or "text" not in msg:
            continue
        text = msg["text"].strip()
        chat_id = msg["chat"]["id"]

        # اول چک کن آیا متن یکی از دکمه‌هاست
        cmd = BUTTON_LABELS.get(text)
        if cmd is None:
            cmd = text.split()[0].lower()

        if cmd in KNOWN_COMMANDS:
            handle_command(cmd, chat_id, sessions, raw_text=text)


# ===================== یادآوری خودکار =====================

def check_reminders(state, sessions):
    now_utc = datetime.now(timezone.utc)
    today_str = datetime.now(DISPLAY_TIMEZONE).strftime("%Y-%m-%d")

    if not sessions:
        return

    sent = state["sent"]
    for s in sessions:
        minutes_until = (s["datetime"] - now_utc).total_seconds() / 60
        reminder_key = f"{s['id']}_reminder"
        started_key = f"{s['id']}_started"

        if 12 <= minutes_until <= 17 and reminder_key not in sent:
            for recipient in CHAT_IDS:
                send_message(recipient, reminder_message(s), with_keyboard=False)
            sent[reminder_key] = today_str

        if -5 <= minutes_until <= 0 and started_key not in sent:
            for recipient in CHAT_IDS:
                send_message(recipient, started_message(s), with_keyboard=False)
            sent[started_key] = today_str

    state["sent"] = {k: v for k, v in sent.items() if v == today_str}


# ===================== main =====================

def main():
    state = load_state()

    if not state.get("commands_registered"):
        set_bot_commands()
        state["commands_registered"] = True

    sessions = get_sessions()  # فقط یک‌بار در هر اجرا از Firestore میخونه

    poll_commands(state, sessions)
    check_reminders(state, sessions)
    save_state(state)


if __name__ == "__main__":
    main()
