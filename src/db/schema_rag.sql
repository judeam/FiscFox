-- FiscFox RAG Database Schema
-- Vector storage for German tax law knowledge base
--
-- Uses sqlite-vec for vector similarity search
-- Combined with FTS5 for keyword search
-- RRF (Reciprocal Rank Fusion) for hybrid retrieval

-- =============================================================================
-- Tax Law Sources
-- =============================================================================

-- Source documents for tax law knowledge
-- EStG (Einkommensteuergesetz), UStG (Umsatzsteuergesetz), AO (Abgabenordnung)
-- BMF (Bundesministerium der Finanzen letters), BFH (Bundesfinanzhof rulings)
CREATE TABLE IF NOT EXISTS tax_law_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL CHECK (source_type IN (
        'estg',     -- Einkommensteuergesetz
        'ustg',     -- Umsatzsteuergesetz
        'ao',       -- Abgabenordnung
        'bmf',      -- BMF-Schreiben
        'bfh',      -- BFH-Urteile
        'richtlinie'  -- Steuerrichtlinien
    )),
    title TEXT NOT NULL CHECK (length(title) >= 1 AND length(title) <= 500),
    version_date DATE,  -- Version/publication date
    source_url TEXT,    -- Official source URL
    full_text TEXT,     -- Complete document text (for reference)
    checksum TEXT,      -- SHA256 for change detection
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tax_law_sources_type ON tax_law_sources(source_type);


-- =============================================================================
-- Hierarchical Chunking (Parent-Child)
-- =============================================================================

-- Parent chunks: Full sections (§) for context retrieval
-- When a child chunk is matched, we retrieve the parent for full context
CREATE TABLE IF NOT EXISTS tax_law_parent_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES tax_law_sources(id),
    -- Citation format: "§ 7 Abs. 1 EStG" or "BMF 2021-02-26 Tz. 1"
    citation TEXT NOT NULL CHECK (length(citation) >= 1 AND length(citation) <= 100),
    title TEXT NOT NULL CHECK (length(title) >= 1 AND length(title) <= 300),
    content TEXT NOT NULL,  -- Full section text
    section_number TEXT,    -- e.g., "7" for § 7
    -- Structure
    hierarchy_level INTEGER DEFAULT 1,  -- 1=§, 2=Abs, 3=Satz
    parent_chunk_id INTEGER REFERENCES tax_law_parent_chunks(id),  -- Self-reference for hierarchy
    -- Metadata
    effective_date DATE,    -- When the law became effective
    last_modified DATE,     -- Last amendment date
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_parent_chunks_source ON tax_law_parent_chunks(source_id);
CREATE INDEX IF NOT EXISTS idx_parent_chunks_citation ON tax_law_parent_chunks(citation);


-- Child chunks: Paragraphs for precise embedding matching
-- Smaller chunks (128-256 tokens) for better semantic matching
CREATE TABLE IF NOT EXISTS tax_law_child_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_chunk_id INTEGER NOT NULL REFERENCES tax_law_parent_chunks(id),
    source_id INTEGER NOT NULL REFERENCES tax_law_sources(id),
    -- Citation includes parent + child position
    citation TEXT NOT NULL CHECK (length(citation) >= 1 AND length(citation) <= 150),
    content TEXT NOT NULL CHECK (length(content) >= 10),
    -- Position within parent
    chunk_index INTEGER NOT NULL DEFAULT 0,  -- Order within parent
    char_start INTEGER,  -- Start position in parent
    char_end INTEGER,    -- End position in parent
    -- Token count for context management
    token_count INTEGER,
    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_child_chunks_parent ON tax_law_child_chunks(parent_chunk_id);
CREATE INDEX IF NOT EXISTS idx_child_chunks_source ON tax_law_child_chunks(source_id);


-- =============================================================================
-- Vector Storage (sqlite-vec)
-- =============================================================================

-- Vector embeddings for semantic search
-- Uses BAAI/bge-m3 (1024 dimensions) by default; must match LLMSettings.embedding_dim
-- sqlite-vec virtual table for efficient similarity search
CREATE VIRTUAL TABLE IF NOT EXISTS tax_law_vectors USING vec0(
    chunk_id INTEGER PRIMARY KEY,
    embedding FLOAT[1024]  -- 1024-dim embeddings (see FISCFOX_LLM_EMBEDDING_DIM)
);


