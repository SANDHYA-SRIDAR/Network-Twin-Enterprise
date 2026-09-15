CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TABLE public.user_profiles (
  id uuid PRIMARY KEY,
  display_name text NOT NULL DEFAULT '',
  theme text NOT NULL DEFAULT 'dark' CHECK (theme IN ('light', 'dark')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_profiles TO authenticated;
GRANT ALL ON public.user_profiles TO service_role;
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own profile" ON public.user_profiles FOR SELECT TO authenticated USING (auth.uid() = id);
CREATE POLICY "Users can create own profile" ON public.user_profiles FOR INSERT TO authenticated WITH CHECK (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON public.user_profiles FOR UPDATE TO authenticated USING (auth.uid() = id) WITH CHECK (auth.uid() = id);
CREATE POLICY "Users can delete own profile" ON public.user_profiles FOR DELETE TO authenticated USING (auth.uid() = id);
CREATE TRIGGER set_user_profiles_updated_at BEFORE UPDATE ON public.user_profiles FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.user_profiles (id, display_name)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data ->> 'display_name', split_part(COALESCE(NEW.email, ''), '@', 1)))
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;
CREATE TRIGGER on_auth_user_created AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

CREATE TABLE public.network_nodes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  node_type text NOT NULL CHECK (node_type IN ('core-router', 'distribution-switch', 'cloud-server', 'load-balancer')),
  label text NOT NULL,
  position_x double precision NOT NULL DEFAULT 0,
  position_y double precision NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'healthy' CHECK (status IN ('healthy', 'warning', 'offline')),
  configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.network_nodes TO authenticated;
GRANT ALL ON public.network_nodes TO service_role;
ALTER TABLE public.network_nodes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own nodes" ON public.network_nodes FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Users can create own nodes" ON public.network_nodes FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own nodes" ON public.network_nodes FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own nodes" ON public.network_nodes FOR DELETE TO authenticated USING (auth.uid() = user_id);
CREATE INDEX network_nodes_user_id_idx ON public.network_nodes (user_id);
CREATE TRIGGER set_network_nodes_updated_at BEFORE UPDATE ON public.network_nodes FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE public.network_connections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  source_node_id uuid NOT NULL REFERENCES public.network_nodes(id) ON DELETE CASCADE,
  target_node_id uuid NOT NULL REFERENCES public.network_nodes(id) ON DELETE CASCADE,
  source_handle text,
  target_handle text,
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'degraded', 'offline')),
  configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (source_node_id <> target_node_id)
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.network_connections TO authenticated;
GRANT ALL ON public.network_connections TO service_role;
ALTER TABLE public.network_connections ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own connections" ON public.network_connections FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Users can create own connections" ON public.network_connections FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id AND EXISTS (SELECT 1 FROM public.network_nodes s WHERE s.id = source_node_id AND s.user_id = auth.uid()) AND EXISTS (SELECT 1 FROM public.network_nodes t WHERE t.id = target_node_id AND t.user_id = auth.uid()));
CREATE POLICY "Users can update own connections" ON public.network_connections FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own connections" ON public.network_connections FOR DELETE TO authenticated USING (auth.uid() = user_id);
CREATE INDEX network_connections_user_id_idx ON public.network_connections (user_id);
CREATE INDEX network_connections_source_idx ON public.network_connections (source_node_id);
CREATE INDEX network_connections_target_idx ON public.network_connections (target_node_id);
CREATE TRIGGER set_network_connections_updated_at BEFORE UPDATE ON public.network_connections FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TABLE public.chat_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  role text NOT NULL CHECK (role IN ('user', 'assistant')),
  parts jsonb NOT NULL DEFAULT '[]'::jsonb,
  sequence bigint GENERATED BY DEFAULT AS IDENTITY,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_messages TO authenticated;
GRANT ALL ON public.chat_messages TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.chat_messages_sequence_seq TO authenticated;
GRANT ALL ON SEQUENCE public.chat_messages_sequence_seq TO service_role;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own chat" ON public.chat_messages FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Users can create own chat" ON public.chat_messages FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own chat" ON public.chat_messages FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can delete own chat" ON public.chat_messages FOR DELETE TO authenticated USING (auth.uid() = user_id);
CREATE INDEX chat_messages_user_sequence_idx ON public.chat_messages (user_id, sequence);
CREATE TRIGGER set_chat_messages_updated_at BEFORE UPDATE ON public.chat_messages FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER PUBLICATION supabase_realtime ADD TABLE public.network_nodes;
ALTER PUBLICATION supabase_realtime ADD TABLE public.network_connections;