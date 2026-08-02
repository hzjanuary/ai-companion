#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$root/scripts/lib/resolve-uv.sh"
uv_bin="$(resolve_uv "$root")"
dump="$root/.runtime/spec-016-synthetic.dump"
restore_db="january_spec016_restore"
cleanup() {
  docker compose exec -T database dropdb -U january --if-exists "$restore_db" >/dev/null 2>&1 || true
  rm -f "$dump"
  docker compose stop database >/dev/null 2>&1 || true
}
trap cleanup EXIT
export JANUARY_DATABASE_HOST=127.0.0.1
export JANUARY_DATABASE_PORT="${JANUARY_DB_HOST_PORT:-5432}"
export JANUARY_DATABASE_NAME=january
export JANUARY_DATABASE_USER=january
export JANUARY_DATABASE_PASSWORD=january-local
mkdir -p "$root/.runtime"
docker compose up -d database >/dev/null
for _ in $(seq 1 30); do docker compose exec -T database pg_isready -U january -d january >/dev/null 2>&1 && break; sleep 1; done
docker compose exec -T database pg_isready -U january -d january >/dev/null
"$uv_bin" run alembic upgrade head >/dev/null
docker compose exec -T database psql -v ON_ERROR_STOP=1 -U january -d january <<'SQL' >/dev/null
INSERT INTO assistants (id,name,status) VALUES ('10000000-0000-0000-0000-000000000001','Synthetic backup','active') ON CONFLICT DO NOTHING;
INSERT INTO platform_connections (id,assistant_id,platform,external_bot_id,status,configuration) VALUES ('20000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','telegram','synthetic-backup-bot','active','{}'::jsonb) ON CONFLICT DO NOTHING;
INSERT INTO conversations (id,platform_connection_id,platform_conversation_id,conversation_type,status,response_mode,settings,memory_privacy_revision) VALUES ('30000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','synthetic-backup-conversation','private','active','mention_only','{}'::jsonb,1) ON CONFLICT DO NOTHING;
INSERT INTO participants (id,conversation_id,platform_user_id,display_name,role,mention_allowed,teasing_allowed,membership_status,is_bot,privacy_deleted_at,metadata) VALUES ('40000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','synthetic-participant','Redacted','member',true,false,'member',false,now(),'{}'::jsonb) ON CONFLICT DO NOTHING;
INSERT INTO incoming_platform_updates (id,platform_connection_id,platform,platform_update_id,update_type,ingress_source,raw_payload,status,received_at,payload_redacted_at) VALUES ('50000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001','telegram','synthetic-update','message','polling','{}'::jsonb,'received',now(),now()) ON CONFLICT DO NOTHING;
INSERT INTO messages (id,conversation_id,participant_id,platform_message_id,direction,message_type,processing_status,text,content_redacted_at,metadata) VALUES ('60000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000001','synthetic-message','incoming','text','processed',NULL,now(),'{}'::jsonb) ON CONFLICT DO NOTHING;
INSERT INTO conversation_processing_records (id,incoming_update_id,outcome,conversation_id,message_id) VALUES ('70000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000001','message_created','30000000-0000-0000-0000-000000000001','60000000-0000-0000-0000-000000000001') ON CONFLICT DO NOTHING;
INSERT INTO response_planning_jobs (id,conversation_processing_record_id,conversation_id,message_id,status,prompt_version,response_schema_version,safety_policy_version) VALUES ('80000000-0000-0000-0000-000000000001','70000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','60000000-0000-0000-0000-000000000001','failed','synthetic','synthetic','safety-policy-v1') ON CONFLICT DO NOTHING;
INSERT INTO response_plans (id,planning_job_id,should_respond,reason_code,mention_participant_ids,confidence,prompt_version,schema_version,interaction_kind,teasing_target_participant_ids) VALUES ('90000000-0000-0000-0000-000000000001','80000000-0000-0000-0000-000000000001',true,'answer','[]'::jsonb,1,'synthetic','synthetic','neutral','[]'::jsonb) ON CONFLICT DO NOTHING;
INSERT INTO outbound_actions (id,response_plan_id,conversation_id,sequence_number,idempotency_key,kind,status,mention_participant_ids,text,completed_at) VALUES ('a0000000-0000-0000-0000-000000000001','90000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',1,'synthetic-backup-idempotency','text','delivered','[]'::jsonb,'synthetic delivered',now()) ON CONFLICT DO NOTHING;
INSERT INTO safety_policy_decisions (id,planning_job_id,conversation_id,policy_version,stage,outcome,transformed) VALUES ('c0000000-0000-0000-0000-000000000001','80000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','safety-policy-v1','pre_generation','allow',false) ON CONFLICT DO NOTHING;
INSERT INTO rate_limit_events (id,outbound_action_id,operation,allowed,configuration_version) VALUES ('d0000000-0000-0000-0000-000000000001','a0000000-0000-0000-0000-000000000001','delivery',true,'safety-policy-v1') ON CONFLICT DO NOTHING;
INSERT INTO operational_recovery_items (id,work_kind,work_id,disposition,reason) VALUES ('b0000000-0000-0000-0000-000000000001','planning','80000000-0000-0000-0000-000000000001','dead_letter','provider_retry_exhausted'), ('b0000000-0000-0000-0000-000000000002','outbound','a0000000-0000-0000-0000-000000000001','quarantine','ambiguous_external_delivery') ON CONFLICT DO NOTHING;
SQL
docker compose exec -T database pg_dump -U january -Fc january > "$dump"
docker compose exec -T database createdb -U january "$restore_db"
docker compose exec -T database pg_restore -U january -d "$restore_db" < "$dump"
result="$(docker compose exec -T database psql -At -U january -d "$restore_db" -c "SELECT (SELECT version_num FROM alembic_version), (SELECT count(*) FROM messages WHERE id='60000000-0000-0000-0000-000000000001' AND text IS NULL AND content_redacted_at IS NOT NULL), (SELECT count(*) FROM outbound_actions WHERE id='a0000000-0000-0000-0000-000000000001' AND status='delivered' AND idempotency_key='synthetic-backup-idempotency'), (SELECT count(*) FROM safety_policy_decisions), (SELECT count(*) FROM rate_limit_events), (SELECT count(*) FROM operational_recovery_items WHERE disposition='dead_letter'), (SELECT count(*) FROM operational_recovery_items WHERE disposition='quarantine')")"
[[ "$result" == "0013_semantic_memory_index|1|1|1|1|1|1" ]]
echo "Synthetic PostgreSQL backup/restore rehearsal: valid (revision, redaction, idempotency, safety/rate, recovery)"
