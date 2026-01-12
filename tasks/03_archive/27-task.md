# Task 27: Telegram Message Interactivity — Expandable Sections & Inline Buttons

## Goal

Transform Telegram market update messages from static truncated text into elegant, interactive single-message experiences using:
1. **Expandable blockquotes** for collapsible sections (sources, calendar, takeaways)
2. **Inline keyboard buttons** for toggling views and navigation
3. **Message editing** to update content dynamically on button press
4. **Spoiler text** for optional/secondary information

Target: One message that fits within the 4096-character limit while providing access to full content through native Telegram interaction patterns.

## Current Status (2026-01-10)

- **Research complete** — Telegram API capabilities documented
- Current messages are truncated at 4096 characters with `[message truncated]` suffix
- Inline keyboards only used in control plane (admin access requests), not market updates
- No expandable sections or spoiler text currently implemented

## Background

### Current Pain Points

| Issue | Impact |
|-------|--------|
| **Truncation at 4096 chars** | Users see `... [message truncated]` and miss sources/calendar |
| **Static format** | No way to show/hide sections |
| **Information overload** | All content displayed at once |
| **No interactivity** | Passive reading experience |

### Telegram Features Available (MarkdownV2)

| Feature | Syntax | Use Case |
|---------|--------|----------|
| **Expandable Blockquote** | `**>line1\n>line2\|\|` | Collapse optional sections |
| **Spoiler Text** | `\|\|hidden text\|\|` | Secondary info revealed on tap |
| **Inline Keyboard** | `reply_markup` JSON | Buttons below message |
| **Message Editing** | `editMessageText` API | Update content on button press |

### Message Character Budget Analysis

| Section | Typical Length | Priority |
|---------|----------------|----------|
| Header + Date | ~50 chars | Essential |
| Index Snapshot | ~200 chars | Essential |
| Narrative (3 paragraphs) | ~1200 chars | Essential |
| Key Takeaways (5 bullets) | ~400 chars | Collapsible |
| Key Dates (5 events) | ~350 chars | Collapsible |
| What to Watch (3 bullets) | ~200 chars | Collapsible |
| Sources (6 links) | ~600 chars | Collapsible |
| **Total** | ~3000 chars | Fits with room |

**Insight:** If we make Takeaways, Calendar, and Sources **expandable**, the default view is ~1450 chars, leaving ample room for the narrative.

## Scope

### Design Option A: Expandable Blockquotes (Native, No Callbacks)

Use Telegram's native expandable blockquote feature to collapse sections. Users tap to expand.

**Pros:**
- No server-side callback handling needed
- Native UX (users familiar with blockquotes)
- Works offline

**Cons:**
- Less control over interaction
- Can't track what users expand
- Limited styling options

### Design Option B: Inline Buttons + Message Editing (Full Control)

Use inline keyboard buttons to switch between "views" of the same message. Bot edits message on button press.

**Pros:**
- Full control over UX
- Can track engagement (which buttons pressed)
- Multiple view modes (Summary / Full / Sources Only)

**Cons:**
- Requires callback handling infrastructure
- Message editing has rate limits
- Slightly more complex implementation

### Design Option C: Hybrid (Recommended)

Combine both: Use expandable blockquotes for in-message collapsing + inline buttons for major view switches.

**Default View:**
- Header, Index Snapshot, Narrative (always visible)
- Key Takeaways in expandable blockquote (collapsed)
- Sources in expandable blockquote (collapsed)

**Inline Buttons:**
- `[📊 Full Report]` — Edit message to show everything expanded
- `[📰 Sources]` — Edit to show sources-focused view
- `[📅 Week Ahead]` — Edit to show calendar-focused view
- `[🔄 Summary]` — Return to default collapsed view

## Implementation Details

### 1. Expandable Blockquote Syntax (MarkdownV2)

**Current Renderer Output:**
```markdown
*Market Update*
*6 Jan 2026*

S&P 500 – 5,942.47 (1D +1.26%, +74.91 pts)
...

The narrative paragraph here with [1] citations...

—————

__Investor Key Takeaways__
• Takeaway 1
• Takeaway 2
...

__Sources__
[1] [Article Title](https://example.com)
...
```

**Proposed with Expandable Blockquotes:**
```markdown
*Market Update*
*6 Jan 2026*

S&P 500 – 5,942.47 (1D \+1\.26%, \+74\.91 pts)
\.\.\.

The narrative paragraph here with \[1\] citations\.\.\.

—————

**>__Investor Key Takeaways__
>• Takeaway 1
>• Takeaway 2
>• Takeaway 3||

**>__Sources__
>\[1\] [Article Title](https://example\.com)
>\[2\] [Another Article](https://example2\.com)||
```

