## Purpose
Generate a stable “Feedback Stack” report with charts + table.

## Inputs
- Semantic Data Model: `Agent Response Feedback`
- Existing/derived DataFrames may be queried via `sema4ai_data_frames`

## Required Outputs
1. Overall feedback split (thumb up vs down) — bar chart
2. Weekly feedback trend for last 2 calendar weeks — line chart with separate up/down lines
3. Feedback by file attachment status (`has_file` vs `no_file`) — bar chart
4. Agent feedback by volume — plain markdown table (NOT a chart)
5. Word-cloud-style visualization from notes — renderer-safe text-size chart (avoid unsupported wordcloud transforms)

## Tooling Rules
- Use `generate_sql` for all non-trivial queries (group by, filters, time windows, aggregations).
- Use one SDM per `generate_sql` call.
- Prefer `Agent Response Feedback` for source queries.
- If querying already-created frames, use `generate_sql` with `sema4ai_data_frames`.
- Use `data_frames_slice` only to inspect/preview frame contents.

## Query Specs
### A) Feedback split
From `agent_feedback`: count by `thumb_up_or_down`.

### B) Weekly trend (last 2 calendar weeks)
From `agent_feedback`: group by `date_trunc('week', created_at)::date` and `thumb_up_or_down`.
Include previous and current week; fill missing combos with 0 if possible.

### C) File attachment status
From `agent_feedback`: derive
- `no_file` if `input_file_refs` is null/empty array/empty object
- otherwise `has_file`
Then count by status.

### D) Agent volume table
From `agent_feedback`: top agents by total feedback with:
- `total_feedback`
- `thumbs_up_count`
- `thumbs_down_count`
- `thumbs_up_rate = thumbs_up_count / total_feedback`
Render as markdown table only.

### E) Notes word frequency
From `agent_feedback.notes`:
- tokenize/lowercase
- keep alphabetic words, length > 2
- remove stopwords
- count frequency
- sort `frequency desc, word asc