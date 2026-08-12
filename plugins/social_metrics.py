# plugins/social_metrics.py
#
# Local Datasette plugin (Datasette stable 0.x) for tracking social engagement.
#
# Key behaviors:
# - Uses ONLY GET requests (avoids CSRF issues).
# - Uses datasette-write for all inserts (data entry / execution).
# - Provides friendly dropdown-based "New engagement" form, then redirects to
#   /{db}/-/write?sql=... with the chosen values prefilled.
# - Provides "Add platform" and "Add account" pages (GET-only) that also
#   redirect to datasette-write with INSERT SQL prefilled.
#
# UPDATE:
# - New engagement form now includes "Engagement timestamp" input.
#   Defaults to the current timestamp (UTC) at page load, but is editable.
#
# Requirements:
#   pip install datasette datasette-write
#
# Run:
#   datasette --db social_metrics=social_metrics.db --plugins-dir=plugins --root

import base64
from html import escape
from pathlib import Path
from urllib.parse import urlencode
from datetime import datetime, timezone

from datasette import hookimpl
from datasette.utils.asgi import Response


def _pick_default_db(datasette):
    # Choose the first non-internal database
    for name in datasette.databases.keys():
        if not name.startswith("_"):
            return name
    return None


def _now_utc_sqlite_timestamp():
    # SQLite CURRENT_TIMESTAMP is UTC in "YYYY-MM-DD HH:MM:SS"
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _image_data_uri(path):
    image_path = Path(path)
    if not image_path.exists():
        return ""
    suffix = image_path.suffix.lower().lstrip(".") or "png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/{suffix};base64,{encoded}"


