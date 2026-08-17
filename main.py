import os
import logging
import sqlite3
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters, ConversationHandler
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8374129050

WAITING_FOR_PROOF, WAITING_FOR_UPI, WAITING_FOR_TASK_DATA = range(3)

class HealthCheck(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is Live!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheck)
    server.serve_forever()

def init_db():
    conn = sqlite3.connect('microtask_system.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, upi_id TEXT DEFAULT '')''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (task_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, reward REAL, link TEXT, instructions TEXT)''')
    conn.commit()
    conn.close()

init_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect('microtask_system.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user.id,))
    conn.commit()
    conn.close()
    
    keyboard = [[InlineKeyboardButton("📋 Tasks", callback_data='view_tasks')],
                [InlineKeyboardButton("💰 Wallet", callback_data='my_wallet'), InlineKeyboardButton("💳 Set UPI", callback_data='set_upi')]]
    if user.id == ADMIN_ID: 
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data='admin_panel')])
    
    await update.message.reply_text(f"Namaste {user.first_name}! z.ween2x Network mein swagat hai.", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = sqlite3.connect('microtask_system.db')
    cursor = conn.cursor()
    data = query.data

    if data == 'view_tasks':
        cursor.execute('SELECT task_id, title, reward FROM tasks')
        tasks = cursor.fetchall()
        if not tasks: 
            await query.edit_message_text("Abhi koi task nahi hai.")
        else:
            keyboard = [[InlineKeyboardButton(f"{t[1]} - ₹{t[2]}", callback_data=f'do_task_{t[0]}')] for t in tasks]
            await query.edit_message_text("Available Tasks:", reply_markup=InlineKeyboardMarkup(keyboard))
        conn.close()
        return ConversationHandler.END

    elif data.startswith('do_task_'):
        task_id = data.split('_')[2]
        cursor.execute('SELECT title, reward, link, instructions FROM tasks WHERE task_id = ?', (task_id,))
        task = cursor.fetchone()
        context.user_data['current_task'] = task_id
        context.user_data['task_reward'] = task[1]
        conn.close()
        await query.edit_message_text(f"Task: {task[0]}\nReward: ₹{task[1]}\nInstructions: {task[3]}\n\nScreenshot bhejein:", 
                                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Submit Proof", callback_data='submit_proof')]]))
        return ConversationHandler.END

    elif data == 'submit_proof':
        conn.close()
        await query.edit_message_text("Task ka screenshot chat mein bhejein:")
        return WAITING_FOR_PROOF

    elif data == 'my_wallet':
        cursor.execute('SELECT balance, upi_id FROM users WHERE user_id = ?', (query.from_user.id,))
        row = cursor.fetchone()
        conn.close()
        await query.edit_message_text(f"Wallet: ₹{row[0]}\nUPI: {row[1] if row and row[1] else 'Not Set'}")
        return ConversationHandler.END

    elif data == 'set_upi':
        conn.close()
        await query.edit_message_text("Apni UPI ID likhkar bhejein:")
        return WAITING_FOR_UPI

    elif data == 'admin_panel':
        conn.close()
        await query.edit_message_text("Task Add karne ke liye is format mein bhejein:\n\n`Title | Reward | Link | Instructions`")
        return WAITING_FOR_TASK_DATA

async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reward = context.user_data.get('task_reward', 0)
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, 
                                 caption=f"Proof from {update.effective_user.id}\nReward: ₹{reward}")
    await update.message.reply_text("✅ Proof submit ho gaya!")
    return ConversationHandler.END

async def receive_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('microtask_system.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET upi_id = ? WHERE user_id = ?', (update.message.text, update.effective_user.id))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ UPI Set ho gaya!")
    return ConversationHandler.END

async def receive_admin_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = update.message.text.split('|')
        conn = sqlite3.connect('microtask_system.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO tasks (title, reward, link, instructions) VALUES (?, ?, ?, ?)', 
                       (data[0].strip(), float(data[1].strip()), data[2].strip(), data[3].strip()))
        conn.commit()
        conn.close()
        await update.message.reply_text("✅ Task add ho gaya!")
    except Exception as e:
        await update.message.reply_text("❌ Format galat hai. Format: `Title | Reward | Link | Instructions`")
    return ConversationHandler.END

if __name__ == '__main__':
    if BOT_TOKEN:
        threading.Thread(target=run_dummy_server, daemon=True).start()
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        
        conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_handler)], 
            states={
                WAITING_FOR_PROOF: [MessageHandler(filters.PHOTO, receive_proof)],
                WAITING_FOR_UPI: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_upi)],
                WAITING_FOR_TASK_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_task)]
            },
            fallbacks=[CommandHandler("start", start)],
            allow_reentry=True
        )
        app.add_handler(CommandHandler("start", start))
        app.add_handler(conv)
        app.run_polling()
