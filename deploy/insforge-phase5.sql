-- Run in the same InsForge project's SQL Editor after phase 4.
-- Additive: keeps existing investigations and their user-isolation policies.
-- No BEGIN/COMMIT wrapper: the hosted SQL Editor rejects transaction controls.
ALTER TABLE public.investigations ADD COLUMN IF NOT EXISTS cluster_context text;
ALTER TABLE public.investigations ADD COLUMN IF NOT EXISTS cluster_name text;
ALTER TABLE public.investigations ADD COLUMN IF NOT EXISTS summary jsonb;
CREATE INDEX IF NOT EXISTS investigations_user_context_created_idx
  ON public.investigations(user_id, cluster_context, created_at DESC);