def _html_page(title, body_html):
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1.25rem; }}
    .row {{ margin: 0.7rem 0; }}
    label {{ display: block; font-weight: 600; margin-bottom: 0.25rem; }}
    input, select, textarea {{ width: 100%; max-width: 46rem; padding: 0.45rem; }}
    textarea {{ height: 8rem; }}
    .actions {{ margin-top: 1rem; display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; }}
    .hint {{ color: #555; font-size: 0.95rem; }}
    code {{ background: #f6f6f6; padding: 0.1rem 0.25rem; border-radius: 4px; }}
    .toplinks a {{ margin-right: 1rem; }}
  </style>
</head>
<body>
  <h1>{escape(title)}</h1>
  {body_html}
</body>
</html>"""


def _quick_html_page(title, body_html):
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 0;
      padding: 0;
      color: #F5C710;
      background: black;
    }}
    main {{
      box-sizing: border-box;
      width: min(23rem, 100vw);
      margin: 0;
      padding: 8px;
    }}
    .toplinks {{
      display: flex;
      justify-content: flex-start;
      gap: 10px;
      margin: 0 0 8px;
      font-size: 12px;
      flex-wrap: wrap;
    }}
    .toplinks a {{ color: #F5C710; }}
    .box-border, .quick-panel, fieldset {{
      border: 3px solid #F5C710;
      border-radius: 10px;
      box-sizing: border-box;
    }}
    .quick-panel {{
      width: 100%;
      padding: 15px;
    }}
    .panel-header {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin: 0 0 10px;
    }}
    .panel-title {{
      margin: 0;
      color: #F5C710;
      font-size: 18px;
      font-weight: bold;
    }}
    .daily-count {{
      margin: 0;
      text-align: right;
      font-size: 24px;
      line-height: 1;
      font-weight: bold;
      color: #F5C710;
    }}
    fieldset {{
      margin: 0 0 10px;
      padding: 10px;
    }}
    legend {{
      color: #F5C710;
      font-weight: bold;
      padding: 0 5px;
      font-size: 13px;
    }}
    .picker-stage {{
      position: relative;
      min-height: 92px;
      width: 100%;
      margin: 0;
    }}
    .youtube-mark {{
      display: block;
      width: 28px;
      height: 28px;
      margin: 0 0 5px 154px;
      object-fit: contain;
    }}
    .account-picker {{
      box-sizing: border-box;
      width: 210px;
      height: 58px;
      margin: 0 0 0 74px;
      padding: 7px 10px;
      border: 2px solid #F5C710;
      border-radius: 5px;
      background: #050505;
      display: flex;
      gap: 16px;
      align-items: center;
      justify-content: center;
    }}
    .account-choice {{
      border: 0;
      background: transparent;
      padding: 0;
      cursor: pointer;
    }}
    .account-choice input {{
      position: absolute;
      opacity: 0;
      pointer-events: none;
    }}
    .linkedin-choice {{
      position: absolute;
      left: 0;
      top: 39px;
    }}
    .linkedin-icon {{
      width: 34px;
      height: 34px;
      border-radius: 5px;
      object-fit: contain;
    }}
    .account-avatar {{
      display: block;
      width: 38px;
      height: 38px;
      border-radius: 50%;
      border: 0;
      object-fit: cover;
      overflow: hidden;
    }}
    .account-choice input:checked + .account-stack .account-avatar,
    .account-choice input:checked + .account-stack .linkedin-icon {{
      outline: 3px solid #F5C710;
      outline-offset: 2px;
    }}
    .form-row {{ margin: 0 0 8px; }}
    .post-row {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 10px;
      font-size: 13px;
      font-weight: bold;
    }}
    .post-row input {{
      appearance: none;
      width: 18px;
      height: 18px;
      margin: 0;
      border: 2px solid #F5C710;
      border-radius: 3px;
      background: #222;
    }}
    .post-row input:checked::after {{
      content: "";
      display: block;
      width: 8px;
      height: 8px;
      margin: 3px;
      background: #F5C710;
    }}
    label {{
      display: block;
      margin: 0 0 4px;
      font-size: 12px;
      font-weight: 700;
      color: #F5C710;
    }}
    input[type="text"], input[type="url"], textarea {{
      box-sizing: border-box;
      display: block;
      width: 100%;
      margin-left: 0;
      border: 2px solid #F5C710;
      background: #222;
      color: #F5C710;
      padding: 5px;
      font: inherit;
      border-radius: 5px;
    }}
    input[type="text"]:focus, input[type="url"]:focus, textarea:focus {{
      outline: 1px solid #F5C710;
    }}
    textarea {{
      height: 112px;
      resize: vertical;
    }}
    .submit-row {{
      text-align: left;
      margin-top: 10px;
    }}
    button[type="submit"] {{
      margin-top: 0;
      margin-right: 10px;
      background-color: #222;
      color: #F5C710;
      border: 2px solid #F5C710;
      border-radius: 5px;
      padding: 5px 18px;
      font-size: 13px;
      font-weight: bold;
      cursor: pointer;
    }}
    button[type="submit"]:hover {{
      background: #333;
    }}
  </style>
</head>
<body>
  <main>
    {body_html}
  </main>
</body>
</html>"""


async def _fetch_platforms(db):
    res = await db.execute("select id, name from platform order by name")
    return [dict(r) for r in res.rows]


async def _fetch_accounts(db, platform_id=None):
    if platform_id is not None:
        res = await db.execute(
            "select id, handle, display_name, platform_id from account where platform_id = ? order by handle",
            [platform_id],
        )
    else:
        res = await db.execute(
            "select id, handle, display_name, platform_id from account order by handle"
        )
    return [dict(r) for r in res.rows]


PLUGIN_DIR = Path(__file__).resolve().parent
REPO_DIR = PLUGIN_DIR.parent

LINKEDIN_QUICK_ACCOUNT_ID = 4
YOUTUBE_QUICK_ACCOUNT_IDS = [1, 3, 2]
QUICK_ACCOUNT_IDS = [LINKEDIN_QUICK_ACCOUNT_ID] + YOUTUBE_QUICK_ACCOUNT_IDS
QUICK_LINKEDIN_ICON = REPO_DIR / "linkedin_ico.png"
QUICK_YOUTUBE_ICON = REPO_DIR / "youtube.png"
QUICK_ACCOUNT_ICONS = {
    1: REPO_DIR / "antigrav_kids.png",
    3: REPO_DIR / "gladych_files.png",
    2: REPO_DIR / "cootermaroos_ico.png",
}


def _initials(account):
    text = account.get("display_name") or account.get("handle") or "?"
    parts = [p for p in text.replace("@", "").replace("_", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return "".join(p[0] for p in parts[:2]).upper()


def _account_icon(account):
    return _image_data_uri(QUICK_ACCOUNT_ICONS.get(account["account_id"], ""))


async def _fetch_quick_accounts(db):
    placeholders = ",".join("?" for _ in QUICK_ACCOUNT_IDS)
    res = await db.execute(
        f"""
        select
            a.id as account_id,
            a.handle,
            a.display_name,
            p.id as platform_id,
            p.name as platform
        from account a
        join platform p on p.id = a.platform_id
        where a.id in ({placeholders})
        """,
        QUICK_ACCOUNT_IDS,
    )
    by_id = {dict(r)["account_id"]: dict(r) for r in res.rows}
    return [by_id[i] for i in QUICK_ACCOUNT_IDS if i in by_id]


async def _fetch_utc_today_count(db):
    res = await db.execute(
        """
        select
          date(engagement_time) as edate,
          count(*) as count
        from
          content
        where
          date(engagement_time) = date('now')
        group by
          edate
        order by
          edate desc
        limit
          1
        """
    )
    if not res.rows:
        return {"edate": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "count": 0}
    return dict(res.rows[0])


@hookimpl
def register_routes():
    async def social_metrics(datasette, request):
        """
        JSON summary endpoint.
        Aggregates latest engagement per platform / is_post / day
        using latest_engagement view.
        """
        db_name = request.args.get("db") or _pick_default_db(datasette)
        if not db_name:
            return Response.text("No database loaded", status=500)

        db = datasette.get_database(db_name)

        sql = """
        SELECT
            p.name AS platform,
            c.is_post,
            date(c.created_at) AS post_date,
            SUM(e.impressions) AS impressions,
            SUM(e.views) AS views,
            SUM(e.likes) AS likes,
            SUM(e.comments) AS comments,
            SUM(e.shares) AS shares
        FROM content c
        JOIN platform p ON p.id = c.platform_id
        JOIN latest_engagement e ON e.content_id = c.id
        GROUP BY platform, is_post, post_date
        ORDER BY post_date DESC, platform;
        """

        results = await db.execute(sql)
        rows = [dict(r) for r in results.rows]
        return Response.json(rows)

    async def add_platform(datasette, request):
        """
        GET-only:
        1) Show a form to input platform name
        2) Redirect to datasette-write with INSERT SQL and :name prefilled
        """
        db_name = request.args.get("db") or _pick_default_db(datasette)
        if not db_name:
            return Response.text("No database loaded", status=500)

        name = (request.args.get("name") or "").strip()
        go = request.args.get("go") == "1"

        if not go:
            body = f"""
<div class="toplinks">
  <a href="/-/social-metrics/new?db={escape(db_name)}">New engagement</a>
  <a href="/-/social-metrics/add-account?db={escape(db_name)}">Add account</a>
</div>

<p class="hint">This page uses GET only. On continue, it forwards you to <code>datasette-write</code> to run the INSERT.</p>

<form method="get">
  <input type="hidden" name="db" value="{escape(db_name)}" />
  <div class="row">
    <label>Platform name</label>
    <input name="name" value="{escape(name)}" placeholder="youtube, x, bluesky, linkedin, ..." />
  </div>
  <div class="actions">
    <button type="submit" name="go" value="1">Continue to datasette-write...</button>
    <a href="/-/social-metrics/new?db={escape(db_name)}">Cancel</a>
  </div>
</form>
"""
            return Response.html(_html_page("Add platform", body))

        if not name:
            return Response.text("Platform name required", status=400)

        insert_sql = "insert into platform(name) values (:name);"
        qs = urlencode({"sql": insert_sql, "name": name})
        return Response.redirect(f"/{db_name}/-/write?{qs}")

    async def add_account(datasette, request):
        """
        GET-only:
        1) Choose platform + enter handle/display name
        2) Redirect to datasette-write with INSERT SQL and params prefilled
        """
        db_name = request.args.get("db") or _pick_default_db(datasette)
        if not db_name:
            return Response.text("No database loaded", status=500)

        db = datasette.get_database(db_name)
        platforms = await _fetch_platforms(db)

        platform_id = (request.args.get("platform_id") or "").strip()
        handle = (request.args.get("handle") or "").strip()
        display_name = (request.args.get("display_name") or "").strip()
        go = request.args.get("go") == "1"

        if not go:
            opts = ['<option value="">-- choose a platform --</option>']
            for p in platforms:
                sel = ""
                if platform_id.isdigit() and int(platform_id) == p["id"]:
                    sel = " selected"
                opts.append(f'<option value="{p["id"]}"{sel}>{escape(p["name"])}</option>')

            body = f"""
<div class="toplinks">
  <a href="/-/social-metrics/new?db={escape(db_name)}">New engagement</a>
  <a href="/-/social-metrics/add-platform?db={escape(db_name)}">Add platform</a>
</div>

<p class="hint">This page uses GET only. On continue, it forwards you to <code>datasette-write</code> to run the INSERT.</p>

<form method="get">
  <input type="hidden" name="db" value="{escape(db_name)}" />
  <div class="row">
    <label>Platform</label>
    <select name="platform_id">
      {''.join(opts)}
    </select>
  </div>
  <div class="row">
    <label>Handle</label>
    <input name="handle" value="{escape(handle)}" placeholder="@copaseticflow" />
  </div>
  <div class="row">
    <label>Display name (optional)</label>
    <input name="display_name" value="{escape(display_name)}" placeholder="CopaseticFlow" />
  </div>
  <div class="actions">
    <button type="submit" name="go" value="1">Continue to datasette-write...</button>
    <a href="/-/social-metrics/new?db={escape(db_name)}">Cancel</a>
  </div>
</form>
"""
            return Response.html(_html_page("Add account", body))

        if not (platform_id.isdigit() and handle):
            return Response.text("Platform + handle required", status=400)

        insert_sql = """
insert into account(platform_id, handle, display_name)
values (:platform_id, :handle, :display_name);
        """.strip()

        qs = urlencode(
            {
                "sql": insert_sql,
                "platform_id": platform_id,
                "handle": handle,
                "display_name": display_name,
            }
        )
        return Response.redirect(f"/{db_name}/-/write?{qs}")

    async def new_engagement(datasette, request):
        """
        Friendly dropdown-based engagement entry form (GET-only),
        then redirects to datasette-write with prefilled INSERT + params.

        - platform_id chosen via platform name dropdown
        - account_id chosen via account dropdown (filtered by platform if selected)
        - platform_content_id is a free-text optional native ID

        NEW:
        - engagement_time can be specified. Defaults to "now" (UTC) when the form loads.
        """
        db_name = request.args.get("db") or _pick_default_db(datasette)
        if not db_name:
            return Response.text("No database loaded", status=500)
        db = datasette.get_database(db_name)

        # Inputs (GET)
        platform_id = (request.args.get("platform_id") or "").strip()
        account_id = (request.args.get("account_id") or "").strip()
        platform_content_id = (request.args.get("platform_content_id") or "").strip()
        url = (request.args.get("url") or "").strip()
        is_post = (request.args.get("is_post") or "1").strip()
        content_type = (request.args.get("content_type") or "post").strip()
        title = (request.args.get("title") or "").strip()
        body_textarea = request.args.get("body_textarea") or ""
        notes_textarea = request.args.get("notes_textarea") or ""
        link = (request.args.get("link") or "").strip()

        # NEW: engagement_time defaults to "now" unless already provided (e.g. after platform dropdown reload)
        engagement_time = (request.args.get("engagement_time") or "").strip()
        if not engagement_time:
            engagement_time = _now_utc_sqlite_timestamp()

        go = request.args.get("go") == "1"

        # Fetch dropdown data
        platforms = await _fetch_platforms(db)
        platform_id_int = int(platform_id) if platform_id.isdigit() else None
        accounts = await _fetch_accounts(db, platform_id_int)

        # If user clicked "Continue..."
        if go:
            if not platform_id.isdigit() or not account_id.isdigit():
                return Response.text("You must select both a platform and an account.", status=400)

            # Include engagement_time in the insert. (Assumes schema has engagement_time column.)
            insert_sql = """
insert into content (
  platform_id, account_id, platform_content_id, url, is_post, content_type, title, body, notes, link, engagement_time
) values (
  :platform_id, :account_id, :platform_content_id, :url, :is_post, :content_type, :title, :body_textarea, :notes_textarea, :link, :engagement_time
);
            """.strip()

            qs = urlencode(
                {
                    "sql": insert_sql,
                    "platform_id": platform_id,
                    "account_id": account_id,
                    "platform_content_id": platform_content_id,
                    "url": url,
                    "is_post": is_post,
                    "content_type": content_type,
                    "title": title,
                    "body_textarea": body_textarea,
                    "notes_textarea": notes_textarea,
                    "link": link,
                    "engagement_time": engagement_time,
                }
            )
            return Response.redirect(f"/{db_name}/-/write?{qs}")

        # Build platform dropdown (by name, value=id)
        platform_opts = ['<option value="">-- choose a platform --</option>']
        for p in platforms:
            sel = ""
            if platform_id.isdigit() and int(platform_id) == p["id"]:
                sel = " selected"
            platform_opts.append(f'<option value="{p["id"]}"{sel}>{escape(p["name"])}</option>')

        # Build account dropdown (handles/display names)
        account_opts = ['<option value="">-- choose an account --</option>']
        for a in accounts:
            label = a["handle"]
            if a.get("display_name"):
                label = f'{a["display_name"]} ({a["handle"]})'
            sel = ""
            if account_id.isdigit() and int(account_id) == a["id"]:
                sel = " selected"
            account_opts.append(f'<option value="{a["id"]}"{sel}>{escape(label)}</option>')

        # When platform changes we want to reload the page to filter accounts.
        # IMPORTANT: include engagement_time as a field so it survives the auto-submit reload.
        body = f"""
<div class="toplinks">
  <a href="/-/social-metrics/add-platform?db={escape(db_name)}">Add platform</a>
  <a href="/-/social-metrics/add-account?db={escape(db_name)}">Add account</a>
  <a href="/-/social-metrics?db={escape(db_name)}">Social metrics (JSON)</a>
</div>

<p class="hint">
This page uses GET only. Choose platform/account here (dropdowns), then click
<b>Continue to datasette-write...</b> to execute the INSERT.
</p>

<form method="get">
  <input type="hidden" name="db" value="{escape(db_name)}" />

  <div class="row">
    <label>Platform</label>
    <select name="platform_id" onchange="this.form.submit()">
      {''.join(platform_opts)}
    </select>
    <div class="hint">Changing platform reloads the account list.</div>
  </div>

  <div class="row">
    <label>Account</label>
    <select name="account_id">
      {''.join(account_opts)}
    </select>
  </div>

  <div class="row">
    <label>Engagement timestamp (UTC)</label>
    <input name="engagement_time" value="{escape(engagement_time)}"
           placeholder="YYYY-MM-DD HH:MM:SS" />
    <div class="hint">Defaults to now (UTC). You can edit it.</div>
  </div>

  <div class="row">
    <label>Platform content id (optional)</label>
    <input name="platform_content_id" value="{escape(platform_content_id)}"
           placeholder="Native ID (YouTube video id / tweet id / etc.)" />
  </div>

  <div class="row">
    <label>URL (optional)</label>
    <input name="url" value="{escape(url)}" placeholder="https://..." />
  </div>

  <div class="row">
    <label>Is this a post?</label>
    <select name="is_post">
      <option value="1"{" selected" if is_post == "1" else ""}>1 (post)</option>
      <option value="0"{" selected" if is_post == "0" else ""}>0 (not a post)</option>
    </select>
  </div>

  <div class="row">
    <label>Content type</label>
    <input name="content_type" value="{escape(content_type)}" placeholder="post, reply, comment, short, ..." />
  </div>

  <div class="row">
    <label>Title (optional)</label>
    <input name="title" value="{escape(title)}" />
  </div>

  <div class="row">
    <label>Body (optional)</label>
    <textarea name="body_textarea">{escape(body_textarea)}</textarea>
  </div>

  <div class="row">
    <label>Notes (optional)</label>
    <textarea name="notes_textarea">{escape(notes_textarea)}</textarea>
  </div>

  <div class="row">
    <label>Related link (optional)</label>
    <input name="link" value="{escape(link)}" placeholder="https://..." />
  </div>

  <div class="actions">
    <button type="submit" name="go" value="1">Continue to datasette-write...</button>
    <a href="/-/social-metrics/new?db={escape(db_name)}">Reset</a>
  </div>
</form>
"""
        return Response.html(_html_page("New engagement", body))

    async def quick_engagement(datasette, request):
        """
        Fast visual entry page for common accounts.
        Keeps the GET-only datasette-write handoff used by the full form.
        """
        db_name = request.args.get("db") or _pick_default_db(datasette)
        if not db_name:
            return Response.text("No database loaded", status=500)
        db = datasette.get_database(db_name)

        quick_accounts = await _fetch_quick_accounts(db)
        today_count = await _fetch_utc_today_count(db)

        selected = (request.args.get("account") or "").strip()

        link = (request.args.get("link") or "").strip()
        title = (request.args.get("title") or "").strip()
        notes_textarea = request.args.get("notes_textarea") or ""
        is_post = "1" if request.args.get("is_post") == "1" else "0"
        engagement_time = (request.args.get("engagement_time") or "").strip()
        if not engagement_time:
            engagement_time = _now_utc_sqlite_timestamp()
        go = request.args.get("go") == "1"

        selected_account = None
        for account in quick_accounts:
            if selected.isdigit() and int(selected) == account["account_id"]:
                selected_account = account
                break

        if go:
            if selected_account is None:
                return Response.text("You must choose an account.", status=400)
            if not link:
                return Response.text("Link required", status=400)

            insert_sql = """
insert into content (
  platform_id, account_id, platform_content_id, url, is_post, content_type, title, body, notes, link, engagement_time
) values (
  :platform_id, :account_id, :platform_content_id, :url, :is_post, :content_type, :title, :body_textarea, :notes_textarea, :link, :engagement_time
);
            """.strip()

            qs = urlencode(
                {
                    "sql": insert_sql,
                    "platform_id": str(selected_account["platform_id"]),
                    "account_id": str(selected_account["account_id"]),
                    "platform_content_id": link,
                    "url": link,
                    "is_post": is_post,
                    "content_type": "post" if is_post == "1" else "comment",
                    "title": title,
                    "body_textarea": "",
                    "notes_textarea": notes_textarea,
                    "link": link,
                    "engagement_time": engagement_time,
                }
            )
            return Response.redirect(f"/{db_name}/-/write?{qs}")

        accounts_by_id = {account["account_id"]: account for account in quick_accounts}
        linkedin_account = accounts_by_id.get(LINKEDIN_QUICK_ACCOUNT_ID)
        linkedin_button = ""
        if linkedin_account:
            linkedin_id = str(linkedin_account["account_id"])
            checked = " checked" if linkedin_id == selected else ""
            linkedin_icon = _image_data_uri(QUICK_LINKEDIN_ICON)
            linkedin_icon_html = (
                f'<img class="linkedin-icon" src="{escape(linkedin_icon)}" alt="LinkedIn" />'
                if linkedin_icon
                else '<span class="linkedin-icon" aria-label="LinkedIn">in</span>'
            )
            linkedin_button = f"""
<label class="account-choice linkedin-choice" title="{escape(linkedin_account["platform"])}: {escape(linkedin_account["handle"])}">
  <input type="radio" name="account" value="{linkedin_id}"{checked} />
  <span class="account-stack">
    {linkedin_icon_html}
  </span>
</label>
                """.strip()

        account_buttons = []
        for account_id_int in YOUTUBE_QUICK_ACCOUNT_IDS:
            account = accounts_by_id.get(account_id_int)
            if not account:
                continue
            account_id = str(account["account_id"])
            icon_src = _account_icon(account)
            checked = " checked" if account_id == selected else ""
            avatar_html = (
                f'<img class="account-avatar" src="{escape(icon_src)}" alt="" />'
                if icon_src
                else f'<span class="account-avatar">{escape(_initials(account))}</span>'
            )
            account_buttons.append(
                f"""
<label class="account-choice" title="{escape(account["platform"])}: {escape(account["handle"])}">
  <input type="radio" name="account" value="{account_id}"{checked} />
  <span class="account-stack">
    {avatar_html}
  </span>
</label>
                """.strip()
            )
        youtube_icon = _image_data_uri(QUICK_YOUTUBE_ICON)
        youtube_icon_html = (
            f'<img class="youtube-mark" src="{escape(youtube_icon)}" alt="YouTube" />'
            if youtube_icon
            else '<span class="youtube-mark" aria-label="YouTube"></span>'
        )

        body = f"""
<div class="toplinks">
  <a href="/-/social-metrics/new?db={escape(db_name)}">Full form</a>
  <a href="/-/social-metrics/add-platform?db={escape(db_name)}">Add platform</a>
  <a href="/-/social-metrics/add-account?db={escape(db_name)}">Add account</a>
</div>

<form method="get">
  <input type="hidden" name="db" value="{escape(db_name)}" />
  <input type="hidden" name="engagement_time" value="{escape(engagement_time)}" />

  <section class="quick-panel" aria-label="Quick engagement">
    <div class="panel-header">
      <h1 class="panel-title">Social Metrics</h1>
      <div class="daily-count">{escape(str(today_count["count"]))}</div>
    </div>

    <fieldset>
      <legend>Account</legend>
      <div class="picker-stage">
        {linkedin_button}
        {youtube_icon_html}
        <div class="account-picker">
          {''.join(account_buttons)}
        </div>
      </div>
    </fieldset>

    <fieldset>
      <legend>Entry</legend>

      <label class="post-row">
        post?
        <input type="checkbox" name="is_post" value="1"{" checked" if is_post == "1" else ""} />
      </label>

      <div class="form-row">
        <label for="quick-title">Title</label>
        <input id="quick-title" type="text" name="title" value="{escape(title)}" />
      </div>

      <div class="form-row">
        <label for="quick-link">Link</label>
        <input id="quick-link" type="url" name="link" value="{escape(link)}" />
      </div>

      <div class="form-row">
        <label for="quick-notes">Notes</label>
        <textarea id="quick-notes" name="notes_textarea">{escape(notes_textarea)}</textarea>
      </div>
    </fieldset>

    <div class="submit-row">
      <button type="submit" name="go" value="1">Submit</button>
    </div>
  </section>
</form>
"""
        return Response.html(_quick_html_page("Quick engagement", body))

    return [
        (r"^/-/social-metrics$", social_metrics),
        (r"^/-/social-metrics/quick$", quick_engagement),
        (r"^/-/social-metrics/new$", new_engagement),
        (r"^/-/social-metrics/add-platform$", add_platform),
        (r"^/-/social-metrics/add-account$", add_account),
    ]


@hookimpl
def menu_links(datasette, actor):
    db_name = _pick_default_db(datasette)
    if not db_name:
        return []
    return [
        {"href": f"/-/social-metrics/quick?db={db_name}", "label": "Quick engagement"},
        {"href": f"/-/social-metrics/new?db={db_name}", "label": "New engagement"},
        {"href": f"/-/social-metrics/add-platform?db={db_name}", "label": "Add platform"},
        {"href": f"/-/social-metrics/add-account?db={db_name}", "label": "Add account"},
        {"href": f"/-/social-metrics?db={db_name}", "label": "Social metrics (JSON)"},
    ]
