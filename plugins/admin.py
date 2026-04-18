import os
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import OWNER_ID
from database import (get_all_users_count, add_ban, remove_ban, is_user_banned, 
                      check_db_connection, get_all_user_ids, add_protected_channel, 
                      remove_protected_channel, get_protected_channels)

# Ensure OWNER_ID is int
try:
    OWNER_ID = int(OWNER_ID)
except:
    OWNER_ID = 0

# --- Admin Commands ---

@Client.on_message(filters.command("stats") & filters.private)
async def stats_command(client, message):
    if message.from_user.id != OWNER_ID:
        await message.reply_text("🚧 **System Access Denied**\n\nThis command is restricted to the Administrator.")
        return

    # Check DB
    db_status = "🔴 Disconnected"
    if await check_db_connection():
        db_status = "🟢 Connected (MongoDB)"

    try:
        user_count = await get_all_users_count()
        text = (
            "📊 **System Statistics**\n\n"
            f"👤 **Total Users:** `{user_count}`\n"
            f"🗄 **Database:** `{db_status}`\n"
            "⚡ **System Status:** `Online`\n"
            "🛡 **Bot Version:** `2.0 Advanced`"
        )
        await message.reply_text(text)
    except Exception as e:
        await message.reply_text(f"❌ Error fetching stats: {e}")

@Client.on_message(filters.command("ban") & filters.private)
async def ban_command(client, message):
    if message.from_user.id != OWNER_ID:
        return
        
    if len(message.command) < 2:
        await message.reply_text("ℹ️ **Usage:** `/ban <user_id>`")
        return
        
    try:
        target_id = int(message.command[1])
        await add_ban(target_id, reason="Admin Ban")
        await message.reply_text(f"🚫 **User Banned**\nUser `{target_id}` has been blocked from using the bot.")
    except ValueError:
         await message.reply_text("❌ Invalid ID format.")
    except Exception as e:
         await message.reply_text(f"❌ Error: {e}")

@Client.on_message(filters.command("unban") & filters.private)
async def unban_command(client, message):
    if message.from_user.id != OWNER_ID:
        return
        
    if len(message.command) < 2:
        await message.reply_text("ℹ️ **Usage:** `/unban <user_id>`")
        return
        
    try:
        target_id = int(message.command[1])
        await remove_ban(target_id)
        await message.reply_text(f"✅ **User Unbanned**\nUser `{target_id}` access restored.")
    except ValueError:
         await message.reply_text("❌ Invalid ID format.")
    except Exception as e:
         await message.reply_text(f"❌ Error: {e}")

@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_command(client, message):
    if message.from_user.id != OWNER_ID:
        return
    
    msg_to_send = None
    if message.reply_to_message:
        msg_to_send = message.reply_to_message
    elif len(message.command) > 1:
        msg_to_send = message.text.split(None, 1)[1]
    else:
        await message.reply_text("ℹ️ **Usage:** Reply to a message or type text after `/broadcast`.")
        return
        
    status = await message.reply_text("📢 **Starting Broadcast...**")
    
    try:
        users = await get_all_user_ids()
        total = len(users)
        success = 0
        failed = 0
        
        await status.edit_text(f"📢 **Broadcasting to {total} users...**")
        
        for uid in users:
            try:
                if isinstance(msg_to_send, Message):
                    await msg_to_send.copy(
                        chat_id=uid,
                        reply_markup=msg_to_send.reply_markup
                    )
                else:
                    await client.send_message(uid, msg_to_send)
                success += 1
            except:
                failed += 1
            if (success + failed) % 10 == 0:
                await asyncio.sleep(0.1)
                
        await status.edit_text(
            f"✅ **Broadcast Complete**\n\n"
            f"👥 Total: `{total}`\n"
            f"✅ Success: `{success}`\n"
            f"❌ Failed: `{failed}`"
        )
    except Exception as e:
        await status.edit_text(f"❌ Broadcast Error: {e}")

