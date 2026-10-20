CREATE TABLE public.simulation_experiments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  topology_fingerprint text NOT NULL,
  scenario_id text NOT NULL,
  scenario_parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  traffic_configuration jsonb NOT NULL,
  engine_version text NOT NULL,
  baseline_snapshot jsonb NOT NULL,
  failure_snapshot jsonb NOT NULL,
  modernized_snapshot jsonb,
  proposal jsonb,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'failure_simulated' CHECK (status IN ('failure_simulated', 'modernized')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE ON public.simulation_experiments TO authenticated;
GRANT ALL ON public.simulation_experiments TO service_role;
ALTER TABLE public.simulation_experiments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own simulation experiments" ON public.simulation_experiments FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "Users can create own simulation experiments" ON public.simulation_experiments FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own simulation experiments" ON public.simulation_experiments FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE INDEX simulation_experiments_user_created_idx ON public.simulation_experiments (user_id, created_at DESC);
CREATE TRIGGER set_simulation_experiments_updated_at BEFORE UPDATE ON public.simulation_experiments FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
