import os
import json
import random
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
UPI_ID = os.getenv("UPI_ID", "yourname@upi")

DB_FILE = "users.json"
QUESTIONS_FILE = "questions.json"
FREE_LIMIT = 10  # questions per day


# ── Load questions ────────────────────────────────────────────
def load_questions():
    with open(QUESTIONS_FILE) as f:
        return json.load(f)

def get_random_question(exam=None, subject=None):
    data = load_questions()
    pool = []
    for ex, subjects in data.items():
        if exam and ex != exam:
            continue
        for sub, topics in subjects.items():
            if subject and sub != subject:
                continue
            for topic, questions in topics.items():
                for q in questions:
                    pool.append({**q, "exam": ex, "subject": sub, "topic": topic})
    return random.choice(pool) if pool else None


# ── Database ──────────────────────────────────────────────────
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f:
            return json.load(f)
    return {}

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)

def get_user(user_id):
    db = load_db()
    uid = str(user_id)
    if uid not in db:
        db[uid] = {
            "questions_today": 0,
            "date": str(datetime.today().date()),
            "premium": False,
            "premium_until": "",
            "total_correct": 0,
            "total_attempted": 0
        }
        save_db(db)
    return db[uid], db

def reset_if_new_day(user_id):
    user, db = get_user(user_id)
    today = str(datetime.today().date())
    if user["date"] != today:
        user["questions_today"] = 0
        user["date"] = today
        db[str(user_id)] = user
        save_db(db)
    return user

def is_premium(user_id):
    user, _ = get_user(user_id)
    if not user["premium"]:
        return False
    until = datetime.strptime(user["premium_until"], "%Y-%m-%d").date()
    return datetime.today().date() <= until

def can_attempt(user_id):
    if is_premium(user_id):
        return True
    user = reset_if_new_day(user_id)
    return user["questions_today"] < FREE_LIMIT

def increment_usage(user_id):
    if is_premium(user_id):
        return
    user, db = get_user(user_id)
    user["questions_today"] += 1
    db[str(user_id)] = user
    save_db(db)

def update_score(user_id, correct):
    user, db = get_user(user_id)
    user["total_attempted"] += 1
    if correct:
        user["total_correct"] += 1
    db[str(user_id)] = user
    save_db(db)

def activate_premium(user_id):
    user, db = get_user(user_id)
    until = datetime.today().date() + timedelta(days=30)
    user["premium"] = True
    user["premium_until"] = str(until)
    db[str(user_id)] = user
    save_db(db)


# ── Commands ──────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user = reset_if_new_day(user_id)
    premium = is_premium(user_id)
    remaining = max(0, FREE_LIMIT - user["questions_today"])
    status = "⭐ Premium" if premium else f"🆓 Free ({remaining}/{FREE_LIMIT} left today)"

    await update.message.reply_text(
        f"👋 Welcome to NEET/JEE Quiz Bot!\n\n"
        f"Status: {status}\n\n"
        f"📚 Commands:\n"
        f"/quiz - Random question\n"
        f"/neet - NEET question\n"
        f"/jee - JEE question\n"
        f"/physics - Physics question\n"
        f"/chemistry - Chemistry question\n"
        f"/biology - Biology (NEET)\n"
        f"/maths - Maths (JEE)\n"
        f"/score - Your score\n"
        f"/premium - Upgrade for ₹19/month\n"
    )

