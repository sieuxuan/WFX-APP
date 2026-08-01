-- WFX Smart shared data schema for PostgreSQL.
-- Run once on a dedicated database (recommended name: wfx_shared).

CREATE SCHEMA IF NOT EXISTS wfx_sync;

CREATE TABLE IF NOT EXISTS wfx_sync.article_list (
    company_id      text        NOT NULL,
    division_key    text        NOT NULL,
    article_code    text        NOT NULL,
    article_name    text        NOT NULL DEFAULT '',
    buyer_reference text        NOT NULL DEFAULT '',
    synced_at       timestamptz NOT NULL,
    PRIMARY KEY (company_id, division_key, article_code, buyer_reference)
);

CREATE INDEX IF NOT EXISTS article_list_code_idx
    ON wfx_sync.article_list (company_id, division_key, article_code);

CREATE INDEX IF NOT EXISTS article_list_buyer_reference_idx
    ON wfx_sync.article_list (company_id, division_key, buyer_reference);

CREATE TABLE IF NOT EXISTS wfx_sync.style_options (
    company_id    text        NOT NULL,
    division_key  text        NOT NULL,
    material_type text        NOT NULL DEFAULT '',
    field_name    text        NOT NULL,
    option_value  text        NOT NULL,
    option_label  text        NOT NULL DEFAULT '',
    synced_at     timestamptz NOT NULL,
    PRIMARY KEY (
        company_id,
        division_key,
        material_type,
        field_name,
        option_value
    )
);

CREATE INDEX IF NOT EXISTS style_options_lookup_idx
    ON wfx_sync.style_options (
        company_id,
        division_key,
        field_name,
        material_type
    );

CREATE TABLE IF NOT EXISTS wfx_sync.style_subcategories (
    company_id    text        NOT NULL,
    division_key  text        NOT NULL,
    material_type text        NOT NULL DEFAULT '',
    product_group text        NOT NULL,
    sub_category  text        NOT NULL,
    synced_at     timestamptz NOT NULL,
    PRIMARY KEY (
        company_id,
        division_key,
        material_type,
        product_group,
        sub_category
    )
);

CREATE INDEX IF NOT EXISTS style_subcategories_lookup_idx
    ON wfx_sync.style_subcategories (
        company_id,
        division_key,
        material_type,
        product_group
    );

CREATE TABLE IF NOT EXISTS wfx_sync.sync_state (
    company_id         text        NOT NULL,
    division_key       text        NOT NULL,
    version            text        NOT NULL,
    article_count      integer     NOT NULL DEFAULT 0,
    style_option_count integer     NOT NULL DEFAULT 0,
    subcategory_count  integer     NOT NULL DEFAULT 0,
    published_at       timestamptz NOT NULL,
    PRIMARY KEY (company_id, division_key)
);

-- Atomically replaces the complete snapshot for one Company + Division.
CREATE OR REPLACE FUNCTION wfx_sync.publish_bundle(
    p_company_id text,
    p_division_key text,
    p_version text,
    p_articles jsonb,
    p_style_options jsonb,
    p_style_subcategories jsonb
) RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_now timestamptz := clock_timestamp();
    v_article_count integer := 0;
    v_style_option_count integer := 0;
    v_subcategory_count integer := 0;
