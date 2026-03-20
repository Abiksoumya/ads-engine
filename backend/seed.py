import asyncio
import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

from app.db.database import AsyncSessionFactory
from app.models.user import Role, RoleEnum
from app.models.subscription import SubscriptionPlan, PlanEnum

async def seed():
    async with AsyncSessionFactory() as db:
        # Create roles
        for role_name in RoleEnum:
            role = Role(name=role_name, description=f"{role_name.value} role")
            db.add(role)

        # Create subscription plans
        plans = [
            SubscriptionPlan(name=PlanEnum.FREE,    display_name="Free",    price_monthly=0,    price_yearly=0,    campaigns_per_month=3,   team_seats=1, platforms_allowed=0),
            SubscriptionPlan(name=PlanEnum.STARTER, display_name="Starter", price_monthly=49,   price_yearly=470,  campaigns_per_month=20,  team_seats=1, platforms_allowed=2),
            SubscriptionPlan(name=PlanEnum.PRO,     display_name="Pro",     price_monthly=99,   price_yearly=950,  campaigns_per_month=-1,  team_seats=3, platforms_allowed=5),
            SubscriptionPlan(name=PlanEnum.AGENCY,  display_name="Agency",  price_monthly=299,  price_yearly=2870, campaigns_per_month=-1,  team_seats=10, platforms_allowed=5, white_label=True, api_access=True),
        ]
        for plan in plans:
            db.add(plan)

        await db.commit()
        print("Seed complete — roles and plans created")

asyncio.run(seed())