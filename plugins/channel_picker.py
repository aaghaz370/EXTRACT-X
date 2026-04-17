"""
channel_picker.py — Reusable channel selection UI for batch & livebatch.

Modes:
  "batch"      — choose channels for current batch job
  "live_dest"  — choose channels for live monitor destination
  "def_batch"  — remember defaults for batch
  "def_live"   — remember defaults for live

State per user:
  channel_picker_state[user_id] = {
      "mode": str,
      "selected": set,        # indices of selected channels
      "channels": [(id, title), ...],
      "nicknames": {id: nick},
      "stats": {str(id): count},
      "extra": dict,          # mode-specific data (e.g. live source)
  }
"""
import asyncio
import logging
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_settings, update_settings

logger = logging.getLogger(__name__)

# ─── In-memory state ───────────────────────────────────────────
channel_picker_state = {}   # user_id → state dict
# Callbacks registered per mode on confirm
picker_confirm_callbacks = {}   # user_id → async callable(user_id, selected_channels, extra)

MODE_LABELS = {
    "batch":     "📦 Batch Extract",
    "live_dest": "📡 Live Monitor Dest",
    "def_batch": "📌 Default Batch Channels",
    "def_live":  "📡 Default Live Channels",
}

# ─── Fetch & cache channel titles ──────────────────────────────
async def fetch_channel_title(client, ch_id, nicknames: dict) -> str:
    nick = nicknames.get(str(ch_id)) or nicknames.get(ch_id)
    if nick:
        return f"📌 {nick}"
    try:
        chat = await client.get_chat(ch_id)
        return chat.title or chat.first_name or str(ch_id)
    except Exception:
        return str(ch_id)

# ─── Build keyboard ─────────────────────────────────────────────
def build_picker_keyboard(user_id: int, page: int = 0) -> InlineKeyboardMarkup:
    state = channel_picker_state.get(user_id)
    if not state:
        return InlineKeyboardMarkup([[]])

    channels = state["channels"]
    selected = state["selected"]
    stats    = state["stats"]
    mode     = state["mode"]
    PAGE_SIZE = 6

    start = page * PAGE_SIZE
    end   = min(start + PAGE_SIZE, len(channels))
    page_channels = channels[start:end]

    buttons = []

    # Channel toggle buttons
    for idx in range(start, end):
        ch_id, title = channels[idx]
        is_sel = idx in selected
        icon   = "✅" if is_sel else "⬜"
        stat   = stats.get(str(ch_id), 0)
        stat_s = f" [{stat}]" if stat else ""
        label  = f"{icon} {title[:22]}{stat_s}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"chpick_tog_{idx}")])

    # Select All / None
    buttons.append([
        InlineKeyboardButton("✅ All", callback_data="chpick_all"),
        InlineKeyboardButton("⬜ None", callback_data="chpick_none"),
    ])

    # Pagination
    total_pages = (len(channels) - 1) // PAGE_SIZE + 1
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"chpick_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="chpick_noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"chpick_page_{page+1}"))
        buttons.append(nav)

    # Confirm / Cancel
    sel_count = len(selected)
    confirm_txt = f"✅ Confirm ({sel_count} selected)" if sel_count else "✅ Confirm"
    buttons.append([
        InlineKeyboardButton(confirm_txt, callback_data="chpick_ok"),
        InlineKeyboardButton("❌ Cancel", callback_data="chpick_cancel"),
    ])

    return InlineKeyboardMarkup(buttons)

def build_picker_text(user_id: int) -> str:
    state = channel_picker_state.get(user_id)
    if not state: return "Loading..."
    mode   = state["mode"]
    sel    = state["selected"]
    total  = len(state["channels"])
    label  = MODE_LABELS.get(mode, mode)

    return (
        f"╔══════════════════════╗\n"
        f"║  📡  CHANNEL PICKER  ║\n"
        f"╚══════════════════════╝\n\n"
        f"🎯 **Mode:** `{label}`\n"
        f"📊 **Selected:** `{len(sel)}/{total}` channels\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Tap channels to select/deselect.\n"
        f"Files will be sent to ALL selected channels.\n\n"
        f"⚠️ Bot must be **Admin** in each destination!"
    )

