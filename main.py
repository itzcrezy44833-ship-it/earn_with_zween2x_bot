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
    
    keyboard = [
        [InlineKeyboardButton("📋 Tasks", callback_data='view_tasks')],
        [InlineKeyboardButton("💰 Wallet", callback_data='my_wallet'), InlineKeyboardButton("💳 Set UPI", callback_data='set_upi')],
        [InlineKeyboardButton("📤 Withdraw", callback_data='withdraw')]
    ]
    if user.id == ADMIN_ID: 
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data='admin_panel')])
    
    welcome_text = (
        f"Namste {user.first_name} z.ween2x pvt.ltd network main aapka swagat hain "
        f"aapka din subh ho or apna kimti waqt Dene ke liye hum aapke aabhari hain"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))
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
            keyboard = []
            for t in tasks:
                keyboard.append([InlineKeyboardButton(f"{t[1]} - ₹{t[2]}", callback_data=f'do_task_{t[0]}')])
                if query.from_user.id == ADMIN_ID:
                    keyboard.append([InlineKeyboardButton(f"❌ Delete Task #{t[0]}", callback_data=f'del_task_{t[0]}')])
            await query.edit_message_text("Available Tasks:", reply_markup=InlineKeyboardMarkup(keyboard))
        conn.close()
        return ConversationHandler.END

    elif data.startswith('del_task_'):
        task_id = data.split('_')[2]
        cursor.execute('DELETE FROM tasks WHERE task_id = ?', (task_id,))
        conn.commit()
        conn.close()
        await query.edit_message_text(f"✅ Task #{task_id} Delete ho gaya hai!")
        return ConversationHandler.END

    elif data.startswith('do_task_'):
        task_id = data.split('_')[2]
        cursor.execute('SELECT title, reward, link, instructions FROM tasks WHERE task_id = ?', (task_id,))
        task = cursor.fetchone()
        context.user_data['current_task'] = task_id
        context.user_data['task_reward'] = task[1]
        conn.close()

        # UPDATED: Link Button aur Submit Proof Button dono add kar diye hain
        task_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Open Link", url=task[2])],
            [InlineKeyboardButton("Submit Proof / Number", callback_data='submit_proof')]
        ])

        task_text = (
            f"📌 **Task:** {task[0]}\n"
            f"💵 **Reward:** ₹{task[1]}\n"
            f"📋 **Instructions:** {task[3]}\n\n"
            f"Pehle upar diye gaye link par click karke task poora karein, phir 'Submit Proof' par click karein."
        )

        await query.edit_message_text(
            text=task_text,
            reply_markup=task_buttons,
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    elif data == 'submit_proof':
        conn.close()
        await query.edit_message_text("📲 Apna WhatsApp Number ya Screenshot chat mein bhejein:")
        return WAITING_FOR_PROOF

    elif data == 'my_wallet':
        cursor.execute('SELECT balance, upi_id FROM users WHERE user_id = ?', (query.from_user.id,))
        row = cursor.fetchone()
        conn.close()
        await query.edit_message_text(f"💳 Wallet Balance: ₹{row[0]}\n📲 UPI ID: {row[1] if row and row[1] else 'Not Set'}")
        return ConversationHandler.END

    elif data == 'set_upi':
        conn.close()
        await query.edit_message_text("Apni UPI ID (e.g. 9876543210@paytm) chat mein likhkar bhejein:")
        return WAITING_FOR_UPI

    elif data == 'withdraw':
        cursor.execute('SELECT balance, upi_id FROM users WHERE user_id = ?', (query.from_user.id,))
        row = cursor.fetchone()
        conn.close()
        bal = row[0] if row else 0.0
        upi = row[1] if row and row[1] else ""
        
        if bal < 100:
            await query.edit_message_text("⚠️ Minimum Withdrawal ₹100 hai.")
        elif not upi:
            await query.edit_message_text("⚠️ Pehle 'Set UPI' par click karke apni UPI ID set karein.")
        else:
            conn = sqlite3.connect('microtask_system.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET balance = 0 WHERE user_id = ?', (query.from_user.id,))
            conn.commit()
            conn.close()
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 **NEW WITHDRAWAL REQUEST**\n\nUser ID: `{query.from_user.id}`\nAmount: ₹{bal}\nUPI ID: `{upi}`",
                parse_mode='Markdown'
            )
            await query.edit_message_text(f"✅ ₹{bal} ki withdrawal request bhej di gayi hai! Admin review karke UPI ({upi}) par paise bhej dega.")
        return ConversationHandler.END

    elif data == 'admin_panel':
        conn.close()
        await query.edit_message_text("Task Add karne ke liye is format mein text bhejein:\n\n`Title | Reward | Link | Instructions`")
        return WAITING_FOR_TASK_DATA

