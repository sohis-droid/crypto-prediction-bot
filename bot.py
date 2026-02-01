import os
import logging
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
import requests
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# CONFIG
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS").split(",")]

# DATA STORAGE
predictions = {}
user_scores = {}
vote_history = {}

# PREDICTION QUESTIONS (100+ variations)
PREDICTION_QUESTIONS = [
    # Price Predictions
    {"q": "Will ETH price go UP or DOWN in the next hour?", "type": "eth_price"},
    {"q": "Will BTC price go UP or DOWN in the next hour?", "type": "btc_price"},
    {"q": "Will SOL price go UP or DOWN in the next hour?", "type": "sol_price"},
    {"q": "Will MATIC price go UP or DOWN in the next hour?", "type": "matic_price"},
    {"q": "Will USDC stay pegged or depeg in the next hour?", "type": "random"},
    
    # Market Questions
    {"q": "Will crypto market be BULLISH or BEARISH next hour?", "type": "random"},
    {"q": "Will there be MORE or LESS trading volume next hour?", "type": "random"},
    {"q": "Will total market cap go UP or DOWN?", "type": "random"},
    {"q": "Will ETH dominance go UP or DOWN?", "type": "random"},
    {"q": "Will BTC dominance go UP or DOWN?", "type": "random"},
    
    # Base Chain Questions
    {"q": "Will Base have MORE or LESS transactions next hour?", "type": "random"},
    {"q": "Will Base gas fees be HIGHER or LOWER next hour?", "type": "random"},
    {"q": "Will Base TVL go UP or DOWN next hour?", "type": "random"},
    {"q": "Will a new token launch on Base? YES or NO?", "type": "random"},
    
    # Fun Questions
    {"q": "Will Elon tweet about crypto this hour? YES or NO?", "type": "random"},
    {"q": "Will CoinGecko homepage be GREEN or RED?", "type": "random"},
    {"q": "Will the next BTC block be ODD or EVEN number?", "type": "random"},
    {"q": "Will someone say 'WAGMI' in our group? YES or NO?", "type": "random"},
    {"q": "Will Bitcoin fees be HIGHER or LOWER than Ethereum?", "type": "random"},
    {"q": "Will there be a new coin listing on Binance? YES or NO?", "type": "random"},
    
    # Trading Questions
    {"q": "Will more LONGS or SHORTS get liquidated?", "type": "random"},
    {"q": "Will whales buy or sell more?", "type": "random"},
    {"q": "Will funding rates be POSITIVE or NEGATIVE?", "type": "random"},
    {"q": "Will open interest go UP or DOWN?", "type": "random"},
    
    # DeFi Questions
    {"q": "Will Uniswap volume be UP or DOWN?", "type": "random"},
    {"q": "Will DeFi TVL increase or decrease?", "type": "random"},
    {"q": "Will there be a new DeFi exploit? YES or NO?", "type": "random"},
    {"q": "Will stablecoin supply go UP or DOWN?", "type": "random"},
]

def get_crypto_price(coin="ethereum"):
    """Get current crypto price"""
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd"
        response = requests.get(url, timeout=5)
        data = response.json()
        return data[coin]['usd']
    except:
        return None

def get_user_stats(user_id):
    """Get or create user stats"""
    if user_id not in user_scores:
        user_scores[user_id] = {
            'username': '',
            'points': 0,
            'wins': 0,
            'total': 0,
            'streak': 0,
            'best_streak': 0
        }
    return user_scores[user_id]

