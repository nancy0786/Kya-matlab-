from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
)
from telegram.ext import (
    ApplicationBuilder, ChatJoinRequestHandler, CommandHandler,
    CallbackQueryHandler, MessageHandler, ContextTypes, filters
)
from telegram.constants import ParseMode
from fpdf import FPDF
import pandas as pd
import io
from datetime import datetime

# Your bot token here
BOT_TOKEN = "7930181984:AAFWKYt8dpaZDw1Fj6nM7sPk5Eg3eor2cUk"
BOT_OWNER_ID = 6973932532  # Replace with your Telegram user ID

# In-memory data
group_admins = {}  # group_id -> owner_id
group_welcome_messages = {}  # group_id -> welcome message
temp_group_selection = {}  # user_id -> group_id (in /setmsg)
approved_users = []  # list of dicts

# Handle join requests
async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.chat_join_request.from_user
    group = update.chat_join_request.chat
    user_id = user.id
    group_id = group.id
    group_title = group.title

    # Approve join request
    await context.bot.approve_chat_join_request(chat_id=group_id, user_id=user_id)

    # Save owner of the group
    if group_id not in group_admins:
        group_admins[group_id] = user_id

    # Export invite link (bot must be admin)
    try:
        gc_link = await context.bot.export_chat_invite_link(group_id)
    except:
        gc_link = "N/A"

    # Owner info
    owner_id = group_admins.get(group_id)
    owner_name = "Owner"
    owner_mention = "Owner"
    if owner_id:
        try:
            owner = await context.bot.get_chat_member(group_id, owner_id)
            owner_name = owner.user.full_name
            owner_mention = f"[{owner_name}](tg://user?id={owner_id})"
        except:
            pass

    # Welcome message
    raw_msg = group_welcome_messages.get(group_id, "Welcome to {gc_name}!")
    welcome_msg = (
        raw_msg.replace("{gc_name}", group_title)
               .replace("{gc_link}", gc_link)
               .replace("{gc_owner}", owner_mention)
               .replace("{owner}", owner_mention)
    )

    # Send one-time DM
    await context.bot.send_message(
        chat_id=user_id,
        text=welcome_msg,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

    # Log user for /useradded
    approved_users.append({
        "name": user.full_name,
        "username": f"@{user.username}" if user.username else "N/A",
        "user_id": user.id,
        "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "group_id": group_id,
        "group_name": group_title,
        "group_link": gc_link
    })


# /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Add Me to Your Group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("📢 Update Channel", url="https://t.me/yourchannel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome! I'm your group assistant bot.\n\n"
        "➤ I auto-approve join requests\n"
        "➤ I send a DM to users with a welcome message\n"
        "➤ You can customize the message per group\n\n"
        "Use /setmsg to begin.",
        reply_markup=reply_markup
    )


# /setmsg command (start message setting process)
async def setmsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    owned_groups = [gid for gid, uid in group_admins.items() if uid == user_id]

    if not owned_groups:
        await update.message.reply_text("You don’t own any groups yet (where join requests have been processed).")
        return

    keyboard = [
        [InlineKeyboardButton(f"{gid}", callback_data=f"setmsg_{gid}")]
        for gid in owned_groups
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select the group to set the welcome message for:", reply_markup=reply_markup)

# Group selection handler
async def group_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("setmsg_"):
        group_id = int(data.split("_")[1])
        temp_group_selection[user_id] = group_id
        await query.message.reply_text("Now send the welcome message.\n\n"
                                       "You can use these placeholders:\n"
                                       "{gc_name} - Group name\n"
                                       "{gc_owner} or {owner} - Owner mention\n"
                                       "{gc_link} - Group link",
                                       parse_mode=ParseMode.MARKDOWN)


# Save message
async def save_custom_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in temp_group_selection:
        group_id = temp_group_selection.pop(user_id)
        group_welcome_messages[group_id] = update.message.text
        await update.message.reply_text("Welcome message saved successfully!")
    else:
        await update.message.reply_text("Please use /setmsg and select a group first.")


# /useradded PDF generator
async def useradded(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    is_owner = user_id == BOT_OWNER_ID

    # Filter users
    if is_owner:
        data = approved_users
    else:
        owned_groups = [gid for gid, uid in group_admins.items() if uid == user_id]
        data = [u for u in approved_users if u["group_id"] in owned_groups]

    if not data:
        await update.message.reply_text("No approved users found.")
        return

    # Create DataFrame
    df = pd.DataFrame(data)
    df = df[["name", "username", "user_id", "joined_at", "group_name", "group_link"]]
    headers = ["Name", "Username", "User ID", "Join Time", "Group Name", "Group Link"]

    # PDF Table
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    col_widths = [40, 35, 30, 40, 45, 60]

    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 10, header, border=1)
    pdf.ln()

    for index, row in df.iterrows():
        pdf.cell(col_widths[0], 10, str(row["name"])[:20], border=1)
        pdf.cell(col_widths[1], 10, str(row["username"]), border=1)
        pdf.cell(col_widths[2], 10, str(row["user_id"]), border=1)
        pdf.cell(col_widths[3], 10, str(row["joined_at"]), border=1)
        pdf.cell(col_widths[4], 10, str(row["group_name"])[:25], border=1)
        pdf.cell(col_widths[5], 10, str(row["group_link"]), border=1)
        pdf.ln()

    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)

    await update.message.reply_document(document=output, filename="approved_users_report.pdf")

# Main
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(ChatJoinRequestHandler(handle_join_request))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("setmsg", setmsg))
app.add_handler(CallbackQueryHandler(group_selection_callback))
app.add_handler(CommandHandler("useradded", useradded))
app.add_handler(MessageHandler(filters.TEXT & filters.PRIVATE, save_custom_message))

app.run_polling()
