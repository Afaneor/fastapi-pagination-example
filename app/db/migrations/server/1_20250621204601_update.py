from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "samplemodel" RENAME TO "sample_model";
        ALTER TABLE "sample_model" ADD "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE "sample_model" ADD "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS "idx_sample_mode_name_b64c0e" ON "sample_model" ("name", "id");
        CREATE INDEX IF NOT EXISTS "idx_sample_mode_created_333297" ON "sample_model" ("created_at", "id");"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP INDEX IF EXISTS "idx_sample_mode_created_333297";
        DROP INDEX IF EXISTS "idx_sample_mode_name_b64c0e";
        ALTER TABLE "sample_model" RENAME TO "samplemodel";
        ALTER TABLE "sample_model" DROP COLUMN "created_at";
        ALTER TABLE "sample_model" DROP COLUMN "updated_at";"""
