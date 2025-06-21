from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "sample_model" RENAME TO "samplemodel";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "samplemodel" RENAME TO "sample_model";"""
