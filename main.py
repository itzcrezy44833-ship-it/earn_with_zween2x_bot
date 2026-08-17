import os
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
# Token code mein nahi, Render ke Environment Variables mein set karenge
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8374129050

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
        [InlineKeyboardButton("📋 Tasks", callback_data='view_tasks')],
        [InlineKeyboardButton("💰 Wallet", callback_data='my_wallet'), InlineKeyboardButton("💳 Set UPI", callback_data='set_upi')],
        [InlineKeyboardButton("📤 Withdraw", callback_data='withdraw')]
    ]
    if user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data='admin_panel')])

    await update.message.reply_text(f"Namaste {user.first_name}! z.ween2x Network mein swagat hai.", reply_markup=InlineKeyboardMarkup(keyboard))

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
            await query.edit_message_text("Abhi koi task nahi hai.")
            return
        keyboard = [[InlineKeyboardButton(f"Task #{t[0]} - ₹{t[2]}", callback_data=f'do_task_{t[0]}')] for t in tasks]
        await query.edit_message_text("Available Tasks:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith('do_task_'):
        task_id = data.split('_')[2]
        cursor.execute('SELECT title, reward, link, instructions FROM tasks WHERE task_id = ?', (task_id,))
        task = cursor.fetchone()
        context.user_data['current_task'] = task_id
        context.user_data['task_reward'] = task[1]
        msg = f"Task: {task[0]}\nReward: ₹{task[1]}\nLink: {task[2]}\nInstructions: {task[3]}\n\nScreenshot bhejein:"
        await query.edit_message_text(text=msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Submit Proof", callback_data='submit_proof')]]))

    elif data == 'submit_proof':
        await query.edit_message_text("Photo bhejein:")
        return WAITING_FOR_PROOF

    elif data == 'my_wallet':
        cursor.execute('SELECT balance, upi_id FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        await query.edit_message_text(f"Wallet: ₹{row[0]}\nUPI: {row[1]}")

    elif data == 'set_upi':
        await query.edit_message_text("UPI ID likhkar bhejein:")
        return WAITING_FOR_UPI

    elif data == 'withdraw':
        cursor.execute('SELECT balance, upi_id FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row[0] < 50: await query.edit_message_text("Min withdrawal ₹50.")
        else: await query.edit_message_text("Request send ho gayi hai!")

    elif data == 'admin_panel':
        await query.edit_message_text("Format: `Title | Reward | Link | Instructions`")
        return WAITING_FOR_TASK_DATA
    conn.close()

async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reward = context.user_data.get('task_reward', 0)
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, 
                                 caption=f"New Proof from {update.effective_user.id}\nReward: ₹{reward}")
    await update.message.reply_text("Submit ho gaya!")
    return ConversationHandler.END

async def receive_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('microtask_system.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET upi_id = ? WHERE user_id = ?', (update.message.text, update.effective_user.id))
    conn.commit()
    conn.close()
    await update.message.reply_text("UPI Set ho gaya!")
    return ConversationHandler.END

async def receive_admin_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.message.text.split('|')
    conn = sqlite3.connect('microtask_system.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO tasks (title, reward, link, instructions) VALUES (?, ?, ?, ?)', (data[0], data[1], data[2], data[3]))
    conn.commit()
    conn.close()
    await update.message.reply_text("Task added!")
    return ConversationHandler.END

if __name__ == '__main__':
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN environment variable not set!")
    else:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        conv = ConversationHandler(entry_points=[CallbackQueryHandler(button_handler)], 
                                   states={WAITING_FOR_PROOF: [MessageHandler(filters.PHOTO, receive_proof)],
                                           WAITING_FOR_UPI: [MessageHandler(filters.TEXT, receive_upi)],
                                           WAITING_FOR_TASK_DATA: [MessageHandler(filters.TEXT, receive_admin_task)]},
                                   fallbacks=[CommandHandler("start", start)])
        app.add_handler(CommandHandler("start", start))
        app.add_handler(conv)
        app.run_polling()