BEGIN
    IF btrim(COALESCE(p_company_id, '')) = '' THEN
        RAISE EXCEPTION 'company_id is required';
    END IF;
    IF btrim(COALESCE(p_division_key, '')) = '' THEN
        RAISE EXCEPTION 'division_key is required';
    END IF;
    IF btrim(COALESCE(p_version, '')) = '' THEN
        RAISE EXCEPTION 'version is required';
    END IF;
    IF jsonb_typeof(COALESCE(p_articles, '[]'::jsonb)) <> 'array'
       OR jsonb_typeof(COALESCE(p_style_options, '[]'::jsonb)) <> 'array'
       OR jsonb_typeof(COALESCE(p_style_subcategories, '[]'::jsonb)) <> 'array'
    THEN
        RAISE EXCEPTION 'all datasets must be JSON arrays';
    END IF;

    -- Prevent two Admin publishes for the same scope from overlapping.
    PERFORM pg_advisory_xact_lock(
        hashtext(btrim(p_company_id) || ':' || btrim(p_division_key))
    );

    DELETE FROM wfx_sync.article_list
    WHERE company_id = btrim(p_company_id)
      AND division_key = btrim(p_division_key);

    WITH source AS (
        SELECT
            btrim(COALESCE(item.article_code, '')) AS article_code,
            btrim(COALESCE(item.article_name, '')) AS article_name,
            btrim(COALESCE(item.buyer_reference, '')) AS buyer_reference
        FROM jsonb_to_recordset(COALESCE(p_articles, '[]'::jsonb)) AS item(
            article_code text,
            article_name text,
            buyer_reference text
        )
    ), deduplicated AS (
        SELECT
            article_code,
            buyer_reference,
            max(article_name) AS article_name
        FROM source
        WHERE article_code <> ''
        GROUP BY article_code, buyer_reference
    )
    INSERT INTO wfx_sync.article_list (
        company_id,
        division_key,
        article_code,
        article_name,
        buyer_reference,
        synced_at
    )
    SELECT
        btrim(p_company_id),
        btrim(p_division_key),
        article_code,
        article_name,
        buyer_reference,
        v_now
    FROM deduplicated;
    GET DIAGNOSTICS v_article_count = ROW_COUNT;

    DELETE FROM wfx_sync.style_options
    WHERE company_id = btrim(p_company_id)
      AND division_key = btrim(p_division_key);

    WITH source AS (
        SELECT
            upper(btrim(COALESCE(item.material_type, ''))) AS material_type,
            lower(btrim(COALESCE(item.field_name, ''))) AS field_name,
            btrim(COALESCE(item.option_value, '')) AS option_value,
            btrim(COALESCE(item.option_label, item.option_value, '')) AS option_label
        FROM jsonb_to_recordset(COALESCE(p_style_options, '[]'::jsonb)) AS item(
            material_type text,
            field_name text,
            option_value text,
            option_label text
        )
    ), deduplicated AS (
        SELECT
            material_type,
            field_name,
            option_value,
            max(option_label) AS option_label
        FROM source
        WHERE field_name <> '' AND option_value <> ''
        GROUP BY material_type, field_name, option_value
    )
    INSERT INTO wfx_sync.style_options (
        company_id,
        division_key,
        material_type,
        field_name,
        option_value,
        option_label,
        synced_at
    )
    SELECT
        btrim(p_company_id),
        btrim(p_division_key),
        material_type,
        field_name,
        option_value,
        option_label,
        v_now
    FROM deduplicated;
    GET DIAGNOSTICS v_style_option_count = ROW_COUNT;

    DELETE FROM wfx_sync.style_subcategories
    WHERE company_id = btrim(p_company_id)
      AND division_key = btrim(p_division_key);

    WITH source AS (
        SELECT
            upper(btrim(COALESCE(item.material_type, ''))) AS material_type,
            btrim(COALESCE(item.product_group, '')) AS product_group,
            btrim(COALESCE(item.sub_category, '')) AS sub_category
        FROM jsonb_to_recordset(
            COALESCE(p_style_subcategories, '[]'::jsonb)
        ) AS item(
            material_type text,
            product_group text,
            sub_category text
        )
    )
    INSERT INTO wfx_sync.style_subcategories (
        company_id,
        division_key,
        material_type,
        product_group,
        sub_category,
        synced_at
    )
    SELECT DISTINCT
        btrim(p_company_id),
        btrim(p_division_key),
        material_type,
        product_group,
        sub_category,
        v_now
    FROM source
    WHERE product_group <> '' AND sub_category <> '';
    GET DIAGNOSTICS v_subcategory_count = ROW_COUNT;

    INSERT INTO wfx_sync.sync_state (
        company_id,
        division_key,
        version,
        article_count,
        style_option_count,
        subcategory_count,
        published_at
    ) VALUES (
        btrim(p_company_id),
        btrim(p_division_key),
        btrim(p_version),
        v_article_count,
        v_style_option_count,
        v_subcategory_count,
        v_now
    )
    ON CONFLICT (company_id, division_key) DO UPDATE SET
        version = EXCLUDED.version,
        article_count = EXCLUDED.article_count,
        style_option_count = EXCLUDED.style_option_count,
        subcategory_count = EXCLUDED.subcategory_count,
        published_at = EXCLUDED.published_at;

    RETURN jsonb_build_object(
        'ok', true,
        'version', btrim(p_version),
        'published_at', v_now,
        'counts', jsonb_build_object(
            'articles', v_article_count,
            'style_options', v_style_option_count,
            'style_subcategories', v_subcategory_count
        )
    );
