// Single Supabase client for the whole app. Re-exports the typed generated
// client so there is exactly ONE GoTrue/auth instance and one Database-typed
// client — two parallel createClient() calls previously risked auth-storage
// conflicts and type drift.
export { supabase } from '@/integrations/supabase/client';
