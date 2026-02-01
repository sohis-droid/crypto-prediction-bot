import os
import logging
import random
from datetime import datetime, timedelta

import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# --------------------------------------------------
# LOGGING
# --------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --------------------------------------------------
# ENV CONFIG
# --------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not GROUP_CHAT_ID:
    raise RuntimeError("GROUP_CHAT_ID is not set")

GROUP_CHAT_ID = int(GROUP_CHAT_ID)
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip()]

# --------------------------------------------------
# IN-MEMORY STORAGE
# --------------------------------------------------
predictions = {}
user_scores = {}
vote_history = {}

# --------------------------------------------------
# QUESTIONS
# --------------------------------------------------
PREDICTION_QUESTIONS = [
    {"q": "Will BTC price go UP or DOWN in the next hour?", "type": "btc_price"},
    {"q": "Will ETH price go UP or DOWN in the next hour?", "type": "eth_price"},
    {"q": "Will crypto market be BULLISH or BEARISH next hour?", "type": "random"},
    {"q": "Will there be MORE or LESS volume next hour?", "type": "random"},
    {"q": "Will CoinGecko homepage be GREEN or RED?", "type": "random"},
]

COIN_MAP = {
    "btc_price": "bitcoin",
    "eth_price": "ethereum",
}

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def get_price(coin: str):
    try:
        r = requests.get(
            f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd",
            timeout=5,
        )
        return r.json()[coin]["usd"]
    except Exception:
        return None


def get_user(user_id: int):
    if user_id not in user_scores:
        user_scores[user_id] = {
            "username": "",
            "points": 0,
            "wins": 0,
            "total": 0,
            "streak": 0,
            "best_streak": 0,
        }
    return user_scores[user_id]


# --------------------------------------------------
# CREATE PREDICTION (JOBQUEUE)
# --------------------------------------------------
async def create_prediction(context: ContextTypes.DEFAULT_TYPE):
    template = random.choice(PREDICTION_QUESTIONS)
    pred_id = datetime.now().strftime("%Y%m%d%H")

    initial_price = None
    if template["type"] in COIN_MAP:
        initial_price = get_price(COIN_MAP[template["type"]])

    predictions["current"] = {
        "id": pred_id,
        "question": template["q"],
        "type": template["type"],
        "created": datetime.now(),
        "closes": datetime.now() + timedelta(minutes=55),
        "initial_price": initial_price,
        "status": "open",
        "votes": {
            "UP": [],
            "DOWN": [],
            "BULLISH": [],
            "BEARISH": [],
            "MORE": [],
            "LESS": [],
            "GREEN": [],
            "RED": [],
        },
    }

    vote_history[pred_id] = {}

    if "UP or DOWN" in template["q"]:
        options = [("📈 UP", "UP"), ("📉 DOWN", "DOWN")]
    elif "BULLISH or BEARISH" in template["q"]:
        options = [("🐂 BULLISH", "BULLISH"), ("🐻 BEARISH", "BEARISH")]
    elif "MORE or LESS" in template["q"]:
        options = [("➕ MORE", "MORE"), ("➖ LESS", "LESS")]
    elif "GREEN or RED" in template["q"]:
        options = [("🟢 GREEN", "GREEN"), ("🔴 RED", "RED")]
    else:
        options = [("📈 UP", "UP"), ("📉 DOWN", "DOWN")]

    keyboard = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=f"vote_{value}_{pred_id}",
            )
            for label, value in options
        ],
        [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
    ]

    msg = (
        f"🎯 **HOURLY PREDICTION**\n\n"
        f"❓ {template['q']}\n\n"
        f"⏰ Closes at {predictions['current']['closes'].strftime('%H:%M')}\n"
        f"🏆 +10 points for correct guess\n\n"
        f"👇 Vote now!"
    )

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        text=msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    logger.info("New prediction created")


