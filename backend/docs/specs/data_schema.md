# Data Storage Architecture

All storage decisions frozen at Week 1. No database redesigns after this.

---

## 1. PostgreSQL (Primary Relational Store)

### `reports` table

| Column         | Type                                                   | Notes |
| -------------- | ------------------------------------------------------ | ----- |
| `report_id`    | `UUID` PK                                              |       |
| `company_name` | `TEXT`                                                 |       |
| `filename`     | `TEXT`                                                 |       |
| `upload_date`  | `TIMESTAMP`                                            |       |
| `total_pages`  | `INT`                                                  |       |
| `status`       | `ENUM(uploaded, parsing, parsed, analyzing, complete)` |       |

### `document_blocks` table

| Column          | Type                                                       | Notes               |
| --------------- | ---------------------------------------------------------- | ------------------- |
| `block_id`      | `TEXT` PK                                                  | e.g. `p3_b7`        |
| `report_id`     | `UUID` FK                                                  |                     |
| `page_number`   | `INT`                                                      |                     |
| `block_type`    | `ENUM(heading, paragraph, table, list, caption, footnote)` |                     |
| `text`          | `TEXT`                                                     |                     |
| `section_label` | `TEXT`                                                     | Mapped ESG category |
| `bbox`          | `JSONB`                                                    | `{x0, y0, x1, y1}`  |
| `font_size`     | `FLOAT`                                                    |                     |

### `claims` table

| Column                 | Type                                                   | Notes                            |
| ---------------------- | ------------------------------------------------------ | -------------------------------- |
| `claim_id`             | `UUID` PK                                              |                                  |
| `report_id`            | `UUID` FK                                              |                                  |
| `aspect`               | `TEXT`                                                 |                                  |
| `action`               | `TEXT`                                                 |                                  |
| `metric_value`         | `FLOAT`                                                | nullable                         |
| `metric_unit`          | `TEXT`                                                 | nullable                         |
| `location_raw`         | `TEXT`                                                 |                                  |
| `location_specificity` | `TEXT`                                                 |                                  |
| `time_start`           | `DATE`                                                 | nullable                         |
| `time_end`             | `DATE`                                                 | nullable                         |
| `source_sentence`      | `TEXT`                                                 | Provenance                       |
| `page_number`          | `INT`                                                  | Provenance                       |
| `block_id`             | `TEXT` FK                                              | Provenance                       |
| `section_label`        | `TEXT`                                                 | Provenance                       |
| `bbox`                 | `JSONB`                                                | Provenance                       |
| `confidence`           | `FLOAT`                                                | LLM extraction confidence        |
| `cve_score`            | `FLOAT`                                                | Computed in Week 6               |
| `observability_type`   | `ENUM(optical_possible, sar_possible, not_observable)` |                                  |
| `integrity_gap`        | `FLOAT`                                                | Computed in Week 8               |
| `embedding`            | `VECTOR(1024)`                                         | pgvector for similarity (Week 4) |

### `audit_events` table

| Column      | Type                              | Notes                                       |
| ----------- | --------------------------------- | ------------------------------------------- |
| `event_id`  | `UUID` PK                         |                                             |
| `claim_id`  | `UUID` FK                         |                                             |
| `step_name` | `TEXT`                            | e.g. `parse`, `extract`, `cve`, `satellite` |
| `status`    | `ENUM(success, failure, skipped)` |                                             |
| `timestamp` | `TIMESTAMP`                       |                                             |
| `details`   | `JSONB`                           | Arbitrary step output                       |

---

## 2. PostGIS Extension (Geospatial)

Adds `GEOMETRY` type to PostgreSQL.

### `facility_geometries` table

| Column        | Type                      | Notes                               |
| ------------- | ------------------------- | ----------------------------------- |
| `facility_id` | `UUID` PK                 |                                     |
| `claim_id`    | `UUID` FK                 |                                     |
| `point`       | `GEOMETRY(Point, 4326)`   | Geocoded lat/lng                    |
| `polygon`     | `GEOMETRY(Polygon, 4326)` | Facility boundary (if available)    |
| `buffer_km`   | `FLOAT`                   | Search radius for satellite imagery |

---

## 3. Object Storage (PDFs + Imagery)

Local filesystem in dev, S3-compatible in prod.

```
/uploads/
  {report_id}/
    original.pdf

/parsed/
  {document_id}/
    full.json
    sections.json
    sentences.json
    candidates.json
    chunks.json
    provenance.json
    table_rows.json

/satellite/
  {claim_id}/
    sentinel2_before.tif
    sentinel2_after.tif
    ndvi_before.tif
    ndvi_after.tif
    thumbnail.png
```

---

## 4. Claim Contradiction Graph (In-Postgres with JSONB)

> Using Neo4j is overkill for a solo project.
> We store the graph edges in PostgreSQL using the `document_graph_schema.json` format.

### `claim_edges` table

| Column            | Type                                        | Notes                                |
| ----------------- | ------------------------------------------- | ------------------------------------ |
| `edge_id`         | `UUID` PK                                   |                                      |
| `source_claim_id` | `UUID` FK                                   |                                      |
| `target_claim_id` | `UUID` FK                                   |                                      |
| `edge_type`       | `ENUM(contradicts, supports, duplicate_of)` |                                      |
| `severity`        | `FLOAT`                                     | 0-1 contradiction strength           |
| `nli_label`       | `TEXT`                                      | entailment / contradiction / neutral |
| `nli_confidence`  | `FLOAT`                                     | Model confidence                     |

---

## 5. Supabase (Auth + Edge Functions)

Already configured. Used for:

- User authentication
- `analyze-claims` Edge Function (existing)
- Row-level security on claims/reports

---

## Migration Strategy

Week 3: Create tables via Supabase migrations (`supabase/migrations/`).
Week 4: Add pgvector extension + embedding column.
Week 5: Add PostGIS extension + geometry columns.