**Key Syntax Notes:**
- `**>` starts an expandable blockquote (empty bold + blockquote marker)
- Each line in the block starts with `>`
- `||` at the end marks where collapse begins (content after first `||` is hidden)
- Blockquotes cannot be nested

### 2. Inline Keyboard Structure

**File:** `src/argus/publisher/telegram.py`

```python
def _build_market_update_keyboard() -> dict[str, Any]:
    """Build inline keyboard for market update messages."""
    return {
        "inline_keyboard": [
            [
                {"text": "📊 Full", "callback_data": "view:full"},
                {"text": "📰 Sources", "callback_data": "view:sources"},
                {"text": "📅 Calendar", "callback_data": "view:calendar"},
            ],
            [
                {"text": "🔄 Summary", "callback_data": "view:summary"},
            ]
        ]
    }
```

**Callback Data Format:** `view:{mode}` where mode is:
- `full` — All sections expanded
- `sources` — Sources section prominent
- `calendar` — Calendar section prominent
- `summary` — Default collapsed view

### 3. Message Editing on Callback

**File:** `src/argus/telegram_control/poller.py` (extend existing callback handling)

```python
async def _handle_view_callback(self, callback_query: dict) -> None:
    """Handle view mode change for market update messages."""
    query_id = callback_query["id"]
    data = callback_query["data"]  # e.g., "view:full"
    message = callback_query["message"]
    chat_id = message["chat"]["id"]
    message_id = message["message_id"]

    # Parse view mode
    _, view_mode = data.split(":", 1)

    # Get stored message data (need to persist original bundle)
    original_bundle = await self._get_message_bundle(message_id)

    # Re-render with new view mode
    new_content = render_message_for_view(original_bundle, view_mode)

    # Edit the message
    await self.bot_api.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=new_content,
        parse_mode="MarkdownV2",
        reply_markup=_build_market_update_keyboard(),
    )

    # Answer callback to dismiss loading indicator
    await self.bot_api.answer_callback_query(query_id)
```

### 4. View Mode Rendering

**File:** `src/argus/generator/renderer.py`

```python
class ViewMode(Enum):
    SUMMARY = "summary"      # Default: narrative + collapsed sections
    FULL = "full"            # All sections expanded
    SOURCES = "sources"      # Sources prominent, others collapsed
    CALENDAR = "calendar"    # Calendar prominent, others collapsed

def render_for_view(
    bundle: FactsBundle,
    news_contexts: list[NewsItemContext],
    view_mode: ViewMode = ViewMode.SUMMARY,
) -> str:
    """Render message optimized for specific view mode."""

    # Always include: Header, Index Snapshot, Narrative
    sections = [
        _render_header(bundle),
        _render_index_snapshot(bundle.market_snapshot),
        _render_narrative(bundle.narrative),
        "—————",
    ]

    # Conditional section rendering based on view mode
    if view_mode == ViewMode.FULL:
        sections.extend([
            _render_takeaways_expanded(bundle.takeaways),
            _render_calendar_expanded(bundle.calendar_events),
            _render_watch_next_expanded(bundle.watch_next),
            _render_sources_expanded(news_contexts),
        ])
    elif view_mode == ViewMode.SOURCES:
        sections.extend([
            _render_takeaways_collapsed(bundle.takeaways),
            _render_sources_expanded(news_contexts),  # Prominent
        ])
    elif view_mode == ViewMode.CALENDAR:
        sections.extend([
            _render_calendar_expanded(bundle.calendar_events),  # Prominent
            _render_takeaways_collapsed(bundle.takeaways),
            _render_sources_collapsed(news_contexts),
        ])
    else:  # SUMMARY (default)
        sections.extend([
            _render_takeaways_collapsed(bundle.takeaways),
            _render_calendar_collapsed(bundle.calendar_events),
            _render_sources_collapsed(news_contexts),
        ])

    return "\n\n".join(sections)
```

### 5. Collapsed vs Expanded Section Renderers