# --------------------------------------------------
# CALLBACK HANDLER (VOTES + STATS)
# --------------------------------------------------
async def vote_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "stats":
        await show_stats(query)
        return

    _, vote, pred_id = query.data.split("_")

    current = predictions.get("current")
    if not current or current["id"] != pred_id:
        await query.answer("❌ Prediction expired", show_alert=True)
        return

    if current["status"] != "open":
        await query.answer("❌ Voting closed", show_alert=True)
        return

    user = query.from_user
    stats = get_user(user.id)
    stats["username"] = user.username or user.first_name

    if user.id in vote_history[pred_id]:
        old = vote_history[pred_id][user.id]
        if user.id in current["votes"][old]:
            current["votes"][old].remove(user.id)

    vote_history[pred_id][user.id] = vote
    current["votes"][vote].append(user.id)

    # ---- LIVE COUNTS ----
    counts = {
        k: len(v) for k, v in current["votes"].items() if len(v) > 0
    }
    count_text = " | ".join(f"{k}:{v}" for k, v in counts.items())

    await query.edit_message_text(
        text=(
            f"{query.message.text}\n\n"
            f"📊 **Votes so far:**\n{count_text}"
        ),
        parse_mode="Markdown",
        reply_markup=query.message.reply_markup,
    )


# --------------------------------------------------
# STATS
# --------------------------------------------------
async def show_stats(query):
    stats = get_user(query.from_user.id)
    win_rate = (stats["wins"] / stats["total"] * 100) if stats["total"] else 0

    msg = (
        f"📊 **YOUR STATS**\n\n"
        f"🏆 Points: {stats['points']}\n"
        f"✅ Wins: {stats['wins']}/{stats['total']}\n"
        f"📈 Win rate: {win_rate:.1f}%\n"
        f"🔥 Streak: {stats['streak']}\n"
        f"⭐ Best streak: {stats['best_streak']}"
    )

    await query.edit_message_text(msg, parse_mode="Markdown")


# --------------------------------------------------
# RESOLVE PREDICTION
# --------------------------------------------------
async def resolve_prediction(context: ContextTypes.DEFAULT_TYPE):
    current = predictions.get("current")
    if not current or current["status"] != "open":
        return

    if current["type"] in COIN_MAP:
        final_price = get_price(COIN_MAP[current["type"]])
        result = (
            "UP"
            if final_price and final_price > current["initial_price"]
            else "DOWN"
        )
    else:
        result = random.choice(
            [k for k, v in current["votes"].items() if v] or ["UP"]
        )

    current["status"] = "resolved"

    winners = current["votes"].get(result, [])
    all_users = set().union(*current["votes"].values())
    losers = all_users - set(winners)

    for uid in winners:
        s = get_user(uid)
        s["points"] += 10
        s["wins"] += 1
        s["total"] += 1
        s["streak"] += 1
        s["best_streak"] = max(s["best_streak"], s["streak"])

    for uid in losers:
        s = get_user(uid)
        s["total"] += 1
        s["streak"] = 0

    await context.bot.send_message(
        GROUP_CHAT_ID,
        f"🏆 **RESULT**\n\n✅ Answer: **{result}**\n🎉 Winners: {len(winners)}",
        parse_mode="Markdown",
    )


# --------------------------------------------------
# COMMANDS
# --------------------------------------------------
async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = sorted(
        user_scores.items(),
        key=lambda x: x[1]["points"],
        reverse=True,
    )[:10]

    msg = "🏆 **LEADERBOARD**\n\n"
    for i, (_, s) in enumerate(top, 1):
        msg += f"{i}. @{s['username']} — {s['points']} pts\n"

    await update.message.reply_text(msg, parse_mode="Markdown")


# --------------------------------------------------
# MAIN
# --------------------------------------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CallbackQueryHandler(vote_handler))

    jq = app.job_queue
    jq.run_repeating(create_prediction, interval=3600, first=10)
    jq.run_repeating(resolve_prediction, interval=3600, first=3610)

    logger.info("🎮 Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
