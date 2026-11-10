-- 档位随投递持久保存，超时重试和进程恢复不能改变同一消息的选择。
ALTER TABLE agent_deliveries ADD COLUMN effort TEXT;
CREATE INDEX agent_deliveries_session_created ON agent_deliveries(session_id, created_at);
