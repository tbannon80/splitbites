import httpx
import asyncio

async def verify_endpoints():
    async with httpx.AsyncClient() as client:
        # 1. Test Health Check
        health_res = await client.get("http://localhost:8001/healthz")
        print(f"Health Check Status: {health_res.status_code}")
        print(f"Health Check Response: {health_res.json()}")

        # 2. Test Meal Plan Generation Route
        try:
            plan_res = await client.get("http://localhost:8001/api/meal-plans/generate")
            print(f"Meal Plan Generation Status: {plan_res.status_code}")
            print(f"Meal Plan Response: {plan_res.json()}")
        except Exception as e:
            print(f"Meal Plan Route Note: {e}")

if __name__ == "__main__":
    asyncio.run(verify_endpoints())
