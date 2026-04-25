from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from database import get_settings, update_settings

from plugins.subscription import check_force_sub

@Client.on_message(filters.command("settings") & filters.private)
async def settings_command(client, message):
    if not await check_force_sub(client, message):
        return
    await show_settings_panel(message.from_user.id, message)

async def edit_or_reply(message, text, markup, media_path=None):
    try:
        if media_path:
            if message.photo:
                await message.edit_media(InputMediaPhoto(media_path, caption=text), reply_markup=markup)
            else:
                await message.delete()
                await message.reply_photo(media_path, caption=text, reply_markup=markup)
        else:
            if message.photo:
                await message.edit_caption(text, reply_markup=markup)
            else:
                await message.edit_text(text, reply_markup=markup)
    except Exception:
        # Fallback if type mismatch or other issue
        try:
            await message.edit_text(text, reply_markup=markup)
        except: pass

async def show_settings_panel(user_id, message_obj, is_edit=False):
    settings = await get_settings(user_id)
    if not settings:
        settings = {"dest_channels": [], "filters": {"all": True}}
        await update_settings(user_id)

    dest_count = len(settings["dest_channels"])
    f = settings["filters"]
    
    # Improved Text
    text = (
        "⚙️ **Control Center**\n\n"
        "Here you can manage your extraction preferences and destination channels.\n\n"
        f"📡 **Active Destinations:** `{dest_count}`\n"
        "Tap the buttons below to configure."
    )
    
    # Flags for icons
    tick = "✅"
    cross = "❌"
    
    kb = [
        [
            InlineKeyboardButton(f"📂 Channel Manager ({dest_count})", callback_data="set_channels")
        ],
        [
             InlineKeyboardButton("📝 Caption Editor", callback_data="cap_panel")
        ],
        [
             InlineKeyboardButton("🖼 Thumbnail Editor", callback_data="thumb_panel")
        ],
        [
             InlineKeyboardButton("🧹 Text Cleaner", callback_data="clean_panel")
        ],
        [
             InlineKeyboardButton("--- Content Filters ---", callback_data="ignore")
        ],
        [
            InlineKeyboardButton(f"{tick if f.get('all') else cross} All Content", callback_data="tog_all"),
            InlineKeyboardButton(f"{tick if f.get('media') else cross} Media Only", callback_data="tog_media")
        ],
        [
            InlineKeyboardButton(f"{tick if f.get('photo') else cross} Photos", callback_data="tog_photo"),
            InlineKeyboardButton(f"{tick if f.get('document') else cross} Files", callback_data="tog_document")
        ],
        [
            InlineKeyboardButton(f"{tick if f.get('video') else cross} Videos", callback_data="tog_video"),
            InlineKeyboardButton(f"{tick if f.get('text') else cross} Texts", callback_data="tog_text")
        ]
    ]
    
    markup = InlineKeyboardMarkup(kb)
    
    if is_edit:
        await edit_or_reply(message_obj, text, markup, media_path="logo/setting.jpg")
    else:
        # Initial Command - Send Photo
        try:
             await message_obj.reply_photo("logo/setting.jpg", caption=text, reply_markup=markup)
        except Exception as e:
             # Fallback if image fails
             await message_obj.reply_text(text, reply_markup=markup)

@Client.on_callback_query(filters.regex("^tog_"))
async def toggle_filter(client, callback: CallbackQuery):
    key = callback.data.split("_")[1]
    user_id = callback.from_user.id
    
    settings = await get_settings(user_id)
    if not settings:
        settings = {"dest_channels": [], "filters": {"all": True}}
        
    if "filters" not in settings:
        settings["filters"] = {"all": True}
    
    current_val = settings["filters"].get(key, False)
    settings["filters"][key] = not current_val
    
    # If users selects non-all, maybe disable all? Or if user selects ALL, disable others?
    # Let's keep it simple toggle.
    if key == "all" and settings["filters"]["all"]:
        # If All turned ON, logic usually implies others are ignored or implicitly ON.
        pass
        
    await update_settings(user_id, filters=settings["filters"])
    await show_settings_panel(user_id, callback.message, is_edit=True)

