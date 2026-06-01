-- =============================================================================
-- Legal Eagle AI - Supabase schema
-- Run this in the Supabase SQL editor (or via supabase-cli) to set up tables.
-- =============================================================================

create table if not exists research_sessions (
    session_id text primary key,
    original_query text not null,
    created_at timestamptz not null default now(),
    metadata jsonb not null default '{}'::jsonb
);

create table if not exists legal_documents (
    document_id text primary key,
    jurisdiction text not null check (jurisdiction in ('us', 'eu')),
    title text not null,
    document_type text not null,
    full_text text,
    metadata jsonb not null default '{}'::jsonb,
    citations text[] not null default '{}',
    cited_by text[] not null default '{}',
    url text not null,
    retrieved_at timestamptz not null default now(),
    provenance_id text not null,
    relevance_score double precision not null default 0,
    date_decided text,
    court_or_body text,
    celex text,
    eurovoc_descriptors text[] not null default '{}'
);

create index if not exists idx_legal_documents_jurisdiction
    on legal_documents (jurisdiction);
create index if not exists idx_legal_documents_celex
    on legal_documents (celex);

create table if not exists provenance_log (
    id text primary key,
    session_id text not null references research_sessions (session_id) on delete cascade,
    jurisdiction text not null,
    source text not null,
    query text not null,
    documents_returned int not null,
    created_at timestamptz not null default now(),
    extra jsonb not null default '{}'::jsonb
);

create table if not exists research_reports (
    session_id text primary key references research_sessions (session_id) on delete cascade,
    payload jsonb not null,
    updated_at timestamptz not null default now()
);
