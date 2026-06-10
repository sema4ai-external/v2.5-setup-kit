-- Capture the acting user so we can count distinct users giving feedback.
-- Sourced from invoked_on_behalf_of_user_id in the tool invocation context.
alter table agent_feedback add column if not exists user_id text;
create index if not exists agent_feedback_user_idx on agent_feedback (user_id);