@Client.on_callback_query(filters.regex("^cap_"))
async def caption_settings_handler(client, callback: CallbackQuery):
    action = callback.data
    user_id = callback.from_user.id
    
    settings = await get_settings(user_id)
    if not settings:
        settings = {"dest_channels": [], "filters": {"all": True}, "caption_rules": {}}
        await update_settings(user_id)
    
    rules = settings.get("caption_rules") or {"removals": [], "replacements": {}, "prefix": "", "suffix": ""}
    
    if action == "cap_panel":
        text = (
            "📝 **Caption Settings**\n\n"
            "Here you can modify the text of copied messages.\n"
            f"🚫 **Remove Words**: {len(rules.get('removals', []))}\n"
            f"🔄 **Replace Words**: {len(rules.get('replacements', {}))}\n"
            f"🔡 **Prefix**: {rules.get('prefix') or 'None'}\n"
            f"🔠 **Suffix**: {rules.get('suffix') or 'None'}\n"
        )
        kb = [
            [InlineKeyboardButton("🚫 Manage Removals", callback_data="cap_rem_menu")],
            [InlineKeyboardButton("🔄 Manage Replacements", callback_data="cap_rep_menu")],
            [InlineKeyboardButton("🔡 Set Prefix", callback_data="cap_prefix"), InlineKeyboardButton("🔠 Set Suffix", callback_data="cap_suffix")]
        ]
        
        del_btns = []
        if rules.get('prefix'): del_btns.append(InlineKeyboardButton("🗑 Del Prefix", callback_data="cap_del_prefix"))
        if rules.get('suffix'): del_btns.append(InlineKeyboardButton("🗑 Del Suffix", callback_data="cap_del_suffix"))
        if del_btns: kb.append(del_btns)
        
        kb.append([InlineKeyboardButton("🧹 Clear All Rules", callback_data="cap_clear")])
        kb.append([InlineKeyboardButton("🔙 Back to Main", callback_data="back_settings")])
        await edit_or_reply(callback.message, text, InlineKeyboardMarkup(kb))

    elif action == "cap_rem_menu":
        removals = rules.get("removals", [])
        text = "🚫 **Removal Rules**\nThese words/phrases will be deleted from captions.\n\n"
        if not removals: text += "No words set."
        else:
             for i, w in enumerate(removals, 1):
                 text += f"{i}. `{w}`\n"
        
        kb = [
            [InlineKeyboardButton("➕ Add Word to Remove", callback_data="cap_add_rem")],
            [InlineKeyboardButton("🗑 Delele Word", callback_data="cap_del_rem_menu")],
            [InlineKeyboardButton("🔙 Back", callback_data="cap_panel")]
        ]
        await edit_or_reply(callback.message, text, InlineKeyboardMarkup(kb))

    elif action == "cap_rep_menu":
        reps = rules.get("replacements", {})
        text = "🔄 **Replacement Rules**\nFormat: `Old` -> `New`\n\n"
        if not reps: text += "No replacements set."
        else:
             for old, new in reps.items():
                 text += f"- `{old}` ➡️ `{new}`\n"
        
        kb = [
            [InlineKeyboardButton("➕ Add Replacement", callback_data="cap_add_rep")],
            [InlineKeyboardButton("🗑 Delete Replacement", callback_data="cap_del_rep_menu")],
            [InlineKeyboardButton("🔙 Back", callback_data="cap_panel")]
        ]
        await edit_or_reply(callback.message, text, InlineKeyboardMarkup(kb))
        
    elif action == "cap_add_rem":
        client.waiting_input = {"user": user_id, "type": "rem_word"}
        await callback.message.reply_text("🗣 **Send the word/phrase to REMOVE:**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))
        
    elif action == "cap_add_rep":
        client.waiting_input = {"user": user_id, "type": "rep_word_old"}
        await callback.message.reply_text("🗣 **Send the OLD word (to be replaced):**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))

    # Prefix/Suffix Inputs
    elif action == "cap_prefix":
        client.waiting_input = {"user": user_id, "type": "set_prefix"}
        await callback.message.reply_text("🗣 **Send the Prefix Text** (appears at start):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))
    elif action == "cap_suffix":
        client.waiting_input = {"user": user_id, "type": "set_suffix"}
        await callback.message.reply_text("🗣 **Send the Suffix Text** (appears at end):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]))

        
    elif action == "cap_clear":
        rules = {"removals": [], "replacements": {}, "prefix": "", "suffix": ""}
        await update_settings(user_id, caption_rules=rules)
        await callback.answer("All rules cleared!", show_alert=True)
        # Re-show panel
        await caption_settings_handler(client, callback)
        
    # Delete Handlers with Interactive Menus
    elif action == "cap_del_rem_menu":
        removals = rules.get("removals", [])
        if not removals:
            await callback.answer("❌ No words to delete!", show_alert=True)
            return
            
        text = "🗑 **Select a Word/Phrase to Delete:**\n\n"
        kb = []
        for i, w in enumerate(removals):
            lb = w if len(w) <= 30 else w[:27] + "..."
            kb.append([InlineKeyboardButton(f"❌ {lb}", callback_data=f"cap_del_rem_idx_{i}")])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="cap_rem_menu")])
        await edit_or_reply(callback.message, text, InlineKeyboardMarkup(kb))

    elif action.startswith("cap_del_rem_idx_"):
        idx = int(action.split("_")[-1])
        removals = rules.get("removals", [])
        if 0 <= idx < len(removals):
            removed = removals.pop(idx)
            await update_settings(user_id, caption_rules=rules)
            await callback.answer(f"🗑 Deleted: {removed}")
        callback.data = "cap_del_rem_menu"
        await caption_settings_handler(client, callback)

    elif action == "cap_del_rep_menu":
        reps = rules.get("replacements", {})
        if not reps:
            await callback.answer("❌ No replacements to delete!", show_alert=True)
            return
            
        text = "🗑 **Select a Replacement Rule to Delete:**\n\n"
        kb = []
        for i, (old, new) in enumerate(reps.items()):
            label = f"{old} ➡️ {new}"
            if len(label) > 30: label = label[:27] + "..."
            kb.append([InlineKeyboardButton(f"❌ {label}", callback_data=f"cap_del_rep_idx_{i}")])
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="cap_rep_menu")])
        await edit_or_reply(callback.message, text, InlineKeyboardMarkup(kb))

    elif action.startswith("cap_del_rep_idx_"):
        idx = int(action.split("_")[-1])
        reps = rules.get("replacements", {})
        keys = list(reps.keys())
        if 0 <= idx < len(keys):
            removed_key = keys[idx]
            del reps[removed_key]
            await update_settings(user_id, caption_rules=rules)
            await callback.answer(f"🗑 Deleted Rule for: {removed_key}")
        callback.data = "cap_del_rep_menu"
        await caption_settings_handler(client, callback)
        
    elif action == "cap_del_prefix":
        rules["prefix"] = ""
        await update_settings(user_id, caption_rules=rules)
        await callback.answer("Prefix deleted.", show_alert=True)
        callback.data = "cap_panel"
        await caption_settings_handler(client, callback)
        
    elif action == "cap_del_suffix":
        rules["suffix"] = ""
        await update_settings(user_id, caption_rules=rules)
        await callback.answer("Suffix deleted.", show_alert=True)
        callback.data = "cap_panel"
        await caption_settings_handler(client, callback)