```python
def _render_takeaways_collapsed(takeaways: list[str]) -> str:
    """Render takeaways in expandable blockquote (collapsed by default)."""
    if not takeaways:
        return ""

    lines = ["**>__Investor Key Takeaways__"]
    for i, takeaway in enumerate(takeaways[:5]):
        bullet = f">• {_escape_markdown(takeaway)}"
        lines.append(bullet)

    # Add collapse marker after first item (rest hidden)
    # Insert || after first bullet to hide remaining
    if len(lines) > 2:
        lines[2] = lines[2] + "||"

    return "\n".join(lines)

def _render_takeaways_expanded(takeaways: list[str]) -> str:
    """Render takeaways fully visible (no blockquote)."""
    if not takeaways:
        return ""

    lines = ["__Investor Key Takeaways__"]
    for takeaway in takeaways[:5]:
        lines.append(f"• {_escape_markdown(takeaway)}")

    return "\n".join(lines)

def _render_sources_collapsed(news_contexts: list[NewsItemContext]) -> str:
    """Render sources in expandable blockquote."""
    if not news_contexts:
        return ""

    lines = ["**>__Sources__"]
    for i, ctx in enumerate(news_contexts[:6], 1):
        title = _escape_markdown(ctx.title[:50])
        url = _escape_url(ctx.url)
        lines.append(f">\\[{i}\\] [{title}]({url})")

    # Collapse after showing first 2
    if len(lines) > 3:
        lines[3] = lines[3] + "||"

    return "\n".join(lines)
```

### 6. Spoiler Text for Secondary Info

Use spoiler syntax for optional context that users can reveal:

```python
def _render_index_with_context(snapshot: MarketSnapshotBundle) -> str:
    """Render index snapshot with optional spoiler context."""
    lines = []

    # Main index data (always visible)
    sp500 = snapshot.sp500
    lines.append(f"S&P 500 – {sp500.level:,.2f} \\(1D {_format_change(sp500)}\\)")

    # Weekly context in spoiler (tap to reveal)
    if snapshot.weekly_return:
        lines.append(f"||Week: {snapshot.weekly_return:+.2f}%||")

    return "\n".join(lines)
```

### 7. Message Bundle Persistence for Editing

To edit messages on button press, we need to store the original data:

**Option A: Store in message table**
```sql
ALTER TABLE messages ADD COLUMN facts_bundle_json JSONB;
-- Already exists in runs table, can JOIN
```

**Option B: Encode in callback_data** (limited to 64 bytes)
- Not viable for full content

**Option C: Use run_id as reference**
```python
# Callback data includes run_id
{"text": "📊 Full", "callback_data": f"view:full:{run_id}"}

# Handler retrieves bundle from runs table
bundle = get_run_facts_bundle(run_id)
```

### 8. Bot API Extensions

**File:** `src/argus/telegram_control/client.py`

```python
class TelegramBotApi:
    # ... existing methods ...

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str = "MarkdownV2",
        reply_markup: Optional[dict] = None,
        disable_web_page_preview: bool = True,
    ) -> dict:
        """Edit text of a message sent by the bot."""
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        return await self._post("editMessageText", payload)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Answer a callback query from inline button press."""
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = True

        return await self._post("answerCallbackQuery", payload)
```

## New Files to Create

| File | Purpose |
|------|---------|
| `src/argus/generator/views.py` | ViewMode enum and view-specific renderers |
| `src/argus/publisher/keyboards.py` | Inline keyboard builders |
| `tests/test_expandable_blockquotes.py` | Test MarkdownV2 expandable syntax |
| `tests/test_view_rendering.py` | Test different view modes |

## Files to Modify

| File | Changes |
|------|---------|
| `src/argus/generator/renderer.py` | Add expandable blockquote rendering, view mode support |
| `src/argus/publisher/telegram.py` | Add `reply_markup` to sendMessage, implement message editing |
| `src/argus/telegram_control/client.py` | Add `editMessageText`, `answerCallbackQuery` methods |
| `src/argus/telegram_control/poller.py` | Add callback handlers for view mode changes |
| `src/argus/db/models.py` | Optionally add view state tracking |

## Acceptance Criteria

### Functional

| ID | Criterion | Verification |
|----|-----------|--------------|
| AC-1 | Expandable blockquotes render correctly | Send test message, verify tap-to-expand works |
| AC-2 | Inline buttons appear below message | Visual inspection |
| AC-3 | Button press updates message content | Press button, verify message changes |
| AC-4 | All view modes render within 4096 chars | Unit test character counts |
| AC-5 | Spoiler text hides until tapped | Visual verification |
| AC-6 | Callback queries answered (no loading spinner stuck) | UX testing |

### UX Quality

| ID | Criterion | Verification |
|----|-----------|--------------|
| UX-1 | Default view shows essential info | User testing |
| UX-2 | Expand interaction feels native | Compare to other Telegram bots |
| UX-3 | No flickering on message edit | UX testing |
| UX-4 | Button labels clear and intuitive | User feedback |