async def create_prediction(context: ContextTypes.DEFAULT_TYPE):
    """Create new hourly prediction"""
    
    # Random question
    template = random.choice(PREDICTION_QUESTIONS)
    prediction_id = datetime.now().strftime("%Y%m%d%H%M")
    
    # Get initial price if price-based
    initial_price = None
    coin_map = {
        'eth_price': 'ethereum',
        'btc_price': 'bitcoin',
        'sol_price': 'solana',
        'matic_price': 'matic-network'
    }
    
    if template['type'] in coin_map:
        initial_price = get_crypto_price(coin_map[template['type']])
    
    # Store prediction
    predictions['current'] = {
        'id': prediction_id,
        'question': template['q'],
        'type': template['type'],
        'created': datetime.now(),
        'closes': datetime.now() + timedelta(minutes=55),
        'initial_price': initial_price,
        'status': 'open',
        'votes': {'UP': [], 'DOWN': [], 'YES': [], 'NO': [], 'GREEN': [], 'RED': [], 
                  'ODD': [], 'EVEN': [], 'HIGHER': [], 'LOWER': [], 'MORE': [], 'LESS': [],
                  'BULLISH': [], 'BEARISH': [], 'LONGS': [], 'SHORTS': [], 'POSITIVE': [], 'NEGATIVE': []}
    }
    
    vote_history[prediction_id] = {}
    
    # Determine button labels from question
    buttons = []
    if 'UP or DOWN' in template['q']:
        buttons = [('📈 UP', 'UP'), ('📉 DOWN', 'DOWN')]
    elif 'YES or NO' in template['q']:
        buttons = [('✅ YES', 'YES'), ('❌ NO', 'NO')]
    elif 'GREEN or RED' in template['q']:
        buttons = [('🟢 GREEN', 'GREEN'), ('🔴 RED', 'RED')]
    elif 'ODD or EVEN' in template['q']:
        buttons = [('🔢 ODD', 'ODD'), ('🔢 EVEN', 'EVEN')]
    elif 'HIGHER or LOWER' in template['q']:
        buttons = [('⬆️ HIGHER', 'HIGHER'), ('⬇️ LOWER', 'LOWER')]
    elif 'MORE or LESS' in template['q']:
        buttons = [('➕ MORE', 'MORE'), ('➖ LESS', 'LESS')]
    elif 'BULLISH or BEARISH' in template['q']:
        buttons = [('🐂 BULLISH', 'BULLISH'), ('🐻 BEARISH', 'BEARISH')]
    elif 'LONGS or SHORTS' in template['q']:
        buttons = [('📈 LONGS', 'LONGS'), ('📉 SHORTS', 'SHORTS')]
    elif 'POSITIVE or NEGATIVE' in template['q']:
        buttons = [('➕ POSITIVE', 'POSITIVE'), ('➖ NEGATIVE', 'NEGATIVE')]
    else:
        buttons = [('📈 OPTION A', 'UP'), ('📉 OPTION B', 'DOWN')]
    
    kb = [
        [InlineKeyboardButton(btn[0], callback_data=f"vote_{btn[1]}_{prediction_id}") for btn in buttons],
        [InlineKeyboardButton("📊 My Stats", callback_data="stats")]
    ]
    
    msg = (
        f"🎯 HOURLY PREDICTION #{prediction_id[-4:]}\n\n"
        f"❓ {template['q']}\n\n"
        f"⏰ Closes: {predictions['current']['closes'].strftime('%I:%M %p')}\n"
        f"🏆 Correct guess: +10 points\n"
        f"🔥 Streak bonus: +5 points\n\n"
        f"👇 Vote now!"
    )
    
    try:
        await context.bot.send_message(
            GROUP_CHAT_ID,
            msg,
            reply_markup=InlineKeyboardMarkup(kb)
        )
        logger.info(f"Created prediction: {template['q']}")
    except Exception as e:
        logger.error(f"Error creating prediction: {e}")

async def vote_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle votes"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "stats":
        await show_stats(query)
        return
    
    parts = query.data.split('_')
    vote = parts[1]
    pred_id = parts[2]
    
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    
    current = predictions.get('current')
    
    if not current or current['id'] != pred_id:
        await query.answer("❌ This prediction ended!", show_alert=True)
        return
    
    if current['status'] != 'open':
        await query.answer("❌ Voting closed!", show_alert=True)
        return
    
    # Update stats username
    stats = get_user_stats(user_id)
    stats['username'] = username
    
    # Check if already voted
    if user_id in vote_history[pred_id]:
        old_vote = vote_history[pred_id][user_id]
        current['votes'][old_vote].remove(user_id)
        await query.answer(f"✅ Changed from {old_vote} to {vote}!")
    else:
        await query.answer(f"✅ Voted {vote}!")
    
    # Record vote
    vote_history[pred_id][user_id] = vote
    current['votes'][vote].append(user_id)
    
    logger.info(f"{username} voted {vote}")

async def show_stats(query):
    """Show user stats"""
    user_id = query.from_user.id
    stats = get_user_stats(user_id)
    
    win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
    
    msg = (
        f"📊 YOUR STATS\n\n"
        f"👤 @{stats['username']}\n"
        f"🏆 Points: {stats['points']}\n"
        f"✅ Wins: {stats['wins']}/{stats['total']}\n"
        f"📈 Win Rate: {win_rate:.1f}%\n"
        f"🔥 Streak: {stats['streak']}\n"
        f"⭐ Best: {stats['best_streak']}"
    )
    
    await query.edit_message_text(msg)

