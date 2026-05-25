import asyncio
import json
from sqlalchemy import text
from backend.models.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as s:
        shop_col = "店铺ID"
        ym_col = "年月"
        q = text(f"""
INSERT INTO a_class.operating_costs
  (\"{shop_col}\", \"{ym_col}\", \"租金\", \"营销费用\", \"水电费\", \"AI Token费用\", \"其他成本\", \"成本合计\", \"备注\", \"附件\", \"创建时间\", \"更新时间\")
VALUES
  (:shop_id,:year_month,:rent,:marketing_fee,:utilities,:ai_token_cost,:other_costs,:total_cost,:note,:attachments::jsonb,NOW(),NOW())
ON CONFLICT (\"{shop_col}\", \"{ym_col}\")
DO UPDATE SET
  \"租金\"=EXCLUDED.\"租金\",
  \"营销费用\"=EXCLUDED.\"营销费用\",
  \"水电费\"=EXCLUDED.\"水电费\",
  \"AI Token费用\"=EXCLUDED.\"AI Token费用\",
  \"其他成本\"=EXCLUDED.\"其他成本\",
  \"成本合计\"=EXCLUDED.\"成本合计\",
  \"备注\"=EXCLUDED.\"备注\",
  \"附件\"=EXCLUDED.\"附件\",
  \"更新时间\"=NOW()
RETURNING id
""")
        payload={
            'shop_id':'eternalblossom.sg',
            'year_month':'2026-05',
            'rent':0,
            'marketing_fee':111,
            'utilities':0,
            'ai_token_cost':0,
            'other_costs':0,
            'total_cost':111,
            'note':'debug',
            'attachments': json.dumps([]),
        }
        r = await s.execute(q,payload)
        row=r.fetchone()
        await s.commit()
        print('OK', row[0] if row else None)

asyncio.run(main())
