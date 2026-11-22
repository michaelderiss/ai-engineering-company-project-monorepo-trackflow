-- Apply to the same PostgreSQL database configured by TELEMETRY_DATABASE_URL.
-- job_runs tracks nightly orchestration; reporting.pipeline_runs tracks ETL.
CREATE TABLE IF NOT EXISTS public.job_runs (
    id UUID PRIMARY KEY,
    job_name TEXT NOT NULL,
    target_date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_job_runs_job_name_target_date
    ON public.job_runs (job_name, target_date);

-- Processing status itself is the distributed lock. PostgreSQL guarantees that
-- independent worker processes cannot claim the same job concurrently.
CREATE UNIQUE INDEX IF NOT EXISTS uq_job_runs_processing_job_name
    ON public.job_runs (job_name)
    WHERE status = 'processing';

-- A successful date remains claimed forever; failed dates can be retried.
CREATE UNIQUE INDEX IF NOT EXISTS uq_job_runs_active_or_completed_date
    ON public.job_runs (job_name, target_date)
    WHERE status IN ('processing', 'completed');
