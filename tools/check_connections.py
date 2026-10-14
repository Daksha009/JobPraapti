"""Read-only live checks using the local encrypted credentials; never apply."""

import asyncio
import json
from jobpilot.dashboard.connections import check_gemini, check_platform
from jobpilot.registry import platform_names


async def main():
    print(json.dumps(await check_gemini()), flush=True)
    for name in platform_names():
        print(json.dumps(await check_platform(name)), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
