"""Tax law document ingestion for German tax RAG system.

Handles parsing, chunking, embedding, and indexing of German tax law
documents (EStG, UStG, AO, BMF letters, BFH rulings).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import struct
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import aiosqlite

from src.llm.embeddings import (
    EMBEDDING_DIM,
    EmbeddingService,
    GermanTaxTextProcessor,
    get_embedding_service,
)
from src.llm.exceptions import IngestionError

logger = logging.getLogger(__name__)

# Chunking parameters
MIN_CHUNK_SIZE = 50  # Minimum characters per chunk
MAX_CHUNK_SIZE = 1000  # Maximum characters per chunk
TARGET_CHUNK_SIZE = 300  # Target chunk size
CHUNK_OVERLAP = 50  # Character overlap between chunks


class SourceType(StrEnum):
    """Types of tax law sources."""

    ESTG = "estg"  # Einkommensteuergesetz
    USTG = "ustg"  # Umsatzsteuergesetz
    AO = "ao"  # Abgabenordnung
    BMF = "bmf"  # BMF-Schreiben
    BFH = "bfh"  # BFH-Urteile
    RICHTLINIE = "richtlinie"  # Steuerrichtlinien


@dataclass
class ParsedSection:
    """Parsed section from tax law document."""

    citation: str  # e.g., "§ 7 Abs. 1 EStG"
    title: str  # Section title
    content: str  # Full section text
    section_number: str | None = None  # e.g., "7" for § 7
    hierarchy_level: int = 1  # 1=§, 2=Abs, 3=Satz
    parent_citation: str | None = None
    effective_date: date | None = None
    last_modified: date | None = None


@dataclass
class ParsedChunk:
    """Parsed chunk from a section."""

    content: str
    citation: str  # Full citation with position
    chunk_index: int  # Position within section
    char_start: int
    char_end: int
    token_count: int | None = None


@dataclass
class IngestionResult:
    """Result of document ingestion."""

    source_id: int
    source_type: SourceType
    title: str
    sections_created: int
    chunks_created: int
    embeddings_created: int
    fts_indexed: int
    processing_time_ms: float
    errors: list[str] = field(default_factory=list)


class GermanTaxLawParser:
    """Parser for German tax law documents.

    Handles hierarchical structure:
    - Gesetz (Law)
      - Teil (Part)
        - Abschnitt (Section)
          - § (Paragraph)
            - Absatz (Abs.)
              - Satz (Sentence)
    """

    # Pattern for section headers: § 7, § 7a, etc.
    SECTION_PATTERN = re.compile(
        r"^§\s*(\d+[a-z]?)\s+(.+?)$",
        re.MULTILINE,
    )

    # Pattern for subsections: (1), (2), Abs. 1, etc.
    ABSATZ_PATTERN = re.compile(
        r"^\((\d+)\)\s*(.+)",
        re.MULTILINE | re.DOTALL,
    )

    # Pattern for BMF citations: BMF vom 26.02.2021, Tz. 1
    BMF_PATTERN = re.compile(
        r"(?:BMF\s+vom\s+)?(\d{1,2})\.(\d{1,2})\.(\d{4})",
    )

    # Pattern for BFH citations: BFH-Urteil vom 15.03.2020 - IX R 12/19
    BFH_PATTERN = re.compile(
        r"BFH[-\s](?:Urteil|Beschluss)\s+vom\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\s*[-–]\s*([IVX]+\s+[A-Z]+\s+\d+/\d+)",
    )

    def __init__(self, source_type: SourceType):
        """Initialize parser for specific source type.

        Args:
            source_type: Type of tax law source
        """
        self.source_type = source_type
        self._preprocessor = GermanTaxTextProcessor()

    def parse(self, text: str, title: str) -> list[ParsedSection]:
        """Parse tax law document into sections.

        Args:
            text: Full document text
            title: Document title

        Returns:
            List of parsed sections
        """
        if self.source_type in (SourceType.ESTG, SourceType.USTG, SourceType.AO):
            return self._parse_law(text, title)
        elif self.source_type == SourceType.BMF:
            return self._parse_bmf(text, title)
        elif self.source_type == SourceType.BFH:
            return self._parse_bfh(text, title)
        else:
            return self._parse_generic(text, title)

    def _parse_law(self, text: str, title: str) -> list[ParsedSection]:
        """Parse a law document (EStG, UStG, AO).

        Args:
            text: Full law text
            title: Law title

        Returns:
            List of parsed sections
        """
        sections = []
        law_abbrev = self.source_type.value.upper()

        # Find all section headers
        matches = list(self.SECTION_PATTERN.finditer(text))

        for i, match in enumerate(matches):
            section_num = match.group(1)
            section_title = match.group(2).strip()

            # Get content until next section
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()

            citation = f"§ {section_num} {law_abbrev}"

            sections.append(
                ParsedSection(
                    citation=citation,
                    title=section_title,
                    content=content,
                    section_number=section_num,
                    hierarchy_level=1,
                )
            )

            # Parse subsections (Absätze)
            subsections = self._parse_absaetze(
                content, citation, section_num, law_abbrev
            )
            sections.extend(subsections)

        return sections

    def _parse_absaetze(
        self,
        content: str,
        parent_citation: str,
        section_num: str,
        law_abbrev: str,
    ) -> list[ParsedSection]:
        """Parse subsections (Absätze) from section content.

        Args:
            content: Section content
            parent_citation: Parent section citation
            section_num: Section number
            law_abbrev: Law abbreviation

        Returns:
            List of parsed subsections
        """
        subsections = []

        for match in self.ABSATZ_PATTERN.finditer(content):
            abs_num = match.group(1)
            abs_content = match.group(2).strip()

            # Find end of this Absatz (next Absatz or end of content)
            next_match = self.ABSATZ_PATTERN.search(content, match.end())
            if next_match:
                abs_content = content[match.start() : next_match.start()].strip()

            citation = f"§ {section_num} Abs. {abs_num} {law_abbrev}"

            subsections.append(
                ParsedSection(
                    citation=citation,
                    title=f"Absatz {abs_num}",
                    content=abs_content,
                    section_number=section_num,
                    hierarchy_level=2,
                    parent_citation=parent_citation,
                )
            )

        return subsections

    def _parse_bmf(self, text: str, title: str) -> list[ParsedSection]:
        """Parse BMF-Schreiben (Ministry of Finance letters).

        Args:
            text: BMF document text
            title: Document title

        Returns:
            List of parsed sections
        """
        sections = []

        # Extract date from title or text
        effective_date = None
        date_match = self.BMF_PATTERN.search(title) or self.BMF_PATTERN.search(text)
        if date_match:
            try:
                effective_date = date(
                    int(date_match.group(3)),
                    int(date_match.group(2)),
                    int(date_match.group(1)),
                )
            except ValueError:
                pass

        # Parse numbered sections (Tz. 1, 2, 3, etc.)
        tz_pattern = re.compile(r"^(?:Tz\.\s*)?(\d+)\.\s*(.+?)(?=^(?:Tz\.\s*)?\d+\.|$)", re.MULTILINE | re.DOTALL)

        for match in tz_pattern.finditer(text):
            tz_num = match.group(1)
            content = match.group(2).strip()

            citation = f"BMF {effective_date.strftime('%Y-%m-%d') if effective_date else 'o.D.'} Tz. {tz_num}"

            sections.append(
                ParsedSection(
                    citation=citation,
                    title=f"Textziffer {tz_num}",
                    content=content,
                    section_number=tz_num,
                    hierarchy_level=1,
                    effective_date=effective_date,
                )
            )

        # If no Tz. found, treat as single section
        if not sections:
            citation = f"BMF {effective_date.strftime('%Y-%m-%d') if effective_date else 'o.D.'}"
            sections.append(
                ParsedSection(
                    citation=citation,
                    title=title,
                    content=text,
                    hierarchy_level=1,
                    effective_date=effective_date,
                )
            )

        return sections

    def _parse_bfh(self, text: str, title: str) -> list[ParsedSection]:
        """Parse BFH-Urteil (Federal Fiscal Court ruling).

        Args:
            text: BFH document text
            title: Document title

        Returns:
            List of parsed sections
        """
        sections = []

        # Extract case reference and date
        case_ref = None
        ruling_date = None

        bfh_match = self.BFH_PATTERN.search(title) or self.BFH_PATTERN.search(text)
        if bfh_match:
            try:
                ruling_date = date(
                    int(bfh_match.group(3)),
                    int(bfh_match.group(2)),
                    int(bfh_match.group(1)),
                )
                case_ref = bfh_match.group(4)
            except ValueError:
                pass

        # Parse numbered sections (Rn. 1, 2, 3 or Rz. 1, 2, 3)
        rn_pattern = re.compile(r"^(?:Rn\.|Rz\.)\s*(\d+)\s*(.+?)(?=^(?:Rn\.|Rz\.)\s*\d+|$)", re.MULTILINE | re.DOTALL)

        for match in rn_pattern.finditer(text):
            rn_num = match.group(1)
            content = match.group(2).strip()

            base_citation = f"BFH {ruling_date.strftime('%Y-%m-%d') if ruling_date else ''} {case_ref or ''}".strip()
            citation = f"{base_citation} Rn. {rn_num}"

            sections.append(
                ParsedSection(
                    citation=citation,
                    title=f"Randnummer {rn_num}",
                    content=content,
                    section_number=rn_num,
                    hierarchy_level=1,
                    effective_date=ruling_date,
                )
            )

        # If no Rn. found, treat as single section
        if not sections:
            base_citation = f"BFH {ruling_date.strftime('%Y-%m-%d') if ruling_date else ''} {case_ref or ''}".strip()
            sections.append(
                ParsedSection(
                    citation=base_citation or "BFH",
                    title=title,
                    content=text,
                    hierarchy_level=1,
                    effective_date=ruling_date,
                )
            )

        return sections

    def _parse_generic(self, text: str, title: str) -> list[ParsedSection]:
        """Parse generic document.

        Args:
            text: Document text
            title: Document title

        Returns:
            List of parsed sections
        """
        # Split by double newlines as paragraph separators
        paragraphs = re.split(r"\n\n+", text)

        sections = []
        for i, para in enumerate(paragraphs, 1):
            para = para.strip()
            if len(para) < MIN_CHUNK_SIZE:
                continue

            sections.append(
                ParsedSection(
                    citation=f"{title} §{i}",
                    title=f"Abschnitt {i}",
                    content=para,
                    section_number=str(i),
                    hierarchy_level=1,
                )
            )

        return sections

    def chunk_section(self, section: ParsedSection) -> list[ParsedChunk]:
        """Split section into smaller chunks for embedding.

        Uses semantic chunking that respects sentence boundaries.

        Args:
            section: Parsed section to chunk

        Returns:
            List of chunks
        """
        content = section.content
        if len(content) <= MAX_CHUNK_SIZE:
            return [
                ParsedChunk(
                    content=content,
                    citation=section.citation,
                    chunk_index=0,
                    char_start=0,
                    char_end=len(content),
                    token_count=len(content) // 4,  # Rough estimate
                )
            ]

        chunks = []
        sentences = self._split_sentences(content)

        current_chunk = ""
        chunk_start = 0
        chunk_index = 0

        for sentence in sentences:
            # If adding this sentence would exceed max size, finalize chunk
            if len(current_chunk) + len(sentence) > MAX_CHUNK_SIZE and current_chunk:
                chunks.append(
                    ParsedChunk(
                        content=current_chunk.strip(),
                        citation=f"{section.citation} [{chunk_index + 1}]",
                        chunk_index=chunk_index,
                        char_start=chunk_start,
                        char_end=chunk_start + len(current_chunk),
                        token_count=len(current_chunk) // 4,
                    )
                )
                chunk_index += 1

                # Start new chunk with overlap
                overlap_start = max(0, len(current_chunk) - CHUNK_OVERLAP)
                current_chunk = current_chunk[overlap_start:]
                chunk_start = chunk_start + overlap_start

            current_chunk += sentence

        # Add final chunk
        if current_chunk.strip():
            chunks.append(
                ParsedChunk(
                    content=current_chunk.strip(),
                    citation=f"{section.citation} [{chunk_index + 1}]" if chunk_index > 0 else section.citation,
                    chunk_index=chunk_index,
                    char_start=chunk_start,
                    char_end=chunk_start + len(current_chunk),
                    token_count=len(current_chunk) // 4,
                )
            )

        return chunks

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split text into sentences respecting German conventions.

        Args:
            text: Text to split

        Returns:
            List of sentences
        """
        # Pattern for sentence boundaries
        # Handles abbreviations like "Abs.", "Nr.", "z.B." etc.
        sentence_pattern = re.compile(
            r"(?<=[.!?])\s+(?=[A-ZÄÖÜ])|"  # Normal sentence end
            r"(?<=[.!?])\s*\n+",  # Sentence end at line break
            re.UNICODE,
        )

        sentences = sentence_pattern.split(text)

        # Clean up and filter
        return [s.strip() + " " for s in sentences if s.strip()]


