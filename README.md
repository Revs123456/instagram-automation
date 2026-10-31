# instagram-automation

Connects **@techchamps_by.rev** to the official Instagram API to:

1. **Track growth every day.** Stores follows *and* unfollows per day, reach and views, plus per-reel views, likes, comments, saves, shares and follows, in a local SQLite database. You get history beyond Instagram's 30/90-day windows and can see which reels actually gain followers.
2. **Send auto-DMs on comment keywords.** Someone comments `ROADMAP` → they get a private DM with the link, plus an optional public "Sent! 📩" reply. It **doesn't require a follow**: the DM *invites* them to follow for the next part. This avoids the follow-for-freebie → unfollow cycle.

It uses the **Instagram API with Instagram Login** (`graph.instagram.com`). It doesn't need a Facebook Page and doesn't scrape anything.

---

## 1. One-time Meta setup (about 20 minutes)

1. **Professional account.** In the Instagram app: Settings → Account type and tools → make sure it's a *Creator* or *Business* account.
2. **Allow message access.** In the Instagram app: Settings → Messages and story replies → Message controls → Connected tools → **Allow access to messages** → On.
3. **Create a Meta app.** Go to <https://developers.facebook.com/apps> → *Create app*. Pick the use case **"Manage messaging & content on Instagram"** (app type *Business*).
4. In the app dashboard, open **Instagram → API setup with Instagram login**:
   - Under *Generate access tokens*, click **Add account** and log in as `techchamps_by.rev`. If asked, accept the *Instagram Tester* invite in Instagram → Settings → Website permissions → Apps and websites.
   - Grant these permissions: `instagram_business_basic`, `instagram_business_manage_insights`, `instagram_business_manage_comments`, `instagram_business_manage_messages`.
   - Click **Generate token** and copy it. It's a long-lived token, valid for 60 days.
   - Copy the **Instagram app secret** shown on the same page.
5. Configure:
   ```bash
   cp .env.example .env          # paste IG_ACCESS_TOKEN, IG_APP_SECRET, pick IG_WEBHOOK_VERIFY_TOKEN
   pip install -r requirements.txt
   python -m igauto whoami       # copy "user_id" into IG_USER_ID in .env
   ```

## 2. Track insights

```bash
python -m igauto sync                 # last 30 days of follows/unfollows + reels from last 60 days
python -m igauto report daily         # follows vs unfollows per day, net, reach, views
python -m igauto report reels         # reels ranked by follows (also --sort views|comments|saves)
```

Run `sync` once a day (cron, a GitHub Actions schedule, etc.). Each run adds a snapshot, so your history keeps growing:

```cron
30 2 * * *  cd /path/to/instagram-automation && python -m igauto sync
0  3 1,15 * *  cd /path/to/instagram-automation && python -m igauto refresh-token
```

> Notes: Instagram reports follows/unfollows only for the last 30 days and can lag up to 48h. Per-reel `follows` isn't available for every media type. The column shows `-` where Instagram doesn't provide it.

## 3. Comment → DM automation

1. `cp config/rules.example.json config/rules.json` and edit the keywords, links and messages.
   - `{username}` and `{link}` are filled in automatically.
   - `media_ids` (optional) limits a rule to specific reels. Find IDs with `python -m igauto report reels` or in `data/igauto.db`. Rules tied to specific reels take priority over global ones.
   - `public_replies` (optional): one is picked at random and posted under the comment.
2. Run the server on a machine with a public **HTTPS** URL (Render, Railway, Fly.io, a VPS…). For a quick test, use `ngrok http 8000`.
   ```bash
   python -m igauto serve --port 8000
   ```
3. In the Meta app: **Instagram → API setup with Instagram login → Configure webhooks**:
   - Callback URL: `https://YOUR-DOMAIN/webhook`
   - Verify token: the same value as `IG_WEBHOOK_VERIFY_TOKEN`
   - Subscribe to the **`comments`** field.
4. Switch the app to **Live** mode (this needs a privacy-policy URL). In Development mode, Meta delivers webhooks only for users who have a role on the app. Since the app only manages your own account, Standard Access is normally enough. Meta may still ask for App Review or business verification depending on your setup.

Check results with `python -m igauto report dms`.

### Instagram rules the bot follows

- **One private DM per comment, within 7 days of the comment.** Duplicates (including Meta's webhook retries) are skipped.
- After that, you can only message someone again if they reply (24h window). So the "follow for part 2" invitation goes in the first DM.
- Instagram limits automated DMs per hour. `hourly_dm_cap` (default 180) stops sending before that limit. Comments over the cap are saved as `rate_limited`, and `python -m igauto retry` sends them later.
- The bot skips your own comments and threaded replies.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Layout: `igauto/client.py` (Graph API), `insights.py` (sync), `reports.py`, `rules.py` + `autodm.py` (keyword → DM), `webhook.py` (Flask), `cli.py`.
