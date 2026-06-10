-- agent_feedback: one row per thumbs up/down the user gives on an agent suggestion.
create extension if not exists "pgcrypto";

create table if not exists agent_feedback (
  id                     uuid primary key default gen_random_uuid(),
  created_at             timestamptz not null default now(),
  tenant_id              text,
  user_id                text,        -- acting user (invoked_on_behalf_of_user_id)
  agent_id               text not null,
  thread_id              text not null,
  rated_message_id       text,        -- id of the rated agent message (for step-scoped gating)
  thumb_up_or_down       text not null check (thumb_up_or_down in ('up','down')),
  notes                  text,        -- optional free-text the user added with the thumb
  rated_agent_message    text,        -- the specific agent suggestion the thumb is about
  preceding_user_message text,        -- what the user sent right before that suggestion
  input_file_refs        jsonb not null default '[]'::jsonb,   -- [{name,mime_type,uri}] refs only
  thread_transcript      jsonb,       -- full thread messages (turns + tool calls + thoughts)
  source_url             text
);

create index if not exists agent_feedback_thread_idx on agent_feedback (thread_id, created_at desc);
create index if not exists agent_feedback_agent_idx  on agent_feedback (agent_id, created_at desc);
create index if not exists agent_feedback_thumb_idx  on agent_feedback (thumb_up_or_down);
create index if not exists agent_feedback_user_idx   on agent_feedback (user_id);
