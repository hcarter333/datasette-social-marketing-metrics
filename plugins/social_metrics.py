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

from html import escape
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
    <button type="submit" name="go" value="1">Continue to datasette-write…</button>
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
    <button type="submit" name="go" value="1">Continue to datasette-write…</button>
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
<b>Continue to datasette-write…</b> to execute the INSERT.
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
    <button type="submit" name="go" value="1">Continue to datasette-write…</button>
    <a href="/-/social-metrics/new?db={escape(db_name)}">Reset</a>
  </div>
</form>
"""
        return Response.html(_html_page("New engagement", body))

    return [
        (r"^/-/social-metrics$", social_metrics),
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
        {"href": f"/-/social-metrics/new?db={db_name}", "label": "New engagement"},
        {"href": f"/-/social-metrics/add-platform?db={db_name}", "label": "Add platform"},
        {"href": f"/-/social-metrics/add-account?db={db_name}", "label": "Add account"},
        {"href": f"/-/social-metrics?db={db_name}", "label": "Social metrics (JSON)"},
    ]
