-- Match INSERT's endpoint ownership invariant on UPDATE too.
DROP POLICY IF EXISTS "Users can update own connections" ON public.network_connections;
CREATE POLICY "Users can update own connections"
ON public.network_connections FOR UPDATE TO authenticated
USING (auth.uid() = user_id)
WITH CHECK (
  auth.uid() = user_id
  AND EXISTS (SELECT 1 FROM public.network_nodes s WHERE s.id = source_node_id AND s.user_id = auth.uid())
  AND EXISTS (SELECT 1 FROM public.network_nodes t WHERE t.id = target_node_id AND t.user_id = auth.uid())
);