class TaxLawIngestionService:
    """Service for ingesting tax law documents into RAG system.

    Handles:
    - Document parsing and chunking
    - Embedding generation
    - Vector storage (sqlite-vec)
    - FTS5 indexing
    - Category linking
    """

    def __init__(
        self,
        db_path: str,
        embedding_service: EmbeddingService | None = None,
    ):
        """Initialize ingestion service.

        Args:
            db_path: Path to SQLite database
            embedding_service: Embedding service (creates new if None)
        """
        self._db_path = db_path
        self._embedding_service = embedding_service or get_embedding_service()

    async def ingest_document(
        self,
        source_type: SourceType,
        title: str,
        content: str,
        source_url: str | None = None,
        version_date: date | None = None,
    ) -> IngestionResult:
        """Ingest a tax law document.

        Args:
            source_type: Type of source document
            title: Document title
            content: Full document text
            source_url: Optional source URL
            version_date: Document version date

        Returns:
            IngestionResult with stats

        Raises:
            IngestionError: If ingestion fails
        """
        start_time = datetime.now()
        errors: list[str] = []

        try:
            # Calculate checksum for change detection
            checksum = hashlib.sha256(content.encode()).hexdigest()

            async with aiosqlite.connect(self._db_path) as db:
                # Check if document already exists with same checksum
                existing = await self._check_existing(db, source_type, title, checksum)
                if existing:
                    logger.info(f"Document '{title}' unchanged, skipping")
                    return IngestionResult(
                        source_id=existing,
                        source_type=source_type,
                        title=title,
                        sections_created=0,
                        chunks_created=0,
                        embeddings_created=0,
                        fts_indexed=0,
                        processing_time_ms=0,
                    )

                # Create or update source record
                source_id = await self._upsert_source(
                    db, source_type, title, content, source_url, version_date, checksum
                )

                # Parse document into sections
                parser = GermanTaxLawParser(source_type)
                sections = parser.parse(content, title)

                sections_created = 0
                chunks_created = 0
                embeddings_created = 0
                fts_indexed = 0

                # Process each section
                for section in sections:
                    try:
                        # Create parent chunk
                        parent_id = await self._create_parent_chunk(
                            db, source_id, section
                        )
                        sections_created += 1

                        # Create child chunks
                        chunks = parser.chunk_section(section)
                        for chunk in chunks:
                            chunk_id = await self._create_child_chunk(
                                db, source_id, parent_id, chunk
                            )
                            chunks_created += 1

                            # Generate and store embedding
                            try:
                                embedding = await self._embedding_service.embed_text(
                                    chunk.content
                                )
                                await self._store_embedding(db, chunk_id, embedding)
                                embeddings_created += 1
                            except Exception as e:
                                errors.append(f"Embedding failed for chunk {chunk_id}: {e}")

                            # Index in FTS5
                            try:
                                await self._index_fts(
                                    db, chunk_id, chunk.citation, section.title, chunk.content
                                )
                                fts_indexed += 1
                            except Exception as e:
                                errors.append(f"FTS indexing failed for chunk {chunk_id}: {e}")

                    except Exception as e:
                        errors.append(f"Section '{section.citation}' failed: {e}")

                await db.commit()

        except Exception as e:
            raise IngestionError(str(e), title) from e

        processing_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        result = IngestionResult(
            source_id=source_id,
            source_type=source_type,
            title=title,
            sections_created=sections_created,
            chunks_created=chunks_created,
            embeddings_created=embeddings_created,
            fts_indexed=fts_indexed,
            processing_time_ms=processing_time_ms,
            errors=errors,
        )

        logger.info(
            f"Ingested '{title}': {sections_created} sections, "
            f"{chunks_created} chunks, {embeddings_created} embeddings in {processing_time_ms:.0f}ms"
        )

        return result

    async def _check_existing(
        self,
        db: aiosqlite.Connection,
        source_type: SourceType,
        title: str,
        checksum: str,
    ) -> int | None:
        """Check if document exists with same checksum.

        Args:
            db: Database connection
            source_type: Source type
            title: Document title
            checksum: Content checksum

        Returns:
            Source ID if exists unchanged, None otherwise
        """
        cursor = await db.execute(
            """
            SELECT id FROM tax_law_sources
            WHERE source_type = ? AND title = ? AND checksum = ?
            """,
            (source_type.value, title, checksum),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def _upsert_source(
        self,
        db: aiosqlite.Connection,
        source_type: SourceType,
        title: str,
        full_text: str,
        source_url: str | None,
        version_date: date | None,
        checksum: str,
    ) -> int:
        """Create or update source record.

        Args:
            db: Database connection
            source_type: Source type
            title: Document title
            full_text: Full document text
            source_url: Source URL
            version_date: Version date
            checksum: Content checksum

        Returns:
            Source ID
        """
        # Check if source exists
        cursor = await db.execute(
            """
            SELECT id FROM tax_law_sources
            WHERE source_type = ? AND title = ?
            """,
            (source_type.value, title),
        )
        existing = await cursor.fetchone()

        if existing:
            # Update existing
            source_id = existing[0]

            # Delete old chunks and embeddings
            await self._delete_source_data(db, source_id)

            # Update source record
            await db.execute(
                """
                UPDATE tax_law_sources
                SET full_text = ?, source_url = ?, version_date = ?,
                    checksum = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (full_text, source_url, version_date, checksum, source_id),
            )
        else:
            # Create new
            cursor = await db.execute(
                """
                INSERT INTO tax_law_sources (
                    source_type, title, full_text, source_url, version_date, checksum
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (source_type.value, title, full_text, source_url, version_date, checksum),
            )
            source_id = cursor.lastrowid or 0

        return source_id

    async def _delete_source_data(
        self,
        db: aiosqlite.Connection,
        source_id: int,
    ) -> None:
        """Delete existing chunks and embeddings for a source.

        Args:
            db: Database connection
            source_id: Source ID to delete data for
        """
        # Get chunk IDs for this source
        cursor = await db.execute(
            "SELECT id FROM tax_law_child_chunks WHERE source_id = ?",
            (source_id,),
        )
        chunk_ids = [row[0] async for row in cursor]

        if chunk_ids:
            placeholders = ", ".join("?" for _ in chunk_ids)

            # Delete embeddings
            await db.execute(
                f"DELETE FROM tax_law_vectors WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            )

            # Delete FTS entries
            await db.execute(
                f"""
                DELETE FROM tax_law_fts
                WHERE rowid IN (
                    SELECT fts_rowid FROM tax_law_fts_map
                    WHERE chunk_id IN ({placeholders})
                )
                """,
                chunk_ids,
            )
            await db.execute(
                f"DELETE FROM tax_law_fts_map WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            )

            # Delete category references
            await db.execute(
                f"DELETE FROM tax_law_references WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            )

        # Delete chunks
        await db.execute(
            "DELETE FROM tax_law_child_chunks WHERE source_id = ?",
            (source_id,),
        )
        await db.execute(
            "DELETE FROM tax_law_parent_chunks WHERE source_id = ?",
            (source_id,),
        )

    async def _create_parent_chunk(
        self,
        db: aiosqlite.Connection,
        source_id: int,
        section: ParsedSection,
    ) -> int:
        """Create parent chunk record.

        Args:
            db: Database connection
            source_id: Source ID
            section: Parsed section

        Returns:
            Parent chunk ID
        """
        cursor = await db.execute(
            """
            INSERT INTO tax_law_parent_chunks (
                source_id, citation, title, content, section_number,
                hierarchy_level, effective_date, last_modified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                section.citation,
                section.title,
                section.content,
                section.section_number,
                section.hierarchy_level,
                section.effective_date,
                section.last_modified,
            ),
        )
        return cursor.lastrowid or 0

    async def _create_child_chunk(
        self,
        db: aiosqlite.Connection,
        source_id: int,
        parent_id: int,
        chunk: ParsedChunk,
    ) -> int:
        """Create child chunk record.

        Args:
            db: Database connection
            source_id: Source ID
            parent_id: Parent chunk ID
            chunk: Parsed chunk

        Returns:
            Child chunk ID
        """
        cursor = await db.execute(
            """
            INSERT INTO tax_law_child_chunks (
                parent_chunk_id, source_id, citation, content,
                chunk_index, char_start, char_end, token_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parent_id,
                source_id,
                chunk.citation,
                chunk.content,
                chunk.chunk_index,
                chunk.char_start,
                chunk.char_end,
                chunk.token_count,
            ),
        )
        return cursor.lastrowid or 0

    async def _store_embedding(
        self,
        db: aiosqlite.Connection,
        chunk_id: int,
        embedding: Any,  # np.ndarray
    ) -> None:
        """Store embedding in sqlite-vec.

        Args:
            db: Database connection
            chunk_id: Chunk ID
            embedding: Embedding vector
        """
        import numpy as np

        # Serialize embedding to bytes
        embedding_bytes = struct.pack(
            f"<{EMBEDDING_DIM}f", *embedding.astype(np.float32)
        )

        await db.execute(
            "INSERT INTO tax_law_vectors (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, embedding_bytes),
        )

    async def _index_fts(
        self,
        db: aiosqlite.Connection,
        chunk_id: int,
        citation: str,
        title: str,
        content: str,
    ) -> None:
        """Index chunk in FTS5.

        Args:
            db: Database connection
            chunk_id: Chunk ID
            citation: Citation text
            title: Title text
            content: Content text
        """
        # Insert into FTS5
        cursor = await db.execute(
            "INSERT INTO tax_law_fts (citation, title, content) VALUES (?, ?, ?)",
            (citation, title, content),
        )
        fts_rowid = cursor.lastrowid

        # Create mapping
        await db.execute(
            "INSERT INTO tax_law_fts_map (fts_rowid, chunk_id) VALUES (?, ?)",
            (fts_rowid, chunk_id),
        )

    async def link_category(
        self,
        chunk_id: int,
        category: str,
        relevance_score: float = 1.0,
    ) -> None:
        """Link a chunk to an expense category.

        Args:
            chunk_id: Chunk ID
            category: Expense category
            relevance_score: Relevance score (0.0 to 1.0)
        """
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO tax_law_references (chunk_id, category, relevance_score)
                VALUES (?, ?, ?)
                """,
                (chunk_id, category, relevance_score),
            )
            await db.commit()

    async def ingest_from_file(
        self,
        file_path: Path,
        source_type: SourceType,
        title: str | None = None,
    ) -> IngestionResult:
        """Ingest document from file.

        Args:
            file_path: Path to document file
            source_type: Type of source
            title: Optional title (defaults to filename)

        Returns:
            IngestionResult

        Raises:
            IngestionError: If file cannot be read
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            raise IngestionError(f"Cannot read file: {e}", str(file_path)) from e

        doc_title = title or file_path.stem
        return await self.ingest_document(source_type, doc_title, content)

    async def ingest_batch(
        self,
        documents: list[tuple[SourceType, str, str]],
    ) -> list[IngestionResult]:
        """Ingest multiple documents.

        Args:
            documents: List of (source_type, title, content) tuples

        Returns:
            List of IngestionResult
        """
        results = []
        for source_type, title, content in documents:
            try:
                result = await self.ingest_document(source_type, title, content)
                results.append(result)
            except IngestionError as e:
                logger.error(f"Failed to ingest '{title}': {e}")
                results.append(
                    IngestionResult(
                        source_id=0,
                        source_type=source_type,
                        title=title,
                        sections_created=0,
                        chunks_created=0,
                        embeddings_created=0,
                        fts_indexed=0,
                        processing_time_ms=0,
                        errors=[str(e)],
                    )
                )

        return results

    async def get_ingestion_stats(self) -> dict[str, Any]:
        """Get ingestion statistics.

        Returns:
            Statistics dict
        """
        async with aiosqlite.connect(self._db_path) as db:
            # Count sources by type
            sources_by_type = {}
            cursor = await db.execute(
                """
                SELECT source_type, COUNT(*) as count
                FROM tax_law_sources
                GROUP BY source_type
                """
            )
            async for row in cursor:
                sources_by_type[row[0]] = row[1]

            # Total counts
            cursor = await db.execute("SELECT COUNT(*) FROM tax_law_sources")
            total_sources = (await cursor.fetchone())[0]

            cursor = await db.execute("SELECT COUNT(*) FROM tax_law_parent_chunks")
            total_sections = (await cursor.fetchone())[0]

            cursor = await db.execute("SELECT COUNT(*) FROM tax_law_child_chunks")
            total_chunks = (await cursor.fetchone())[0]

            cursor = await db.execute("SELECT COUNT(*) FROM tax_law_vectors")
            total_embeddings = (await cursor.fetchone())[0]

            return {
                "total_sources": total_sources,
                "total_sections": total_sections,
                "total_chunks": total_chunks,
                "total_embeddings": total_embeddings,
                "sources_by_type": sources_by_type,
            }


# =============================================================================
# Singleton Instance
# =============================================================================

_ingestion_service: TaxLawIngestionService | None = None


def get_ingestion_service(db_path: str | None = None) -> TaxLawIngestionService:
    """Get or create the ingestion service singleton.

    Args:
        db_path: Database path (required on first call)

    Returns:
        TaxLawIngestionService singleton instance
    """
    global _ingestion_service
    if _ingestion_service is None:
        if db_path is None:
            raise ValueError("db_path required for first service initialization")
        _ingestion_service = TaxLawIngestionService(db_path)
    return _ingestion_service