async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, exam=None, subject=None):
    user_id = update.message.from_user.id
    if not can_attempt(user_id):
        await update.message.reply_text(
            f"❌ You've used all {FREE_LIMIT} free questions today!\n\n"
            f"Upgrade to Premium for ₹19/month with /premium\n"
            f"or come back tomorrow!"
        )
        return

    q = get_random_question(exam, subject)
    if not q:
        await update.message.reply_text("No questions found for this category!")
        return

    # Store current question
    context.user_data["current_q"] = q

    options_text = "\n".join(q["options"])
    label = f"[{q['exam']} - {q['subject']}]"

    keyboard = [["A", "B", "C", "D"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        f"📝 {label}\n\n{q['q']}\n\n{options_text}\n\nReply with A, B, C, or D:",
        reply_markup=reply_markup
    )
    increment_usage(user_id)

async def neet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await quiz_cmd(update, context, exam="NEET")

async def jee_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await quiz_cmd(update, context, exam="JEE")

async def physics_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await quiz_cmd(update, context, subject="Physics")

async def chemistry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await quiz_cmd(update, context, subject="Chemistry")

async def biology_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await quiz_cmd(update, context, exam="NEET", subject="Biology")

async def maths_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await quiz_cmd(update, context, exam="JEE", subject="Maths")

async def score_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user, _ = get_user(user_id)
    attempted = user["total_attempted"]
    correct = user["total_correct"]
    accuracy = (correct / attempted * 100) if attempted > 0 else 0

    await update.message.reply_text(
        f"📊 *Your Score*\n\n"
        f"✅ Correct: {correct}\n"
        f"❌ Wrong: {attempted - correct}\n"
        f"📝 Total Attempted: {attempted}\n"
        f"🎯 Accuracy: {accuracy:.1f}%",
        parse_mode="Markdown"
    )

async def premium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"⭐ *Upgrade to Premium — ₹19/month*\n\n"
        f"✅ Unlimited questions per day\n"
        f"✅ All subjects — Physics, Chemistry, Biology, Maths\n"
        f"✅ Detailed explanations\n"
        f"✅ Score tracking\n\n"
        f"*How to pay:*\n"
        f"1. Pay ₹19 to UPI: `{UPI_ID}`\n"
        f"2. Take a screenshot\n"
        f"3. Send screenshot here\n"
        f"4. Get activated within 1 hour!\n\n"
        f"Your ID: `{update.message.from_user.id}`",
        parse_mode="Markdown"
    )
    context.user_data["awaiting_payment"] = True


# ── Answer handler ────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip().upper()

    # Payment screenshot
    if update.message.photo and context.user_data.get("awaiting_payment"):
        await update.message.reply_text("✅ Screenshot received! Premium will be activated within 1 hour.")
        context.user_data["awaiting_payment"] = False
        if ADMIN_ID:
            username = update.message.from_user.username or "No username"
            await context.bot.send_message(
                ADMIN_ID,
                f"💰 New payment!\nUser ID: `{user_id}`\nUsername: @{username}\n\nApprove: /approve {user_id}",
                parse_mode="Markdown"
            )
        return

    # Answer to quiz
    current_q = context.user_data.get("current_q")
    if current_q:
        if current_q["options"][0] == "A) Type your answer":
            await update.message.reply_text(
                f"📝 Your answer: {text}\n\n💡 {current_q['explanation']}\n\nSend /quiz for next question!",
                reply_markup=ReplyKeyboardRemove()
            )
            update_score(user_id, False)
            context.user_data["current_q"] = None
            return
        if text not in ["A", "B", "C", "D"]:
            await update.message.reply_text("Send /quiz to get a question!")
            return
        correct_answer = current_q["answer"]
        explanation = current_q["explanation"]
        is_correct = text == correct_answer
        update_score(user_id, is_correct)
        if is_correct:
            msg = f"✅ *Correct!*\n\n💡 {explanation}\n\nSend /quiz for next question!"
        else:
            msg = f"❌ *Wrong!* Correct answer: *{correct_answer}*\n\n💡 {explanation}\n\nSend /quiz for next question!"
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        context.user_data["current_q"] = None
    else:
        await update.message.reply_text("Send /quiz to get a question!")


# ── Admin ─────────────────────────────────────────────────────
async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve <user_id>")
        return
    uid = context.args[0]
    activate_premium(uid)
    await update.message.reply_text(f"✅ User {uid} activated!")
    try:
        await context.bot.send_message(int(uid), "🎉 Your Premium is now active for 30 days! Use /quiz to start!")
    except:
        pass

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    db = load_db()
    total = len(db)
    premium = sum(1 for u in db.values() if u.get("premium"))
    await update.message.reply_text(f"📊 Total users: {total}\n⭐ Premium: {premium}\n🆓 Free: {total - premium}")


# ── Main ──────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz_cmd))
    app.add_handler(CommandHandler("neet", neet_cmd))
    app.add_handler(CommandHandler("jee", jee_cmd))
    app.add_handler(CommandHandler("physics", physics_cmd))
    app.add_handler(CommandHandler("chemistry", chemistry_cmd))
    app.add_handler(CommandHandler("biology", biology_cmd))
    app.add_handler(CommandHandler("maths", maths_cmd))
    app.add_handler(CommandHandler("score", score_cmd))
    app.add_handler(CommandHandler("premium", premium_cmd))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    print("Quiz Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
