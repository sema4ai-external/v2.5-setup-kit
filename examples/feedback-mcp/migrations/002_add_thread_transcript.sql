-- Store the full thread transcript (all turns incl. tool calls + thoughts, as
-- returned by the agent server messages API) alongside each feedback row.
alter table agent_feedback add column if not exists thread_transcript jsonb;
