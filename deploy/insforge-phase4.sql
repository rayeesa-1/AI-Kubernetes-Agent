-- Run once in the SQL editor of a NEW/dedicated InsForge project as project admin.
-- Review existing permissive realtime policies before reusing a shared project.
BEGIN;
CREATE TABLE IF NOT EXISTS public.investigations (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  namespace text NOT NULL DEFAULT 'All namespaces',
  status text NOT NULL CHECK (status IN ('running','completed','partial','error')),
  root_cause text,
  confidence integer CHECK (confidence BETWEEN 0 AND 100),
  diagnosis jsonb,
  ai_error text,
  progress jsonb NOT NULL DEFAULT '{}'::jsonb,
  revision integer NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS investigations_user_created_idx
  ON public.investigations(user_id, created_at DESC);
ALTER TABLE public.investigations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.investigations FROM anon, authenticated;
GRANT SELECT ON public.investigations TO authenticated;
DROP POLICY IF EXISTS investigations_owner_read ON public.investigations;
CREATE POLICY investigations_owner_read ON public.investigations FOR SELECT TO authenticated
  USING (user_id = auth.uid());
-- All writes go through FastAPI with a server-only project admin API key.
GRANT ALL ON public.investigations TO project_admin;

INSERT INTO realtime.channels (pattern, description, enabled)
VALUES ('investigation:%', 'Private per-user investigation progress', true)
ON CONFLICT (pattern) DO NOTHING;
ALTER TABLE realtime.channels ENABLE ROW LEVEL SECURITY;
ALTER TABLE realtime.messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS investigation_subscribe ON realtime.channels;
CREATE POLICY investigation_subscribe ON realtime.channels FOR SELECT TO authenticated
USING (pattern = 'investigation:%'
  AND realtime.channel_name() = 'investigation:' || auth.uid()::text);
-- Restrictive policies also guard against another permissive policy in this project.
DROP POLICY IF EXISTS investigation_channel_guard ON realtime.channels;
CREATE POLICY investigation_channel_guard ON realtime.channels AS RESTRICTIVE FOR SELECT TO authenticated
USING (realtime.channel_name() NOT LIKE 'investigation:%'
  OR realtime.channel_name() = 'investigation:' || auth.uid()::text);
DROP POLICY IF EXISTS investigation_no_anon ON realtime.channels;
CREATE POLICY investigation_no_anon ON realtime.channels AS RESTRICTIVE FOR SELECT TO anon
USING (realtime.channel_name() NOT LIKE 'investigation:%');
DROP POLICY IF EXISTS investigation_no_client_publish ON realtime.messages;
CREATE POLICY investigation_no_client_publish ON realtime.messages AS RESTRICTIVE FOR INSERT TO anon, authenticated
WITH CHECK (channel_name NOT LIKE 'investigation:%');

CREATE OR REPLACE FUNCTION public.publish_investigation_progress()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  -- No logs, credentials, diagnosis text, or raw evidence are broadcast.
  PERFORM realtime.publish(
    'investigation:' || NEW.user_id::text,
    'investigation_progress',
    jsonb_build_object('id', NEW.id, 'status', NEW.status,
      'progress', NEW.progress, 'revision', NEW.revision)
  );
  RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.publish_investigation_progress() FROM PUBLIC;
DROP TRIGGER IF EXISTS investigation_progress_trigger ON public.investigations;
CREATE TRIGGER investigation_progress_trigger AFTER INSERT OR UPDATE ON public.investigations
FOR EACH ROW EXECUTE FUNCTION public.publish_investigation_progress();
COMMIT;