END;
$$;

-- Returns metadata only when client_version is current, otherwise the full bundle.
CREATE OR REPLACE FUNCTION wfx_sync.get_latest_bundle(
    p_company_id text,
    p_division_key text,
    p_client_version text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_state wfx_sync.sync_state%ROWTYPE;
BEGIN
    SELECT * INTO v_state
    FROM wfx_sync.sync_state
    WHERE company_id = btrim(COALESCE(p_company_id, ''))
      AND division_key = btrim(COALESCE(p_division_key, ''));

    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'ok', false,
            'code', 'SNAPSHOT_NOT_FOUND',
            'message', 'Chưa có dữ liệu cho Company và Division này.'
        );
    END IF;

    IF NULLIF(btrim(COALESCE(p_client_version, '')), '') = v_state.version THEN
        RETURN jsonb_build_object(
            'ok', true,
            'not_modified', true,
            'version', v_state.version,
            'published_at', v_state.published_at,
            'counts', jsonb_build_object(
                'articles', v_state.article_count,
                'style_options', v_state.style_option_count,
                'style_subcategories', v_state.subcategory_count
            )
        );
    END IF;

    RETURN jsonb_build_object(
        'ok', true,
        'not_modified', false,
        'version', v_state.version,
        'published_at', v_state.published_at,
        'counts', jsonb_build_object(
            'articles', v_state.article_count,
            'style_options', v_state.style_option_count,
            'style_subcategories', v_state.subcategory_count
        ),
        'articles', COALESCE((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'article_code', article_code,
                    'article_name', article_name,
                    'buyer_reference', buyer_reference
                )
                ORDER BY article_code, buyer_reference
            )
            FROM wfx_sync.article_list
            WHERE company_id = v_state.company_id
              AND division_key = v_state.division_key
        ), '[]'::jsonb),
        'style_options', COALESCE((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'material_type', material_type,
                    'field_name', field_name,
                    'option_value', option_value,
                    'option_label', option_label
                )
                ORDER BY field_name, material_type, option_label
            )
            FROM wfx_sync.style_options
            WHERE company_id = v_state.company_id
              AND division_key = v_state.division_key
        ), '[]'::jsonb),
        'style_subcategories', COALESCE((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'material_type', material_type,
                    'product_group', product_group,
                    'sub_category', sub_category
                )
                ORDER BY material_type, product_group, sub_category
            )
            FROM wfx_sync.style_subcategories
            WHERE company_id = v_state.company_id
              AND division_key = v_state.division_key
        ), '[]'::jsonb)
    );
END;
$$;

-- If n8n uses a restricted PostgreSQL role, replace wfx_n8n with its real name:
-- GRANT USAGE ON SCHEMA wfx_sync TO wfx_n8n;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA wfx_sync TO wfx_n8n;
-- GRANT EXECUTE ON FUNCTION wfx_sync.publish_bundle(text, text, text, jsonb, jsonb, jsonb) TO wfx_n8n;
-- GRANT EXECUTE ON FUNCTION wfx_sync.get_latest_bundle(text, text, text) TO wfx_n8n;
