import { integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const pipelineStatus = sqliteTable("pipeline_status", {
  id: integer("id").primaryKey(),
  runId: text("run_id").notNull(),
  sourceId: text("source_id").notNull(),
  platform: text("platform").notNull(),
  runtime: text("runtime").notNull(),
  status: text("status").notNull(),
  operationalStatus: text("operational_status").notNull(),
  startedAt: text("started_at").notNull(),
  completedAt: text("completed_at").notNull(),
  receivedAt: text("received_at").notNull(),
  activeRules: integer("active_rules").notNull(),
  videosDiscovered: integer("videos_discovered").notNull(),
  eventsEmitted: integer("events_emitted").notNull(),
  searchCallsRemaining: integer("search_calls_remaining").notNull(),
  coreUnitsRemaining: integer("core_units_remaining").notNull(),
  errorType: text("error_type").notNull(),
});