-- =============================================================================
-- Full-Text Search (FTS5)
-- =============================================================================

-- FTS5 index for keyword/BM25 search
-- Supports German word stemming and tokenization
CREATE VIRTUAL TABLE IF NOT EXISTS tax_law_fts USING fts5(
    citation,
    title,
    content,
    tokenize = 'unicode61 remove_diacritics 1'
);

-- Mapping table to link FTS rowid to chunk_id
CREATE TABLE IF NOT EXISTS tax_law_fts_map (
    fts_rowid INTEGER PRIMARY KEY,
    chunk_id INTEGER NOT NULL REFERENCES tax_law_child_chunks(id)
);


-- =============================================================================
-- Query History and Analytics
-- =============================================================================

-- Track RAG queries for improvement and analytics
CREATE TABLE IF NOT EXISTS rag_query_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT NOT NULL CHECK (length(query_text) >= 1),
    intent_type TEXT CHECK (intent_type IN (
        'tax_law', 'financial_query', 'afa_assist',
        'expense_categorize', 'invoice_risk', 'general_chat'
    )),
    -- Retrieved chunks (stored as JSON array of chunk_ids)
    retrieved_chunk_ids TEXT,  -- JSON array
    -- Quality metrics
    confidence_score REAL,     -- 0.0 to 1.0
    user_feedback TEXT CHECK (user_feedback IN ('helpful', 'not_helpful', NULL)),
    -- Response data
    response_text TEXT,
    response_time_ms INTEGER,
    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rag_query_intent ON rag_query_history(intent_type);
CREATE INDEX IF NOT EXISTS idx_rag_query_created ON rag_query_history(created_at);


-- =============================================================================
-- Category-Law References
-- =============================================================================

-- Links expense categories to relevant tax law sections
-- Enables context-aware retrieval
CREATE TABLE IF NOT EXISTS tax_law_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL CHECK (category IN (
        'buero', 'software', 'hardware', 'reise', 'bewirtung',
        'telefon', 'versicherung', 'fortbildung', 'fachliteratur',
        'beratung', 'miete', 'werbung', 'kfzkosten', 'sonstige', 'geschenke'
    )),
    chunk_id INTEGER NOT NULL REFERENCES tax_law_child_chunks(id),
    relevance_score REAL DEFAULT 1.0,  -- Higher = more relevant
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tax_refs_category ON tax_law_references(category);


-- =============================================================================
-- Embedding Cache
-- =============================================================================

-- Cache for query embeddings to avoid re-computation
CREATE TABLE IF NOT EXISTS embedding_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text_hash TEXT NOT NULL UNIQUE,  -- SHA256 of input text
    embedding BLOB NOT NULL,         -- Serialized embedding vector
    model_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_embedding_cache_hash ON embedding_cache(text_hash);


-- =============================================================================
-- RRF Hybrid Search View
-- =============================================================================

-- Example RRF query (used programmatically, not as a persistent view):
--
-- WITH vector_results AS (
--     SELECT chunk_id, ROW_NUMBER() OVER (ORDER BY distance) as rank
--     FROM tax_law_vectors
--     WHERE embedding MATCH ?
--     ORDER BY distance
--     LIMIT 20
-- ),
-- fts_results AS (
--     SELECT m.chunk_id, ROW_NUMBER() OVER (ORDER BY bm25(tax_law_fts)) as rank
--     FROM tax_law_fts f
--     JOIN tax_law_fts_map m ON f.rowid = m.fts_rowid
--     WHERE tax_law_fts MATCH ?
--     LIMIT 20
-- )
-- SELECT
--     COALESCE(v.chunk_id, f.chunk_id) as chunk_id,
--     COALESCE(1.0 / (60 + v.rank), 0) + COALESCE(1.0 / (60 + f.rank), 0) as rrf_score
-- FROM vector_results v
-- FULL OUTER JOIN fts_results f ON v.chunk_id = f.chunk_id
-- ORDER BY rrf_score DESC
-- LIMIT 10;
