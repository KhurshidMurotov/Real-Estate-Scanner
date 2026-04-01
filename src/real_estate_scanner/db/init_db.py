from __future__ import annotations

from sqlalchemy import text

from real_estate_scanner.db.models import Base
from real_estate_scanner.db.session import engine


async def init_db() -> None:
    # Creates tables on startup. For production you should replace this with Alembic migrations.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Best-effort schema evolution for local runs (since we currently use create_all).
        # If ads.image_url column is missing, add it.
        await conn.execute(
            text("ALTER TABLE ads ADD COLUMN IF NOT EXISTS image_url TEXT")
        )
        # New columns for valuation support
        await conn.execute(
            text("ALTER TABLE ads ADD COLUMN IF NOT EXISTS ad_type VARCHAR(16) NOT NULL DEFAULT 'sale'")
        )
        await conn.execute(
            text("ALTER TABLE ads ADD COLUMN IF NOT EXISTS area NUMERIC(12,2)")
        )
        await conn.execute(
            text("ALTER TABLE ads ADD COLUMN IF NOT EXISTS rooms BIGINT")
        )
        await conn.execute(
            text("ALTER TABLE ads ADD COLUMN IF NOT EXISTS floor BIGINT")
        )
        await conn.execute(
            text("ALTER TABLE ads ADD COLUMN IF NOT EXISTS total_floors BIGINT")
        )
        await conn.execute(
            text("ALTER TABLE ads ADD COLUMN IF NOT EXISTS district VARCHAR(128)")
        )
        await conn.execute(
            text("ALTER TABLE ads ADD COLUMN IF NOT EXISTS city VARCHAR(128)")
        )
        await conn.execute(
            text("ALTER TABLE ads ADD COLUMN IF NOT EXISTS description TEXT")
        )
        await conn.execute(
            text("ALTER TABLE ads ADD COLUMN IF NOT EXISTS raw_data JSONB NOT NULL DEFAULT '{}'::jsonb")
        )
        # Add indexes for valuation queries
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_ads_ad_type ON ads(ad_type)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_ads_district ON ads(district)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_ads_rooms ON ads(rooms)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_ads_area ON ads(area)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_ads_timestamp ON ads(timestamp)")
        )
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_ads_valuation ON ads(ad_type, district, rooms, area, timestamp)")
        )
        await conn.execute(
            text("ALTER TABLE filters ADD COLUMN IF NOT EXISTS cities JSONB NOT NULL DEFAULT '[]'::jsonb")
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'filters'
                          AND column_name = 'cities'
                          AND data_type <> 'jsonb'
                    ) THEN
                        ALTER TABLE filters
                        ALTER COLUMN cities TYPE JSONB
                        USING CASE
                            WHEN cities IS NULL THEN '[]'::jsonb
                            ELSE to_jsonb(cities)
                        END;
                    END IF;
                END
                $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'filters'
                          AND column_name = 'rooms'
                          AND data_type <> 'jsonb'
                    ) THEN
                        ALTER TABLE filters
                        ALTER COLUMN rooms TYPE JSONB
                        USING CASE
                            WHEN rooms IS NULL THEN '[]'::jsonb
                            ELSE to_jsonb(ARRAY[rooms])
                        END;
                    END IF;
                END
                $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'filters'
                          AND column_name = 'city'
                    ) THEN
                        UPDATE filters
                        SET cities = CASE
                            WHEN city IS NULL OR city = '' THEN '[]'::jsonb
                            ELSE to_jsonb(ARRAY[city])
                        END
                        WHERE cities = '[]'::jsonb;
                    END IF;
                END
                $$;
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE filters
                ALTER COLUMN cities SET DEFAULT '[]'::jsonb
                """
            )
        )
        await conn.execute(
            text(
                """
                ALTER TABLE filters
                ALTER COLUMN rooms SET DEFAULT '[]'::jsonb
                """
            )
        )
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sale_broadcast_states (
                    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    is_active BOOLEAN NOT NULL DEFAULT FALSE,
                    started_at TIMESTAMPTZ NULL,
                    window_start TIMESTAMPTZ NULL,
                    window_end TIMESTAMPTZ NULL,
                    last_batch_at TIMESTAMPTZ NULL,
                    total_found BIGINT NOT NULL DEFAULT 0,
                    pending_ads JSONB NOT NULL DEFAULT '[]'::jsonb,
                    sent_olx_ids JSONB NOT NULL DEFAULT '[]'::jsonb
                )
                """
            )
        )

