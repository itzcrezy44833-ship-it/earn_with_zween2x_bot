import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters, ConversationHandler
)

# Logging Setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- BOT CONFIGURATION ---
BOT_TOKEN = "8715542575:AAGg6jBTdnBjiWU7h0U-Ub_6tqPElh2fGVA"
ADMIN_ID = 8374129050  # Aapki Telegram User ID set ho gayi hai

WAITING_FOR_PROOF, WAITING_FOR_UPI, WAITING_FOR_TASK_DATA = range(3)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('microtask_system.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, upi_id TEXT DEFAULT '')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS tasks 
                      (task_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, reward REAL, link TEXT, instructions TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS submissions 
                      (sub_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, task_id INTEGER, status TEXT DEFAULT 'PENDING')''')
    
    # Default Demo Task
    cursor.execute('SELECT COUNT(*) FROM tasks')
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO tasks (title, reward, link, instructions) VALUES ('Demat Account Sign Up', 100.0, 'https://example.com', 'Account open karke final screenshot bhejein.')")
        conn.commit()
    conn.close()

init_db()

# --- USER HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect('microtask_system.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user.id,))
    conn.commit()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("📋 Tasks (Paise Kamayein)", callback_data='view_tasks')],
        [InlineKeyboardButton("💰 Wallet & Balance", callback_data='my_wallet'), InlineKeyboardButton("💳 Set UPI", callback_data='set_upi')],
        [InlineKeyboardButton("📤 Withdraw Payout", callback_data='withdraw')]
    ]
    if user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel (Add Task)", callback_data='admin_panel')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Namaste {user.first_name}! 👋\n\nz.ween2x Micro-Task Network mein aapka swagat hai.\nTasks complete karein aur instant UPI Payout payein!",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    conn = sqlite3.connect('microtask_system.db')
    cursor = conn.cursor()

    if data == 'view_tasks':
        cursor.execute('SELECT task_id, title, reward FROM tasks')
        tasks = cursor.fetchall()
        if not tasks:
            await query.edit_message_text("Abhi koi task available nahi hai. Thodi der baad check karein!")
            return
        
        text = "👇 **Available Tasks:**\n\n"
        keyboard = []
        for t in tasks:
            text += f"🔹 Task #{t[0]}: {t[1]} - **Reward: ₹{t[2]}**\n"
            keyboard.append([InlineKeyboardButton(f"Start Task #{t[0]} (₹{t[2]})", callback_data=f'do_task_{t[0]}')])
        
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data.startswith('do_task_'):
        task_id = data.split('_')[2]
        cursor.execute('SELECT title, reward, link, instructions FROM tasks WHERE task_id = ?', (task_id,))
        task = cursor.fetchone()
        context.user_data['current_task'] = task_id
        context.user_data['task_reward'] = task[1]

        msg = f"📌 **Task:** {task[0]}\n💵 **Reward:** ₹{task[1]}\n🔗 **Link:** {task[2]}\n\n📋 **Instructions:** {task[3]}\n\nTask poora karke screenshot bhejane ke liye niche button dabayein:"
        keyboard = [[InlineKeyboardButton("📸 Submit Screenshot Proof", callback_data='submit_proof')]]
        await query.edit_message_text(text=msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif data == 'submit_proof':
        await query.edit_message_text("📸 Kripya task ka Screenshot photo is chat mein bhejein:")
        return WAITING_FOR_PROOF

    elif data == 'my_wallet':
        cursor.execute('SELECT balance, upi_id FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        bal = row[0] if row else 0.0
        upi = row[1] if row and row[1] else "Not Set"
        await query.edit_message_text(f"💳 **Your Wallet:**\n\n💵 Current Balance: ₹{bal}\n📲 UPI ID: {upi}", parse_mode='Markdown')

    elif data == 'set_upi':
        await query.edit_message_text("📲 Apni UPI ID (e.g., 9876543210@paytm ya abc@okaxis) chat mein likhkar bhejein:")
        return WAITING_FOR_UPI

    elif data == 'withdraw':
        cursor.execute('SELECT balance, upi_id FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        bal, upi = row[0], row[1]
        if bal < 50:
            await query.edit_message_text("⚠️ Minimum Withdrawal ₹50 hai.")
        elif not upi:
            await query.edit_message_text("⚠️ Pehle 'Set UPI' par click karke apni UPI ID set karein.")
        else:
            cursor.execute('UPDATE users SET balance = 0 WHERE user_id = ?', (user_id,))
            conn.commit()
            await context.bot.send_message(
                chat_id=ADMIN_ID, 
                text=f"🚨 **NEW WITHDRAWAL REQUEST**\n\nUser ID: `{user_id}`\nAmount: ₹{bal}\nUPI ID: `{upi}`",
                parse_mode='Markdown'
            )
            await query.edit_message_text(f"✅ ₹{bal} ki withdrawal request send ho gayi hai! 24 ghante mein aapke UPI ({upi}) mein credit ho jayenge.")

    elif data == 'admin_panel':
        await query.edit_message_text("⚙️ **Admin Control Panel**\n\nNaya task add karne ke liye format mein likhein:\n`Title | Reward | Link | Instructions`\n\nAbhi chat mein likhkar bhejein:")
        return WAITING_FOR_TASK_DATA

    conn.close()

# --- PROOF & UPI INPUT HANDLERS ---
async def receive_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upi = update.message.text.strip()
    conn = sqlite3.connect('microtask_system.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET upi_id = ? WHERE user_id = ?', (upi, update.effective_user.id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ UPI ID updated: `{upi}`", parse_mode='Markdown')
    return ConversationHandler.END

async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    task_id = context.user_data.get('current_task', '1')
    reward = context.user_data.get('task_reward', 0)
    
    photo_file = update.message.photo[-1].file_id

    keyboard = [
        [InlineKeyboardButton(f"✅ Approve (Pay ₹{reward})", callback_data=f"app_{user.id}_{reward}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}")]
    ]
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_file,
        caption=f"📩 **New Task Submission**\n\nUser: {user.first_name} (`{user.id}`)\nTask ID: #{task_id}\nReward: ₹{reward}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    await update.message.reply_text("✅ AAPKA PROOF SUBMIT HO GAYA HAI! Admin review karke 2 ghante mein balance add kar dega.")
    return ConversationHandler.END

async def receive_admin_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    try:
        data = update.message.text.split('|')
        title, reward, link, instructions = data[0].strip(), float(data[1].strip()), data[2].strip(), data[3].strip()
        conn = sqlite3.connect('microtask_system.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO tasks (title, reward, link, instructions) VALUES (?, ?, ?, ?)', (title, reward, link, instructions))
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ Naya Task Successfully Live ho gaya hai!")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error Format! Is tarah se likhein:\n`Demat Account | 100 | https://link.com | Account kholein`")
    return ConversationHandler.END

# --- ADMIN APPROVAL HANDLERS ---
async def admin_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    action, target_user = data[0], int(data[1])

    if action == 'app':
        reward = float(data[2])
        conn = sqlite3.connect('microtask_system.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (reward, target_user))
        conn.commit()
        conn.close()
        await context.bot.send_message(chat_id=target_user, text=f"🎉 **CONGRATULATIONS!**\nAapka Task Approve ho gaya hai! ₹{reward} aapke wallet mein add kar diye gaye hain.")
        await query.edit_message_caption(caption=query.message.caption + "\n\n✅ **APPROVED & PAID**")
    elif action == 'rej':
        await context.bot.send_message(chat_id=target_user, text="❌ Aapka task proof reject ho gaya hai. Kripya sahi screenshot upload karein.")
        await query.edit_message_caption(caption=query.message.caption + "\n\n❌ **REJECTED**")

# --- MAIN ENGINE ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={
            WAITING_FOR_PROOF: [MessageHandler(filters.PHOTO, receive_proof)],
            WAITING_FOR_UPI: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_upi)],
            WAITING_FOR_TASK_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_task)],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_approval, pattern="^(app_|rej_)"))

    print("ZWEEN2X BOT IS NOW LIVE...")
    app.run_polling()