@Client.on_callback_query(filters.regex("^set_channels"))
async def channel_manager(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await get_settings(user_id)

    if not settings:
        settings = {"dest_channels": [], "filters": {"all": True}}
        await update_settings(user_id)

    channels        = settings.get("dest_channels", [])
    nicknames       = settings.get("channel_nicknames", {})
    stats           = settings.get("channel_stats", {})
    def_batch       = settings.get("default_batch_channels", [])
    def_live        = settings.get("default_live_channels", [])

    text = (
        "📡 **Channel Manager**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    if not channels:
        text += "📭 No channels added yet.\n"
    else:
        for i, ch in enumerate(channels, 1):
            nick = nicknames.get(str(ch))
            try:
                chat  = await client.get_chat(ch)
                title = nick or chat.title or "Private Channel"
            except:
                title = nick or f"Channel ({ch})"
            sent  = stats.get(str(ch), 0)
            b_def = " 📦" if ch in def_batch else ""
            l_def = " 📡" if ch in def_live else ""
            text += f"{i}. **{title}**{b_def}{l_def}\n   `{ch}` • Sent: `{sent}` files\n\n"

    text += (
        "📦 = Batch Default  •  📡 = Live Default\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = [
        [InlineKeyboardButton("➕ Add Channel", callback_data="add_channel")],
        [InlineKeyboardButton("🗑 Remove Channel", callback_data="del_channel_menu"),
         InlineKeyboardButton("🏷 Nickname", callback_data="nick_menu")],
        [InlineKeyboardButton("📦📌 Defaults for Batch", callback_data="setdef_batch"),
         InlineKeyboardButton("📡📌 Defaults for Live", callback_data="setdef_live")],
        [InlineKeyboardButton("📊 Channel Stats", callback_data="ch_stats"),
         InlineKeyboardButton("🔄 Refresh", callback_data="set_channels")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_settings")],
    ]
    await edit_or_reply(callback.message, text, InlineKeyboardMarkup(kb))


@Client.on_callback_query(filters.regex("^back_settings"))
async def back_settings(client, callback: CallbackQuery):
    # Determine if we go to main settings or somewhere else
    await show_settings_panel(callback.from_user.id, callback.message, is_edit=True)

@Client.on_callback_query(filters.regex("^(add_channel|del_channel_menu|del_channel_idx_|cancel_input|thumb_panel|thumb_set|thumb_rem)"))
async def channel_actions_handler(client, callback: CallbackQuery):
    action = callback.data
    user_id = callback.from_user.id
    
    if action == "cancel_input":
        canceled = False
        if hasattr(client, "waiting_channel_user") and client.waiting_channel_user == user_id:
            del client.waiting_channel_user
            canceled = True
        if hasattr(client, "waiting_input") and client.waiting_input.get("user") == user_id:
            del client.waiting_input
            canceled = True
            
        if canceled:
            await callback.message.edit_text("🚫 **Action Cancelled.**")
        else:
            await callback.answer("Nothing to cancel.", show_alert=True)

    elif action == "thumb_panel":
        settings = await get_settings(user_id) or {}
        thumb_id = settings.get("custom_thumbnail")
        text = (
            "🖼 **Thumbnail Editor**\n\n"
            "Upload a custom thumbnail here. This image will automatically be attached to all extracted videos and documents.\n\n"
        )
        if thumb_id:
            text += "✅ **Status:** Custom Thumbnail Active!"
        else:
            text += "❌ **Status:** No Custom Thumbnail (Default)."
            
        kb = [[InlineKeyboardButton("➕ Set Thumbnail", callback_data="thumb_set")]]
        if thumb_id:
            kb.append([InlineKeyboardButton("🗑 Remove Thumbnail", callback_data="thumb_rem")])
            
        kb.append([InlineKeyboardButton("🔙 Back to Main", callback_data="back_settings")])
        await edit_or_reply(callback.message, text, InlineKeyboardMarkup(kb), media_path=thumb_id or "logo/setting.jpg")

    elif action == "thumb_set":
        client.waiting_input = {"user": user_id, "type": "set_thumb"}
        await callback.message.reply_text(
            "🖼 **Upload Thumbnail**\n\nPlease send me an Image (Photo) to set as your custom thumbnail.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]])
        )
        await callback.answer()

    elif action == "thumb_rem":
        settings = await get_settings(user_id) or {}
        settings["custom_thumbnail"] = None
        await update_settings(user_id, custom_thumbnail=None)
        await callback.answer("🗑 Custom Thumbnail Removed!", show_alert=True)
        callback.data = "thumb_panel"
        await channel_actions_handler(client, callback)

            
    elif action == "add_channel":
        client.waiting_channel_user = user_id
        # Send a new message for input to avoid confusing the menu state
        kb = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_input")]]
        await callback.message.reply_text(
            "📝 **New Channel Setup**\n\n"
            "Please send the **Channel ID** (`-100...`), **Username** (`@...`), or **Forward a message** from it.\n"
            "⚠️ **Note:** Ensure your User Account is an Admin in that channel!",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        await callback.answer()

    elif action == "del_channel_menu":
        settings = await get_settings(user_id)
        if not settings or not settings.get("dest_channels"):
            await callback.answer("❌ No channels to delete!", show_alert=True)
            return
        
        channels = settings["dest_channels"]
        text = "🗑 **Select a Channel to Delete:**\n\n"
        kb = []
        for i, ch in enumerate(channels):
            try:
                chat = await client.get_chat(ch)
                title = chat.title or "Private Channel"
            except:
                title = f"Channel {ch}"
            kb.append([InlineKeyboardButton(f"❌ Delete {title[:20]}", callback_data=f"del_channel_idx_{i}")])
            
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="set_channels")])
        await edit_or_reply(callback.message, text, InlineKeyboardMarkup(kb))
        
    elif action.startswith("del_channel_idx_"):
        idx = int(action.split("_")[-1])
        settings = await get_settings(user_id)
        if settings and settings.get("dest_channels"):
            current = settings["dest_channels"]
            if 0 <= idx < len(current):
                removed = current.pop(idx)
                await update_settings(user_id, dest_channels=current)
                # Also clean removed channel from defaults
                def_batch = [c for c in settings.get("default_batch_channels", []) if c != removed]
                def_live  = [c for c in settings.get("default_live_channels",  []) if c != removed]
                await update_settings(user_id, default_batch_channels=def_batch, default_live_channels=def_live)
                await callback.answer(f"🗑 Removed: {removed}")
        await channel_manager(client, callback)

# ── Defaults: Remember for Batch / Live ─────────────────────
@Client.on_callback_query(filters.regex("^setdef_(batch|live)$"))
async def set_defaults_handler(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    mode    = callback.data  # setdef_batch or setdef_live

    settings = await get_settings(user_id)
    if not settings or not settings.get("dest_channels"):
        await callback.answer("No channels configured!", show_alert=True)
        return

    picker_mode   = "def_batch" if mode == "setdef_batch" else "def_live"
    existing_defs = settings.get(
        "default_batch_channels" if mode == "setdef_batch" else "default_live_channels", []
    )

    from plugins.channel_picker import open_channel_picker

    async def on_defaults_confirmed(cl, cb, uid, selected, extra):
        key = "default_batch_channels" if extra["mode"] == "def_batch" else "default_live_channels"
        await update_settings(uid, **{key: selected})
        label = "📦 Batch" if extra["mode"] == "def_batch" else "📡 Live"
        try:
            await cb.message.edit_text(
                f"✅ **{label} Defaults Saved!**\n\n"
                f"`{len(selected)}` channel(s) will be pre-selected next time."
            )
        except: pass

    await open_channel_picker(
        client, callback.message, user_id,
        mode=picker_mode,
        on_confirm=on_defaults_confirmed,
        pre_selected=existing_defs,
        extra={"mode": picker_mode},
        is_edit=True,
    )
    await callback.answer()

# ── Channel Nicknames ───────────────────────────────
_nick_states = {}  # user_id → {"ch": channel_id}

@Client.on_callback_query(filters.regex("^(nick_menu|nick_set_|nick_del_|ch_stats)$"))
async def nickname_handler(client, callback: CallbackQuery):
    pass  # placeholder — routed below

@Client.on_callback_query(filters.regex("^nick_"))
async def nick_callback(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    action  = callback.data
    settings = await get_settings(user_id) or {}
    channels  = settings.get("dest_channels", [])
    nicknames = settings.get("channel_nicknames", {})

    if action == "nick_menu":
        if not channels:
            await callback.answer("No channels!", show_alert=True)
            return
        text = "🏷 **Channel Nicknames**\n\nTap to set/change nickname:\n\n"
        buttons = []
        for i, ch in enumerate(channels):
            nick = nicknames.get(str(ch), "")
            try:
                chat  = await client.get_chat(ch)
                title = chat.title or str(ch)
            except:
                title = str(ch)
            label = f"🏷 {title[:18]} — Nick: {nick[:12] if nick else 'not set'}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"nick_set_{i}")])
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="set_channels")])
        await edit_or_reply(callback.message, text, InlineKeyboardMarkup(buttons))
        await callback.answer()

    elif action.startswith("nick_set_"):
        idx = int(action[len("nick_set_"):])
        if 0 <= idx < len(channels):
            ch = channels[idx]
            _nick_states[user_id] = {"ch": ch}
            await callback.message.reply_text(
                f"🏷 **Set Nickname**\n\nChannel: `{ch}`\n\nSend the nickname you want (or send `-` to remove):",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="nick_menu")]])
            )
        await callback.answer()

