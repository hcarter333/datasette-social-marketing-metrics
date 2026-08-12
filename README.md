# Datasette Social Metrics

Local Datasette setup for tracking social media engagement in SQLite.

## Quick Engagement Page

The plugin now includes a faster visual entry page in addition to the original full form:

- Quick page: `/-/social-metrics/quick?db=social_metrics`
- Full fallback form: `/-/social-metrics/new?db=social_metrics`

The quick page is designed for high-volume daily comment/link entry. It shows a small account picker at the top, then a minimal form:

- `post?` checkbox
- `Title`
- `Link`
- `Notes`
- `Submit`

By default, `post?` is unchecked because most daily traffic is comments. Unchecked entries are sent as `is_post=0` and `content_type=comment`; checked entries are sent as `is_post=1` and `content_type=post`.

The quick page is intentionally standalone: no Node, bundler, or external JavaScript is required.

## Datasette Write Flow

The quick page does not write directly to the database. It follows the existing plugin flow:

1. Collect minimal values with a GET form.
2. Build an `insert into content (...) values (...)` statement.
3. Redirect to `datasette-write` at `/{db}/-/write?...`.
4. Let the user review or correct values before executing the insert.

This keeps the current correction workflow intact, especially for editing `engagement_time`.

## Link Handling

For now, the quick page copies the `Link` field into all three link-related fields:

- `platform_content_id`
- `url`
- `link`

Future work can parse native platform content IDs from known URL formats.

## Account Picker

The quick page starts with a small curated set of common accounts, configured in `plugins/social_metrics.py`:

```python
LINKEDIN_QUICK_ACCOUNT_ID = 4
YOUTUBE_QUICK_ACCOUNT_IDS = [1, 3, 2]
QUICK_ACCOUNT_IDS = [LINKEDIN_QUICK_ACCOUNT_ID] + YOUTUBE_QUICK_ACCOUNT_IDS
```

Those IDs are loaded from the `account` table and joined to `platform` so each icon selection provides both `account_id` and `platform_id`. The current quick-entry layout shows the LinkedIn option on the left and the YouTube account avatars in the bordered picker group.

Update `QUICK_ACCOUNT_IDS` as more accounts should appear in the fast-entry picker.

The quick-entry icons live in the repo root:

- `linkedin_ico.png`
- `youtube.png`
- `antigrav_kids.png`
- `gladych_files.png`
- `cootermaroos_ico.png`

## Adding Quick Accounts

To add or change accounts shown on the quick-entry page, update the constants in `plugins/social_metrics.py`:

```python
LINKEDIN_QUICK_ACCOUNT_ID = 4
YOUTUBE_QUICK_ACCOUNT_IDS = [1, 3, 2]
QUICK_ACCOUNT_IDS = [LINKEDIN_QUICK_ACCOUNT_ID] + YOUTUBE_QUICK_ACCOUNT_IDS
QUICK_ACCOUNT_ICONS = {
    1: REPO_DIR / "antigrav_kids.png",
    3: REPO_DIR / "gladych_files.png",
    2: REPO_DIR / "cootermaroos_ico.png",
}
```

Use IDs from the `account` table. Each account ID is joined to `platform`, so the quick page gets both `account_id` and `platform_id` from that one ID. Add any new icon PNGs to the repo root and map the account ID to the filename in `QUICK_ACCOUNT_ICONS`.

## Daily Count

The quick page shows the count for the current UTC calendar date using `engagement_time`:

```sql
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
```

UTC is used to keep the daily accounting simple and consistent with SQLite `CURRENT_TIMESTAMP`.

## Running Locally

With Datasette 0.65.x available through Python:

```powershell
python -m datasette serve social_metrics.db --plugins-dir plugins --root -p 8004
```

Then open:

```text
http://127.0.0.1:8004/-/social-metrics/quick?db=social_metrics
```

If using a newer Datasette command style that supports named databases:

```powershell
datasette --db social_metrics=social_metrics.db --plugins-dir=plugins --root
```

## Related Plugin Routes

- `/-/social-metrics/quick`: visual quick-entry page
- `/-/social-metrics/new`: original full entry form
- `/-/social-metrics/add-platform`: add a platform through `datasette-write`
- `/-/social-metrics/add-account`: add an account through `datasette-write`
- `/-/social-metrics`: JSON summary endpoint