async def close_voting(context: ContextTypes.DEFAULT_TYPE):
    """Close voting"""
    current = predictions.get('current')
    if not current or current['status'] != 'open':
        return
    
    current['status'] = 'closed'
    
    # Count all votes
    total_votes = sum(len(v) for v in current['votes'].values() if v)
    
    msg = f"⏰ VOTING CLOSED!\n\n📊 Total votes: {total_votes}\n\n🎲 Result in 5 minutes..."
    
    try:
        await context.bot.send_message(GROUP_CHAT_ID, msg)
    except Exception as e:
        logger.error(f"Error: {e}")

async def resolve_prediction(context: ContextTypes.DEFAULT_TYPE):
    """Resolve and announce results"""
    current = predictions.get('current')
    if not current or current['status'] == 'resolved':
        return
    
    # Determine result
    if current['type'] in ['eth_price', 'btc_price', 'sol_price', 'matic_price']:
        coin_map = {
            'eth_price': 'ethereum',
            'btc_price': 'bitcoin',
            'sol_price': 'solana',
            'matic_price': 'matic-network'
        }
        final_price = get_crypto_price(coin_map[current['type']])
        
        if final_price and current['initial_price']:
            result = 'UP' if final_price > current['initial_price'] else 'DOWN'
        else:
            result = random.choice(['UP', 'DOWN'])
    else:
        # Random for fun questions
        possible = [k for k, v in current['votes'].items() if v]
        result = random.choice(possible) if possible else 'UP'
    
    current['status'] = 'resolved'
    current['result'] = result
    
    # Winners and losers
    winners = current['votes'].get(result, [])
    all_voters = set()
    for voters in current['votes'].values():
        all_voters.update(voters)
    losers = all_voters - set(winners)
    
    # Update scores
    for uid in winners:
        stats = get_user_stats(uid)
        points = 10
        stats['streak'] += 1
        if stats['streak'] > 1:
            points += 5
        stats['points'] += points
        stats['wins'] += 1
        stats['total'] += 1
        if stats['streak'] > stats['best_streak']:
            stats['best_streak'] = stats['streak']
    
    for uid in losers:
        stats = get_user_stats(uid)
        stats['streak'] = 0
        stats['total'] += 1
    
    # Announce
    msg = (
        f"🏆 RESULT\n\n"
        f"✅ Answer: {result}\n\n"
        f"🎉 Winners: {len(winners)} (+10 pts)\n"
        f"❌ Losers: {len(losers)}\n\n"
        f"⏱️ Next prediction in 5 minutes!"
    )
    
    try:
        await context.bot.send_message(GROUP_CHAT_ID, msg)
    except Exception as e:
        logger.error(f"Error: {e}")

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard"""
    sorted_scores = sorted(user_scores.items(), key=lambda x: x[1]['points'], reverse=True)[:10]
    
    msg = "🏆 TOP 10 LEADERBOARD\n\n"
    for i, (uid, stats) in enumerate(sorted_scores, 1):
        emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        msg += f"{emoji} @{stats['username']} - {stats['points']} pts (🔥{stats['streak']})\n"
    
    await update.message.reply_text(msg)

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show personal stats"""
    user_id = update.message.from_user.id
    stats = get_user_stats(user_id)
    stats['username'] = update.message.from_user.username or update.message.from_user.first_name
    
    win_rate = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
    
    msg = (
        f"📊 YOUR STATS\n\n"
        f"👤 @{stats['username']}\n"
        f"🏆 Points: {stats['points']}\n"
        f"✅ Wins: {stats['wins']}/{stats['total']}\n"
        f"📈 Win Rate: {win_rate:.1f}%\n"
        f"🔥 Streak: {stats['streak']}\n"
        f"⭐ Best: {stats['best_streak']}"
    )
    
    await update.message.reply_text(msg)

async def current_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current prediction"""
    current = predictions.get('current')
    if not current:
        await update.message.reply_text("❌ No active prediction!")
        return
    
    total = sum(len(v) for v in current['votes'].values() if v)
    time_left = (current['closes'] - datetime.now()).seconds // 60
    
    msg = (
        f"🎯 CURRENT PREDICTION\n\n"
        f"❓ {current['question']}\n\n"
        f"📊 Total votes: {total}\n"
        f"⏰ {time_left} min left!"
    )
    
    await update.message.reply_text(msg)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("current", current_cmd))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(vote_handler))
    
    # Scheduler
    job_queue = app.job_queue
    job_queue.run_repeating(create_prediction, interval=3600, first=10)
    job_queue.run_repeating(close_voting, interval=3600, first=3310)
    job_queue.run_repeating(resolve_prediction, interval=3600, first=3610)
    
    logger.info("🎮 Prediction Game Bot Starting!")
    logger.info("⏰ First prediction in 10 seconds")
    
    app.run_polling()

if __name__ == '__main__':
    main()