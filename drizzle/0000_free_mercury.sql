CREATE TABLE `pipeline_status` (
	`id` integer PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`source_id` text NOT NULL,
	`platform` text NOT NULL,
	`runtime` text NOT NULL,
	`status` text NOT NULL,
	`operational_status` text NOT NULL,
	`started_at` text NOT NULL,
	`completed_at` text NOT NULL,
	`received_at` text NOT NULL,
	`active_rules` integer NOT NULL,
	`videos_discovered` integer NOT NULL,
	`events_emitted` integer NOT NULL,
	`search_calls_remaining` integer NOT NULL,
	`core_units_remaining` integer NOT NULL,
	`error_type` text NOT NULL
);