@Client.on_message(filters.command("id"))
async def get_id_command(client, message):
    user_id = message.from_user.id if message.from_user else None
    
    # Check Ban First!
    if user_id and await is_user_banned(user_id):
        return # Ignore banned

    text = ""
    # 1. If Link provided: /id <link>
    if len(message.command) > 1:
        link = message.command[1]
        if "t.me/" in link:
            try:
                # Handle /c/ format
                if "/c/" in link:
                    # https://t.me/c/1234567890/10
                    p = link.split("/c/")
                    cid = p[1].split("/")[0]
                    text = f"🔢 **Extracted Channel ID:** `-100{cid}`"
                else:
                    # Public link extraction difficult without request, simple text logic?
                    # or username extraction
                    text = "ℹ️ **Link Info:**\nFor private channels (with /c/), I can extract ID.\nFor public, Extraction needs connection."
            except:
                text = "❌ Invalid Link format."
        else:
            text = f"🆔 **Argument:** `{link}`"
            
        await message.reply_text(text)
        return

    # 2. Normal /id command
    if user_id:
        text += f"🆔 **Your User ID:** `{user_id}`\n"
    
    if message.sender_chat:
        text += f"📢 **Sender Chat ID:** `{message.sender_chat.id}`\n"
        
    text += f"💬 **Current Chat ID:** `{message.chat.id}`"
    
    if message.reply_to_message:
        reply = message.reply_to_message
        text += f"\n\n↩️ **Replied Message ID:** `{reply.id}`"
        
        if reply.from_user:
             text += f"\n👤 **Replied User ID:** `{reply.from_user.id}`"
             
        if reply.forward_from:
             text += f"\n⏩ **Forwarded User ID:** `{reply.forward_from.id}`"
        
        if reply.forward_from_chat:
             text += f"\n📢 **Forwarded Channel ID:** `{reply.forward_from_chat.id}`"
             
    await message.reply_text(text)

@Client.on_message(filters.private & filters.forwarded)
async def forwarded_id_handler(client, message):
    # Auto-reply with ID for forwards
    if await is_user_banned(message.from_user.id): return

    text = "🕵️ **Forwarded Info Detected**\n\n"
    
    found = False
    if message.forward_from:
        text += f"👤 **User ID:** `{message.forward_from.id}`\n"
        found = True
    
    if message.forward_from_chat:
        text += f"📢 **Channel/Chat ID:** `{message.forward_from_chat.id}`\n"
        text += f"📝 **Title:** `{message.forward_from_chat.title}`\n"
        found = True
        
    if not found:
        text += "⚠️ Could not extract source (Hidden Forward?)"
        
    await message.reply_text(text, quote=True)

@Client.on_message(filters.command("protect_channel") & filters.private)
async def protect_channel_command(client, message):
    if message.from_user.id != OWNER_ID:
        await message.reply_text("🔮 **Magic Detected!** 🪄\n\n"
                                 "Oops! Looks like you're trying to use *my* magic spell! 🧙‍♂️✨\n\n"
                                 "**मेरा जादू मुझ पर ही चलेगा!** 😎\n"
                                 "_(My magic works for me only!)_\n\n"
                                 "This command is for the Great Wizard only. 🏰")
        return
    
    args = message.command
    
    if len(args) == 1:
        # List protected channels
        protected = await get_protected_channels()
        if not protected:
            await message.reply_text("🛡️ **Protected Channels**\n\n"
                                     "No channels are protected yet.\n\n"
                                     "**Usage:**\n"
                                     "• `/protect_channel add <channel_id>`\n"
                                     "• `/protect_channel remove <channel_id>`\n"
                                     "• `/protect_channel list`")
        else:
            text = "🛡️ **Protected Channels**\n\n"
            for idx, ch_id in enumerate(protected, 1):
                text += f"{idx}. `{ch_id}`\n"
            text += f"\n**Total:** {len(protected)} channels"
            await message.reply_text(text)
        return
    
    action = args[1].lower()
    
    if action in ["add", "remove"]:
        if len(args) < 3:
            await message.reply_text(f"❗ **Usage:** `/protect_channel {action} <channel_id>`")
            return
        
        try:
            channel_id = int(args[2])
        except ValueError:
            await message.reply_text("❌ Invalid channel ID. Must be a number.")
            return
        
        if action == "add":
            await add_protected_channel(channel_id)
            await message.reply_text(f"✅ **Channel Protected!**\n\n"
                                     f"Channel `{channel_id}` is now protected.\n"
                                     f"Users will see a magical barrier if they try to extract from it! 🔮✨")
        else:
            await remove_protected_channel(channel_id)
            await message.reply_text(f"🔓 **Protection Removed**\n\n"
                                     f"Channel `{channel_id}` is no longer protected.")
    
    elif action == "list":
        protected = await get_protected_channels()
        if not protected:
            await message.reply_text("🛡️ **Protected Channels**\n\nNo channels are protected.")
        else:
            text = "🛡️ **Protected Channels**\n\n"
            for idx, ch_id in enumerate(protected, 1):
                text += f"{idx}. `{ch_id}`\n"
            text += f"\n**Total:** {len(protected)} channels"
            await message.reply_text(text)
    else:
        await message.reply_text("❌ **Invalid action**\n\n"
                                 "Use: `add`, `remove`, or `list`")
