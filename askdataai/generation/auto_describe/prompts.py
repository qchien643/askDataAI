"""
Description Prompts — All prompt templates for XiYan pipeline.

Centralized prompt definitions for:
- Phase 1a: Style guide extraction
- Phase 1b: Database understanding
- Phase 3: Column type classification (batch)
- Phase 4: Table-level agent system prompt
"""

# ═══════════════════════════════════════════════════════════════
# Phase 1a — Style Guide Extraction
# ═══════════════════════════════════════════════════════════════

STYLE_GUIDE_PROMPT = """Analyze these existing column descriptions and extract the writing style conventions.

EXISTING DESCRIPTIONS:
{descriptions}

Extract and return a JSON object:
{{
    "language": "EN or VI or mixed",
    "format_patterns": [
        "pattern description"
    ],
    "enum_format": "how enum values are listed (e.g., 'Value1 = Label1, Value2 = Label2')",
    "measure_format": "how monetary/numeric columns are described (e.g., 'Amount in USD')",
    "fk_format": "how foreign keys are described (e.g., 'FK to <table>')",
    "typical_length": "short (5-15 words) | medium (15-30 words) | long (30+ words)",
    "examples": [
        "3 best example descriptions that represent the style"
    ]
}}"""


# ═══════════════════════════════════════════════════════════════
# Phase 1b — Database Understanding
# ═══════════════════════════════════════════════════════════════

DB_UNDERSTANDING_PROMPT = """Analyze this database schema and provide a domain understanding summary.

DATABASE SCHEMA:
{schema_ddl}

Return a JSON object:
{{
    "domain": "business domain (e.g., e-commerce, HR, finance)",
    "key_entities": ["list of main business entities"],
    "naming_convention": "camelCase | snake_case | PascalCase | mixed",
    "common_prefixes": ["Dim", "Fact", "tbl", etc.],
    "fact_tables": ["list of fact/transaction tables"],
    "dimension_tables": ["list of dimension/lookup tables"],
    "notes": "any other observations about the schema design"
}}"""


# ═══════════════════════════════════════════════════════════════
# Phase 3 — Batch Column Classification
# ═══════════════════════════════════════════════════════════════

CLASSIFY_PROMPT = """Classify each column into exactly one category based on its name, type, and context.

CATEGORIES:
- ENUM: Categorical/status column with a small set of distinct values
- MEASURE: Numeric measurement (price, amount, quantity, rate)
- CODE: Identifier/code column (alternate keys, ISO codes, SKUs)
- TEXT: Free-text or descriptive column (names, addresses, comments)
- DATE: Date/time column
- FK: Foreign key reference to another table
- BOOL: Boolean/flag column

COLUMNS TO CLASSIFY:
{columns_json}

TABLE CONTEXT:
- Table: {table_name}
- Primary Key: {primary_key}
- Known Relationships: {relationships}

Return JSON:
{{
    "classifications": [
        {{"column": "<name>", "category": "<CATEGORY>", "confidence": 0.0-1.0, "reason": "<brief reason>"}}
    ]
}}"""


# ═══════════════════════════════════════════════════════════════
# Phase 4 — Table Agent System Prompt
# ═══════════════════════════════════════════════════════════════

TABLE_AGENT_SYSTEM = """You are a database metadata specialist. Your task is to generate high-quality, accurate descriptions for database columns.

## CONTEXT
- Database domain: {domain}
- Writing language: **English ONLY**
- You are describing columns in table "{table_name}" ({table_description})

## STYLE GUIDE (extracted from existing descriptions in this database)
{style_guide}

## FORMATTING RULES

### Description format — CRITICAL
The "description" field must contain ONLY the description text itself.
Do **NOT** include column name, table name, data type, or any prefix/wrapper.

GOOD style (description text only):
{style_examples}

BAD style (DO NOT output like these — never include column names or types):
{anti_prefix_examples}

### Content rules
1. **English only**: Write all descriptions in English.
2. **Match existing style**: Follow the format, length, and conventions from the style guide above. Your descriptions should look like they were written by the same person who wrote the existing descriptions.
3. **Use evidence**: Call get_column_stats to see real data before writing. Don't guess.
4. **Learn from examples**: Call search_similar_descriptions to find how similar columns in this database were already described — then follow that pattern.
5. **Enum/code columns**: List ALL distinct values with their labels if ≤15 values. Use the enum_format from the style guide.
6. **Measure/money columns**: Include the unit if inferable from data or context (e.g., currency, percentage, days).
7. **FK columns**: State which table the key references, using the fk_format from the style guide.
8. **Calculated columns**: Include the formula if derivable from column relationships.
9. **Never fabricate**: Only mention values verified via get_column_stats.

## OUTPUT FORMAT
After gathering evidence, respond with a JSON object:
{{
    "descriptions": {{
        "<column_name>": {{
            "description": "<description text only — no column name, no type, no brackets>",
            "enum_values": ["<val1>", "<val2>"] or [],
            "category": "<ENUM|MEASURE|CODE|TEXT|DATE|FK|BOOL>",
            "confidence": 0.0-1.0
        }}
    }}
}}"""


TABLE_AGENT_USER = """Generate descriptions for these columns in table "{table_name}":

COLUMNS NEEDING DESCRIPTIONS:
{columns_info}

COLUMN TYPE HINTS (from automated classification):
{classifications}

EXISTING TABLE CONTEXT:
- Table description: {table_description}
- Primary key: {primary_key}
- Already-described columns in this table: {existing_described}

REMINDERS:
- Output ONLY the description text in the "description" field. No column names, no data types, no brackets.
- Include units for monetary/measurement columns if inferable.
- For enum/code columns, list values with human-readable labels (e.g., "code = meaning").
- Match the writing style from the style guide and existing descriptions in this database.

Use your tools (search_similar_descriptions, get_column_stats, get_table_relationships) to gather evidence, then produce the JSON."""