async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    task_id = context.user_data.get('current_task', '1')
    reward = context.user_data.get('task_reward', 0)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Approve (Pay ₹{reward})", callback_data=f"app_{user.id}_{reward}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}")]
    ])

    if update.message.photo:
        await context.bot.send_photo(
            chat_id=ADMIN_ID,
            photo=update.message.photo[-1].file_id,
            caption=f"📩 **New Task Proof (Photo)**\n\nUser: {user.first_name} (`{user.id}`)\nTask ID: #{task_id}\nReward: ₹{reward}",
            reply_markup=keyboard, parse_mode='Markdown'
        )
    else:
        proof_text = update.message.text
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 **New Task Proof (Text/Number)**\n\nUser: {user.first_name} (`{user.id}`)\nTask ID: #{task_id}\nReward: ₹{reward}\n\n**Submitted Data:**\n`{proof_text}`",
            reply_markup=keyboard, parse_mode='Markdown'
        )
        
    proof_submitted_text = (
        "✅ AAPKA PROOF SUBMIT HO GAYA HAI!\n\n"
        "Aapne jo aaj task pure kiye hain uska Paisa aapke account main 48ghante ke under add kr diya jayega "
        "jisko aap 100+ hojane pr widrawal kr sakte hain any kisi information or problem ke liye @zween2x se sampark kr sakte hain"
    )
    await update.message.reply_text(proof_submitted_text)
    return ConversationHandler.END

async def receive_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('microtask_system.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET upi_id = ? WHERE user_id = ?', (update.message.text.strip(), update.effective_user.id))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ UPI ID successfully update ho gayi hai!")
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
        await update.message.reply_text("✅ Naya Task Live ho gaya hai!")
    except Exception:
        await update.message.reply_text("❌ Format galat hai! Format: `Title | Reward | Link | Instructions`")
    return ConversationHandler.END

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
        await context.bot.send_message(chat_id=target_user, text=f"🎉 **CONGRATULATIONS!**\nAapka Task Approve ho gaya hai! ₹{reward} wallet mein add ho gaye hain.")
        if query.message.text:
            await query.edit_message_text(text=query.message.text + "\n\n✅ **APPROVED & PAID**")
        else:
            await query.edit_message_caption(caption=query.message.caption + "\n\n✅ **APPROVED & PAID**")
    elif action == 'rej':
        await context.bot.send_message(chat_id=target_user, text="❌ Aapka task proof reject ho gaya hai. Kripya sahi information bhejien.")
        if query.message.text:
            await query.edit_message_text(text=query.message.text + "\n\n❌ **REJECTED**")
        else:
            await query.edit_message_caption(caption=query.message.caption + "\n\n❌ **REJECTED**")

if __name__ == '__main__':
    if BOT_TOKEN:
        threading.Thread(target=run_dummy_server, daemon=True).start()
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        
        conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_handler)], 
            states={
                WAITING_FOR_PROOF: [MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), receive_proof)],
                WAITING_FOR_UPI: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_upi)],
                WAITING_FOR_TASK_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_task)]
            },
            fallbacks=[CommandHandler("start", start)],
            allow_reentry=True
        )
        app.add_handler(CommandHandler("start", start))
        app.add_handler(conv)
        app.add_handler(CallbackQueryHandler(admin_approval, pattern="^(app_|rej_)"))
        app.run_polling()