# ── Channel Stats ──────────────────────────────────
@Client.on_callback_query(filters.regex("^ch_stats$"))
async def channel_stats_view(client, callback: CallbackQuery):
    user_id  = callback.from_user.id
    settings = await get_settings(user_id) or {}
    channels  = settings.get("dest_channels", [])
    nicknames = settings.get("channel_nicknames", {})
    stats     = settings.get("channel_stats", {})

    text = "📊 **Channel Stats**\n\nHow many files were sent to each channel:\n\n"
    if not channels:
        text += "No channels configured."
    else:
        for ch in channels:
            nick = nicknames.get(str(ch))
            try:
                chat  = await client.get_chat(ch)
                title = nick or chat.title or str(ch)
            except:
                title = nick or str(ch)
            count = stats.get(str(ch), 0)
            bar   = "█" * min(count // 100, 10) + "░" * (10 - min(count // 100, 10))
            text += f"📤 **{title[:22]}**\n   `{bar}` `{count}` files\n\n"

    await edit_or_reply(
        callback.message, text,
        InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="set_channels")]])
    )
    await callback.answer()



# ══════════════════════════════════════════════════
# TEXT CLEANER PANEL
# ══════════════════════════════════════════════════

def _clean_panel_text_and_kb(tc: dict) -> tuple:
    """Build the text cleaner panel message and keyboard from settings dict."""
    on  = "🟢 ON "
    off = "🔴 OFF"

    text = (
        "🧹 **Text Cleaner Settings**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Automatically strip unwanted content from captions & text during extraction.\n\n"
        f"**@Usernames Remover:** `{'ON  ✅' if tc.get('remove_usernames') else 'OFF ❌'}`\n"
        f"  _Removes all @mention tags (e.g. @channel123)_\n\n"
        f"**t.me Link Remover:** `{'ON  ✅' if tc.get('remove_tme_links') else 'OFF ❌'}`\n"
        f"  _Removes Telegram share links (t.me/... links)_\n\n"
        f"**Hashtag Remover:** `{'ON  ✅' if tc.get('remove_hashtags') else 'OFF ❌'}`\n"
        f"  _Removes hashtags like #movie #hd #download_\n\n"
        f"**Phone Number Remover:** `{'ON  ✅' if tc.get('remove_phones') else 'OFF ❌'}`\n"
        f"  _Removes phone numbers like +91xxxxxxxx_\n\n"
        f"**All URLs Remover:** `{'ON  ✅' if tc.get('remove_all_urls') else 'OFF ❌'}`\n"
        f"  _Removes all http/https links from text_\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 _Toggle each rule independently. Applies to every extraction._"
    )

    def btn(label, key):
        state = on if tc.get(key) else off
        return InlineKeyboardButton(f"{state}| {label}", callback_data=f"tc_tog_{key}")

    kb = [
        [btn("Remove @Usernames",  "remove_usernames")],
        [btn("Remove t.me Links",  "remove_tme_links")],
        [btn("Remove #Hashtags",   "remove_hashtags")],
        [btn("Remove 📞 Phones",   "remove_phones")],
        [btn("Remove 🌐 All URLs", "remove_all_urls")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_settings")],
    ]
    return text, InlineKeyboardMarkup(kb)


@Client.on_callback_query(filters.regex("^clean_panel$"))
async def text_cleaner_panel(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    settings = await get_settings(user_id) or {}
    tc = settings.get("text_clean", {})
    text, markup = _clean_panel_text_and_kb(tc)
    await edit_or_reply(callback.message, text, markup)
    await callback.answer()


@Client.on_callback_query(filters.regex("^tc_tog_"))
async def text_cleaner_toggle(client, callback: CallbackQuery):
    user_id = callback.from_user.id
    key = callback.data[len("tc_tog_"):]

    valid_keys = {"remove_usernames", "remove_tme_links", "remove_hashtags", "remove_phones", "remove_all_urls"}
    if key not in valid_keys:
        await callback.answer("Unknown option.", show_alert=True)
        return

    settings = await get_settings(user_id) or {}
    tc = settings.get("text_clean") or {}
    tc[key] = not tc.get(key, False)
    await update_settings(user_id, text_clean=tc)

    text, markup = _clean_panel_text_and_kb(tc)
    await edit_or_reply(callback.message, text, markup)

    state_label = "ON ✅" if tc[key] else "OFF ❌"
    await callback.answer(f"{key.replace('_', ' ').title()}: {state_label}")