### Performance

| ID | Criterion | Verification |
|----|-----------|--------------|
| PC-1 | Message edit < 500ms | Measure API call latency |
| PC-2 | No rate limit errors on rapid button presses | Stress test |
| PC-3 | Callback handling doesn't block poller | Load testing |

### Quality Gates

- [ ] All existing tests pass
- [ ] New unit tests for expandable blockquote escaping
- [ ] New integration tests for callback handling
- [ ] Manual UX testing on mobile and desktop Telegram
- [ ] Type checking passes
- [ ] Linting passes

## Out of Scope

- Multi-message threads (keeping single message design)
- Custom web app / mini app integration
- Rich media attachments (images, charts)
- User preferences for default view mode
- Analytics on button press patterns (future enhancement)

## Risks / Notes

### Telegram API Limitations

| Limitation | Mitigation |
|------------|------------|
| `editMessageText` rate limit (~30/min per chat) | Debounce rapid button presses |
| 64-byte callback_data limit | Use run_id reference, not full content |
| Expandable blockquote support varies by client | Test on iOS, Android, Desktop, Web |
| MarkdownV2 escaping complexity | Comprehensive unit tests |

### Expandable Blockquote Caveats

- **Cannot nest blockquotes** — flat structure only
- **Collapse marker `||`** must be placed carefully
- **Older Telegram clients** may not support expandable blockquotes (graceful degradation)
- **Character counting** must account for escape sequences

### Message Editing State

- Original message content must be retrievable
- If run data is deleted, editing will fail (fallback to error message)
- Consider caching rendered views for faster editing

## Dependencies

- Task 25 (Weekly Statistics) — independent, but calendar view would benefit from weekly data
- Task 26 (CU Optimization) — independent, callback handling adds minimal DB load

## Estimated Effort

| Component | Estimate |
|-----------|----------|
| Expandable blockquote syntax research & testing | 1 hour |
| Renderer updates for collapsible sections | 2-3 hours |
| Inline keyboard implementation | 1-2 hours |
| Bot API extensions (edit, answer) | 1 hour |
| Callback handler in poller | 2 hours |
| View mode rendering logic | 2 hours |
| Unit tests | 2 hours |
| Integration/UX testing | 2 hours |

**Total: ~14-16 hours**

## User Decision Needed

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Primary interaction | Expandable blockquotes vs Inline buttons | Hybrid (both) |
| Default view | Summary vs Full | Summary (collapsed) |
| Button layout | Single row vs Multiple rows | 2 rows (3+1 buttons) |
| Include "Share" button? | Yes/No | No (keep simple initially) |

## References

- [Telegram Bot API - Inline Keyboards](https://core.telegram.org/bots/api#inlinekeyboardmarkup)
- [Telegram Bot API - editMessageText](https://core.telegram.org/bots/api#editmessagetext)
- [MarkdownV2 Formatting](https://core.telegram.org/bots/api#markdownv2-style)
- [Expandable Blockquotes Syntax](https://grammy.dev/ref/types/parsemode)
- [Callback Queries](https://core.telegram.org/bots/api#callbackquery)

## Example Final Message Structure

```
*Market Update*
*10 Jan 2026*

S&P 500 – 5,942\.47 \(1D \+1\.26%, \+74\.91 pts\)
Dow Jones – 42,635\.20 \(1D \+0\.86%, \+364\.21 pts\)
Nasdaq – 19,478\.88 \(1D \+1\.77%, \+338\.35 pts\)

Markets rallied Friday as investors digested mixed jobs data \[1\]\.
The economy added 256K jobs in December, well above the 165K expected,
but the unemployment rate ticked down to 4\.1% \[2\]\.

Tech led the advance with semiconductors gaining 3\.2% on renewed AI
optimism following CES announcements \[3\]\. Treasury yields climbed
8bps to 4\.76% as traders pushed back Fed rate cut expectations\.

—————

**>__Investor Key Takeaways__
>• Jobs report reduces urgency for near\-term Fed cuts||
>• Tech momentum intact despite higher yields
>• Watch 10Y yield resistance at 4\.80%
>• Earnings season kicks off next week

**>__Sources__
>\[1\] [Strong Jobs Report Surprises](https://reuters\.com/jobs)||
>\[2\] [Unemployment Rate Falls](https://bloomberg\.com/unemp)
>\[3\] [CES 2026 AI Highlights](https://wsj\.com/ces)

[📊 Full] [📰 Sources] [📅 Calendar]
[        🔄 Summary        ]
```
