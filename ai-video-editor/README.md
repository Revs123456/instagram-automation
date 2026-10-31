# AI Video Editor (Claude + 4 free tools)

Edit reels in your own style with Claude: drop in raw footage, get a storyboard, approve it, get the final video.

```
Raw footage ─┐
             ├─► Claude ─► storyboard ─► approve ─► reel.mp4   ($0 / mo tools)
Your style ──┘
```

## 01 · Setup (one time)

1. **Download the Claude desktop app** (Mac & Windows): <https://claude.ai/download>, and sign in.
2. **The folder:** this `ai-video-editor/` folder *is* the "AI Video Editor" folder. It has 3 folders inside:
   - `Raw Footage/`: your unedited clips
   - `Reference/`: 3–5 reels in the style you want
   - `Export/`: finished videos
   
   Want it on your Desktop like in the video? Copy it there: `cp -R ai-video-editor ~/Desktop/"AI Video Editor"`.

## 02 · Tools (free, open source)

| Tool | For |
|------|-----|
| [HyperFrames](https://github.com/heygen-com/hyperframes) | motion graphics (HTML in, video out) |
| [FFmpeg](https://ffmpeg.org) | cuts, trims, converting |
| [Whisper](https://github.com/openai/whisper) | transcripts and captions |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | downloading reels to study |

**Option A, one command:**
```bash
cd ai-video-editor && ./setup.sh                                  # macOS / Linux
powershell -ExecutionPolicy Bypass -File .\setup.ps1              # Windows
```

**Option B, let Claude do it (as in the video):** in the Claude app, choose this folder (`+` → folder, **Local**) and send:
> Install these 4 tools and set them up in my AI Video Editor folder:
> heygen-com/hyperframes, ffmpeg.org, openai/whisper, yt-dlp/yt-dlp

## 03 · Style

Download 3–5 reels from a creator whose editing you like:
```bash
./scripts/download_reels.sh https://www.instagram.com/reel/AAA/ https://www.instagram.com/reel/BBB/ https://www.instagram.com/reel/CCC/
```
Then tell Claude:
> Turn these reels into a style sheet

Claude writes `style/style-sheet.md` (fonts, colours, captions, cut speed, motion, music). Click **Approve** or ask for changes.

## 04 · Edit

Put your clip in `Raw Footage/` and tell Claude:
> Edit this video using my style

1. Claude gives you a **storyboard** (e.g. 6 scenes: Hook, Answer, Setup, Tools, Style, CTA) **before generating**.
2. **Give it changes** ("make fonts bigger", "faster cuts in the hook") or approve with "Generate video".
3. You get your **final video** in `Export/`.

How Claude should behave in this folder is defined in [`CLAUDE.md`](CLAUDE.md). Edit it to change the workflow.

## Tie-in with the comment → DM bot

End your reel with "Comment **EDIT**" and add a rule in `../config/rules.json`. The igauto bot then DMs the guide to everyone who comments:

```json
{
  "keywords": ["EDIT"],
  "link": "https://your-guide-link",
  "dm": "Hey {username}! Here's the step-by-step AI video editing guide 👉 {link}",
  "public_replies": ["Sent! Check your DMs 📩"]
}
```
