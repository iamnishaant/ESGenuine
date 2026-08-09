export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

// Schema mirrors the live Postgres tables. Source of truth, in order:
//   backend/database/schema.sql                            (claims, reports, contradictions)
//   backend/database/2026-06-25_observability_type.sql     (claims.observability_type)
//   backend/database/2026-07-03_framework_tags_quality_flags.sql
//   backend/database/2026-06-25_claim_reviews.sql
//   backend/database/2026-06-26_jobs_table.sql
//   backend/database/2026-07-11_satellite_evidence.sql + 2026-07-22_satellite_check_key.sql
//   backend/database/2026-07-19_contradictions_doc_id.sql  (contradictions.doc_id)
// The claims row set is kept in step with `_row()` in
// backend/src/extractors/supabase_ingest.py, which is what actually writes it.
//
// `users` is deliberately ABSENT: anon/authenticated are REVOKED on it
// (2026-06-26_users_table.sql) so it must never be reachable from the browser client.
//
// This file was previously an empty stub (`Tables: { [_ in never]: never }`), which
// typed every `.from(...)` as `never` and silently disabled type-checking on the
// frontend's primary data path. Regenerate with:
//   supabase gen types typescript --project-id <ref> > src/integrations/supabase/types.ts
export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.1"
  }
  public: {
    Tables: {
      claims: {
        Row: {
          claim_id: string
          doc_id: string | null
          report_id: string | null
          company_id: string | null
          company_name: string | null
          report_year: number | null
          page_number: number | null
          chunk_id: string | null
          source_sentence: string | null
          aspect: string | null
          normalized_aspect: string | null
          metric_family: string
          metric_key: string | null
          metric_value: number | null
          metric_unit: string | null
          metric_direction: string | null
          time_start: string | null
          time_end: string | null
          time_bucket: string | null
          location_text: string | null
          location_scope: string | null
          claim_type: string | null
          vagueness_score: number | null
          groundability_score: number | null
          observability_type: string | null
          framework_tags: string[] | null
          quality_flags: string[] | null
          claim_signature: string | null
          embedding: string | null
        }
        Insert: {
          claim_id: string
          doc_id?: string | null
          report_id?: string | null
          company_id?: string | null
          company_name?: string | null
          report_year?: number | null
          page_number?: number | null
          chunk_id?: string | null
          source_sentence?: string | null
          aspect?: string | null
          normalized_aspect?: string | null
          metric_family: string
          metric_key?: string | null
          metric_value?: number | null
          metric_unit?: string | null
          metric_direction?: string | null
          time_start?: string | null
          time_end?: string | null
          time_bucket?: string | null
          location_text?: string | null
          location_scope?: string | null
          claim_type?: string | null
          vagueness_score?: number | null
          groundability_score?: number | null
          observability_type?: string | null
          framework_tags?: string[] | null
          quality_flags?: string[] | null
          claim_signature?: string | null
          embedding?: string | null
        }
        Update: Partial<Database["public"]["Tables"]["claims"]["Insert"]>
        Relationships: []
      }
      contradictions: {
        Row: {
          id: number
          doc_id: string | null
          claim_a_id: string | null
          claim_b_id: string | null
          severity: string | null
          conflict_type: string | null
          reasoning: string | null
          confidence: number | null
          created_at: string | null
        }
        Insert: {
          id?: number
          doc_id?: string | null
          claim_a_id?: string | null
          claim_b_id?: string | null
          severity?: string | null
          conflict_type?: string | null
          reasoning?: string | null
          confidence?: number | null
          created_at?: string | null
        }
        Update: Partial<Database["public"]["Tables"]["contradictions"]["Insert"]>
        Relationships: []
      }
      reports: {
        Row: {
          report_id: string
          company_id: string
          company_name: string
          report_year: number
          report_type: string | null
          source_url: string | null
          file_path: string | null
          file_hash: string | null
          ingested_at: string | null
          claim_count: number | null
        }
        Insert: {
          report_id: string
          company_id: string
          company_name: string
          report_year: number
          report_type?: string | null
          source_url?: string | null
          file_path?: string | null
          file_hash?: string | null
          ingested_at?: string | null
          claim_count?: number | null
        }
        Update: Partial<Database["public"]["Tables"]["reports"]["Insert"]>
        Relationships: []
      }
      claim_reviews: {
        Row: {
          id: string
          doc_id: string
          subject_id: string
          flag_type: string
          verdict: string
          note: string | null
          reviewer: string | null
          created_at: string | null
        }
        Insert: {
          id?: string
          doc_id: string
          subject_id: string
          flag_type: string
          verdict: string
          note?: string | null
          reviewer?: string | null
          created_at?: string | null
        }
        Update: Partial<Database["public"]["Tables"]["claim_reviews"]["Insert"]>
        Relationships: []
      }
      jobs: {
        Row: {
          job_id: string
          report_id: string | null
          company_name: string | null
          report_year: number | null
          status: string
          error: string | null
          detail: Json | null
          created_at: string | null
          updated_at: string | null
        }
        Insert: {
          job_id: string
          report_id?: string | null
          company_name?: string | null
          report_year?: number | null
          status?: string
          error?: string | null
          detail?: Json | null
          created_at?: string | null
          updated_at?: string | null
        }
        Update: Partial<Database["public"]["Tables"]["jobs"]["Insert"]>
        Relationships: []
      }
      satellite_evidence: {
        Row: {
          id: number
          claim_id: string
          report_id: string | null
          verdict: "supported" | "not_supported" | "inconclusive"
          reason: string | null
          ndvi_delta: number | null
          z_score: number | null
          bundle: Json
          bundle_sha256: string
          check_key: string | null
          checked_at: string
        }
        Insert: {
          id?: number
          claim_id: string
          report_id?: string | null
          verdict: "supported" | "not_supported" | "inconclusive"
          reason?: string | null
          ndvi_delta?: number | null
          z_score?: number | null
          bundle: Json
          bundle_sha256: string
          check_key?: string | null
          checked_at?: string
        }
        Update: Partial<Database["public"]["Tables"]["satellite_evidence"]["Insert"]>
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      match_claims: {
        Args: {
          query_embedding: string
          match_threshold?: number
          match_count?: number
        }
        Returns: {
          claim_id: string
          doc_id: string
          source_sentence: string
          metric_key: string
          metric_value: number
          metric_unit: string
          time_bucket: string
          similarity: number
        }[]
      }
      search_claims: {
        Args: {
          query_embedding: string
          match_count?: number
        }
        Returns: {
          claim_id: string
          doc_id: string
          source_sentence: string
          similarity: number
        }[]
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