# ─── Open picker ────────────────────────────────────────────────
async def open_channel_picker(
    client,
    message_or_callback,
    user_id: int,
    mode: str,
    on_confirm,          # async def callback(user_id, [channel_ids], extra)
    extra: dict = None,
    pre_selected: list = None,   # list of channel IDs to pre-tick
    is_edit: bool = False,
):
    settings = await get_settings(user_id)
    if not settings or not settings.get("dest_channels"):
        txt = (
            "⛔ **No Channels Configured!**\n\n"
            "Add channels in /settings → Channel Manager first."
        )
        if is_edit:
            try: await message_or_callback.edit_text(txt)
            except: pass
        else:
            await message_or_callback.reply_text(txt)
        return

    channels_raw = settings["dest_channels"]
    nicknames    = settings.get("channel_nicknames", {})
    stats        = settings.get("channel_stats", {})

    # Fetch titles
    channels = []
    for ch_id in channels_raw:
        title = await fetch_channel_title(client, ch_id, nicknames)
        channels.append((ch_id, title))

    # Pre-select
    pre_selected_set = set()
    if pre_selected:
        for idx, (ch_id, _) in enumerate(channels):
            if ch_id in pre_selected:
                pre_selected_set.add(idx)

    channel_picker_state[user_id] = {
        "mode":     mode,
        "selected": pre_selected_set,
        "channels": channels,
        "nicknames": nicknames,
        "stats":    stats,
        "extra":    extra or {},
        "page":     0,
    }
    picker_confirm_callbacks[user_id] = on_confirm

    text = build_picker_text(user_id)
    kb   = build_picker_keyboard(user_id)

    if is_edit:
        try: await message_or_callback.edit_text(text, reply_markup=kb)
        except Exception as e:
            logger.warning(f"open_channel_picker edit error: {e}")
    else:
        await message_or_callback.reply_text(text, reply_markup=kb)

# ─── Callback handler (register in your main plugin) ────────────
from pyrogram import Client as PyroClient, filters

@PyroClient.on_callback_query(filters.regex("^chpick_"))
async def channel_picker_callback(client, callback):
    user_id = callback.from_user.id
    action  = callback.data
    state   = channel_picker_state.get(user_id)

    if not state:
        await callback.answer("Session expired. Please run the command again.", show_alert=True)
        return

    if action == "chpick_noop":
        await callback.answer()
        return

    if action == "chpick_all":
        state["selected"] = set(range(len(state["channels"])))
        await callback.answer("✅ All selected!")

    elif action == "chpick_none":
        state["selected"] = set()
        await callback.answer("⬜ None selected!")

    elif action.startswith("chpick_tog_"):
        idx = int(action[len("chpick_tog_"):])
        if idx in state["selected"]:
            state["selected"].discard(idx)
        else:
            state["selected"].add(idx)
        await callback.answer()

    elif action.startswith("chpick_page_"):
        page = int(action[len("chpick_page_"):])
        state["page"] = page
        await callback.answer()

    elif action == "chpick_cancel":
        channel_picker_state.pop(user_id, None)
        picker_confirm_callbacks.pop(user_id, None)
        await callback.answer("Cancelled.")
        try:
            await callback.message.edit_text("❌ **Selection Cancelled.**")
        except: pass
        return

    elif action == "chpick_ok":
        selected_indices = state["selected"]
        if not selected_indices:
            await callback.answer("⚠️ Select at least one channel!", show_alert=True)
            return
        selected_channels = [state["channels"][i][0] for i in sorted(selected_indices)]
        on_confirm = picker_confirm_callbacks.pop(user_id, None)
        extra      = state.get("extra", {})
        channel_picker_state.pop(user_id, None)

        try:
            await callback.message.edit_text("⏳ **Processing...**")
        except: pass

        if on_confirm:
            await on_confirm(client, callback, user_id, selected_channels, extra)
        return

    # Refresh UI
    text = build_picker_text(user_id)
    kb   = build_picker_keyboard(user_id, page=state.get("page", 0))
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except: pass
